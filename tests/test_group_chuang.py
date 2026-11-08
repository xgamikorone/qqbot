"""Offline group game storage, concurrency and raw SDK dispatch tests."""

import concurrent.futures
import contextlib
import pathlib
import sqlite3
import tempfile
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from botpy_ext import group_upload
from commands import chuang
from commands import manager


class GroupChuangTests(unittest.IsolatedAsyncioTestCase):
    """Uses a memory database and mocks both image and QQ transports."""

    def setUp(self) -> None:
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.dao = dao.Dao(":memory:")
        self.addCleanup(self.dao.close)
        self.stack.enter_context(
            mock.patch.object(dao, "_dao_instance", self.dao)
        )
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.upload = self.stack.enter_context(
            mock.patch.object(
                group_upload,
                "upload_group_image",
                new=mock.AsyncMock(
                    return_value={
                        "file_info": "image",
                        "file_uuid": "f",
                        "ttl": 300,
                    }
                ),
            )
        )
        self.draw = self.stack.enter_context(
            mock.patch.object(chuang, "biased_random", return_value=700)
        )
        self.date = self.stack.enter_context(
            mock.patch.object(chuang, "today_str", return_value="2026-11-08")
        )
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0

    async def dispatch(
        self,
        group: str = "group",
        member: str = "member",
        content: str = "/开创",
    ) -> None:
        """Sends a raw SDK group event through the production dispatcher."""
        self.counter += 1
        message = botpy_message.GroupMessage(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": str(self.counter),
                    "content": content,
                    "group_openid": group,
                    "author": {"member_openid": member},
                },
            ),
        )
        setattr(message.author, "username", "小明")
        await self.manager.execute_group(message)

    async def test_daily_result_repeats_with_same_image_and_text(self) -> None:
        await self.dispatch()
        first = self.api.post_group_message.await_args.kwargs["content"]
        await self.dispatch(content="/chuang")
        self.assertEqual(
            first, self.api.post_group_message.await_args.kwargs["content"]
        )
        self.draw.assert_called_once()
        self.assertIn("小明今天被瞳瞳车创飞了700米", first)
        call = self.upload.await_args
        assert call is not None
        self.assertEqual(chuang.IMG_BREAK, call.args[2])
        self.assertEqual(
            1,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_chuang_daily"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM user_chuang_daily"
            ).fetchone()[0],
        )

    async def test_groups_and_members_have_independent_results(self) -> None:
        self.draw.side_effect = [700, 200, 300]
        await self.dispatch()
        await self.dispatch("other")
        await self.dispatch(member="other")
        self.assertEqual(3, self.draw.call_count)
        self.assertEqual(
            3,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_chuang_daily"
            ).fetchone()[0],
        )
        self.assertIn(
            "今日排名第2名",
            self.api.post_group_message.await_args.kwargs["content"],
        )

    async def test_next_day_record_and_image_rules(self) -> None:
        await self.dispatch()
        for day, value, image in (
            ("2026-11-09", 600, chuang.IMG_HIGH),
            ("2026-11-10", 100, chuang.IMG_LOW),
            ("2026-11-11", 800, chuang.IMG_BREAK),
        ):
            self.date.return_value = day
            self.draw.return_value = value
            await self.dispatch()
            call = self.upload.await_args
            assert call is not None
            self.assertEqual(image, call.args[2])

    async def test_upload_failure_keeps_result_and_replies_with_text(
        self,
    ) -> None:
        self.upload.side_effect = RuntimeError("upload failed")
        await self.dispatch(content="/开创 && /time")
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertIn("700米", calls[0].kwargs["content"])
        self.assertIn("图片暂时无法加载", calls[0].kwargs["content"])
        await self.dispatch()
        self.draw.assert_called_once()

    async def test_send_failure_keeps_result_without_retrying_image(
        self,
    ) -> None:
        self.api.post_group_message.side_effect = [
            RuntimeError("send failed"),
            None,
        ]
        await self.dispatch(content="/开创 && /time")
        self.upload.assert_awaited_once()
        self.assertEqual(2, self.api.post_group_message.await_count)
        self.api.post_group_message.side_effect = None
        await self.dispatch()
        self.draw.assert_called_once()

    async def test_channel_still_uses_original_storage_and_reply(self) -> None:
        message = botpy_message.Message(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": "channel-message",
                    "content": "/开创",
                    "guild_id": "guild",
                    "channel_id": "channel",
                    "author": {"id": "user", "username": "小明"},
                },
            ),
        )
        with mock.patch.object(
            botpy_message.Message, "reply", new=mock.AsyncMock()
        ) as reply:
            await self.manager.execute_guild(message, ["<@!1>", "/开创"])
        call = reply.await_args
        assert call is not None
        self.assertEqual(chuang.IMG_BREAK, call.kwargs["file_image"])
        self.assertEqual(
            700, self.dao.chuang.get_distance("user", "2026-11-08")
        )
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_chuang_daily"
            ).fetchone()[0],
        )
        self.upload.assert_not_awaited()


class GroupChuangRepositoryTests(unittest.TestCase):
    """Checks transaction boundaries and ranking semantics independently."""

    def test_ties_and_history_compare_personal_bests_not_record_count(
        self,
    ) -> None:
        database = dao.Dao(":memory:")
        self.addCleanup(database.close)
        repo = database.group_chuang
        repo.get_or_create("g", "a", "2026-11-01", lambda: 900)
        repo.get_or_create("g", "a", "2026-11-02", lambda: 800)
        repo.get_or_create("g", "b", "2026-11-02", lambda: 500)
        result = repo.get_or_create("g", "c", "2026-11-02", lambda: 500)
        self.assertEqual((2, 2), (result.daily_rank, result.history_rank))
        self.assertTrue(result.personal_record)

    def test_invalid_draw_rolls_back_and_can_retry(self) -> None:
        database = dao.Dao(":memory:")
        self.addCleanup(database.close)
        with self.assertRaises(sqlite3.IntegrityError):
            database.group_chuang.get_or_create(
                "g", "m", "2026-11-08", lambda: 1000
            )
        result = database.group_chuang.get_or_create(
            "g", "m", "2026-11-08", lambda: 100
        )
        self.assertEqual(100, result.distance)

    def test_two_connections_draw_once_and_schema_reopen_preserves_channel_data(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / "test.db")
            first, second = dao.Dao(path), dao.Dao(path)
            try:
                first.chuang.record(
                    "user", 999, "channel", "guild", "2026-11-08"
                )
                draw = mock.Mock(return_value=123)

                def run(database: dao.Dao) -> int:
                    return database.group_chuang.get_or_create(
                        "g", "m", "2026-11-08", draw
                    ).distance

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=2
                ) as pool:
                    self.assertEqual(
                        [123, 123], list(pool.map(run, [first, second]))
                    )
                draw.assert_called_once()
            finally:
                first.close()
                second.close()
            reopened = dao.Dao(path)
            try:
                self.assertEqual(
                    999, reopened.chuang.get_distance("user", "2026-11-08")
                )
                self.assertEqual(
                    123,
                    reopened.group_chuang.get_or_create(
                        "g", "m", "2026-11-08", draw
                    ).distance,
                )
                draw.assert_called_once()
            finally:
                reopened.close()
