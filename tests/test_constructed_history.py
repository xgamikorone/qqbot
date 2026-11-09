"""Synthetic-ID tests for opt-in, bounded history lookup experiments."""

import asyncio
import unittest
from unittest import mock

import dao
from botpy_ext import channel_history
from botpy_ext import constructed_history
from chat import config
from chat import model_client
from chat import summary
from messaging import message_id


def identifier(
    sequence: int, timestamp: int | None = None, channel: int = 42
) -> str:
    """Creates test-only compact IDs, never production samples."""
    return message_id.encode_message_id(
        999,
        channel,
        sequence,
        timestamp if timestamp is not None else 99 + sequence,
    )


class ConstructedHistoryTests(unittest.IsolatedAsyncioTestCase):
    """Never uses list APIs, sends messages or calls real model endpoints."""

    def setUp(self) -> None:
        self.api = mock.Mock()
        self.api.get_message = mock.AsyncMock(side_effect=self.fetch)
        self.sleep = mock.patch.object(
            constructed_history.asyncio, "sleep", new=mock.AsyncMock()
        ).start()
        self.addCleanup(mock.patch.stopall)

    def fetch(self, channel: str, candidate: str) -> dict[str, object]:
        """Returns the actual message ID, including its different timestamp."""
        sequence = message_id.decode_message_id(candidate).sequence
        return {
            "id": identifier(sequence),
            "channel_id": channel,
            "seq_in_channel": str(sequence),
            "content": "测试正文",
            "author": {"username": "用户"},
        }

    async def test_candidates_preserve_start_time_and_validate_real_time(
        self,
    ) -> None:
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(3)
        )
        records = result.records
        self.assertEqual("", result.stop_reason)
        self.assertEqual([1, 2, 3], [record.sequence for record in records])
        self.assertEqual(
            identifier(2, 100), self.api.get_message.await_args_list[1].args[1]
        )
        self.assertEqual(identifier(2, 101), records[1].id)
        self.api._http.request.assert_not_called()

    async def test_missing_message_stops_without_skipping(self) -> None:
        self.api.get_message.side_effect = [
            self.fetch("42", identifier(1)),
            self.fetch("42", identifier(2)),
            RuntimeError("not found"),
        ]
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(4)
        )
        self.assertEqual([1, 2], [row.sequence for row in result.records])
        self.assertTrue(result.stop_reason)
        self.assertNotIn("not found", result.stop_reason)
        self.assertEqual(3, self.api.get_message.await_count)

    async def test_wrong_sequence_channel_and_time_are_rejected(self) -> None:
        for bad in (
            {"id": identifier(4)},
            {"channel_id": "43"},
            {"id": identifier(2, 999)},
            {"seq_in_channel": "999"},
        ):
            middle = self.fetch("42", identifier(2))
            middle.update(bad)
            self.api.get_message.side_effect = [
                self.fetch("42", identifier(1)),
                middle,
            ]
            with self.subTest(bad=bad):
                result = await constructed_history.read_range(
                    self.api, "42", identifier(1), identifier(3)
                )
                self.assertEqual([1], [row.sequence for row in result.records])
                self.assertTrue(result.stop_reason)

    async def test_scope_and_size_caps_reject_before_any_request(self) -> None:
        for first, last in (
            (identifier(1), identifier(201)),
            (identifier(3), identifier(1)),
            (identifier(1), identifier(1, timestamp=101)),
            (identifier(1), identifier(3, channel=43)),
            ("unknown", identifier(3)),
        ):
            with self.assertRaises(channel_history.HistoryError):
                await constructed_history.read_range(
                    self.api, "42", first, last
                )
        self.api.get_message.assert_not_awaited()

    async def test_single_message_does_not_probe_neighbors(self) -> None:
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(1)
        )
        self.assertEqual(1, len(result.records))
        self.api.get_message.assert_awaited_once()

    async def test_two_hundred_message_range_is_supported(self) -> None:
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(200)
        )
        self.assertEqual(200, len(result.records))
        self.assertEqual(200, result.requested_count)
        self.assertEqual("", result.stop_reason)
        self.assertEqual(200, self.api.get_message.await_count)

    async def test_end_failure_returns_prefix_and_start_failure_aborts(
        self,
    ) -> None:
        self.api.get_message.side_effect = [
            self.fetch("42", identifier(1)),
            RuntimeError("endpoint missing"),
        ]
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(2)
        )
        self.assertEqual([1], [row.sequence for row in result.records])
        self.assertTrue(result.stop_reason)
        self.api.get_message.side_effect = RuntimeError("private detail")
        with self.assertRaises(channel_history.HistoryError) as error:
            await constructed_history.read_range(
                self.api, "42", identifier(1), identifier(2)
            )
        self.assertNotIn("private detail", str(error.exception))

    async def test_request_timeout_keeps_verified_prefix(self) -> None:
        self.api.get_message.side_effect = [
            self.fetch("42", identifier(1)),
            TimeoutError(),
        ]
        result = await constructed_history.read_range(
            self.api, "42", identifier(1), identifier(3)
        )
        self.assertEqual(1, len(result.records))
        self.assertIn("超时", result.stop_reason)

    async def test_total_timeout_keeps_prefix_but_cancellation_propagates(
        self,
    ) -> None:
        async def fetch(channel: str, candidate: str) -> dict[str, object]:
            if message_id.decode_message_id(candidate).sequence == 1:
                return self.fetch(channel, candidate)
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        self.api.get_message.side_effect = fetch
        with mock.patch.object(
            constructed_history, "READ_TIMEOUT_SECONDS", 0.01
        ):
            result = await constructed_history.read_range(
                self.api, "42", identifier(1), identifier(3)
            )
        self.assertEqual(1, len(result.records))
        self.assertIn("总时限", result.stop_reason)
        self.api.get_message.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await constructed_history.read_range(
                self.api, "42", identifier(1), identifier(3)
            )

    async def test_partial_range_summary_excludes_failure_and_labels_scope(
        self,
    ) -> None:
        database = dao.Dao(":memory:")
        self.addCleanup(database.close)
        settings = config.ChatConfig(
            enabled=True,
            allowed_channel_ids=("42",),
            summary_construct_ids=True,
        )
        service = summary.SummaryService(settings, self.api, database.chat)
        self.addAsyncCleanup(service.close)
        service.model.generate = mock.AsyncMock(
            return_value=model_client.GenerationResult("部分结论", "fake")
        )
        key = ("g", "42", "user")
        await service.mark(key, identifier(1), start=True)
        await service.mark(key, identifier(4), start=False)
        self.api.get_message.side_effect = [
            self.fetch("42", identifier(1)),
            self.fetch("42", identifier(2)),
            RuntimeError("private detail"),
        ]
        result = await service.summarize(key)
        self.assertIn("仅总结部分范围", result)
        self.assertIn("原选4条，连续读取成功2条", result)
        self.assertIn(identifier(2), result)
        self.assertNotIn("private detail", result)
        service.model.generate.assert_awaited_once()
        args = service.model.generate.call_args
        assert args is not None
        self.assertIn("不得推断", args.args[0][0]["content"])

    async def test_summary_switch_does_not_use_list_and_failure_does_not_call_model(
        self,
    ) -> None:
        database = dao.Dao(":memory:")
        self.addCleanup(database.close)
        settings = config.ChatConfig(
            enabled=True,
            allowed_channel_ids=("42",),
            summary_construct_ids=True,
        )
        service = summary.SummaryService(settings, self.api, database.chat)
        self.addAsyncCleanup(service.close)
        generate = mock.AsyncMock(
            return_value=model_client.GenerationResult("总结", "fake")
        )
        service.model.generate = generate
        key = ("g", "42", "user")
        await service.mark(key, identifier(1), start=True)
        await service.mark(key, identifier(3), start=False)
        self.assertEqual(identifier(1), service.selections[key].start)
        self.assertIn("实验性构造ID", await service.summarize(key))
        self.api._http.request.assert_not_called()
        generate.reset_mock()
        self.api.get_message.side_effect = RuntimeError("permission denied")
        with self.assertRaises(channel_history.HistoryError):
            await service.summarize(key)
        generate.assert_not_called()

    def test_loader_accepts_boolean_opt_in(self) -> None:
        self.assertFalse(config.load_config().summary_construct_ids)
