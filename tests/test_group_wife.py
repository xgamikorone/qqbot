"""Offline group wife commands and isolated daily assignment storage."""

import concurrent.futures
import contextlib
import datetime
import pathlib
import tempfile
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from botpy_ext import group_upload
from commands import base
from commands import group_wife
from commands import manager
from commands import wife


class GroupWifeTests(unittest.IsolatedAsyncioTestCase):
    """Exercises raw SDK dispatch without real images, APIs or credentials."""

    def setUp(self) -> None:
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.dao = dao.Dao(":memory:")
        self.addCleanup(self.dao.close)
        self.stack.enter_context(
            mock.patch.object(dao, "_dao_instance", self.dao)
        )
        self.directory = pathlib.Path(
            self.stack.enter_context(tempfile.TemporaryDirectory())
        )
        self.source = self.directory / "source.png"
        self.source.write_bytes(b"image")
        self.table = self.directory / "table.jpg"
        wife_id = self.dao.wives.add("小红", str(self.source))
        assert wife_id is not None
        self.wife_id: int = wife_id
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.api.post_message = mock.AsyncMock()
        self.api.post_group_file = mock.AsyncMock(
            return_value={"file_info": "remote", "file_uuid": "f", "ttl": 100}
        )
        self.upload = self.stack.enter_context(
            mock.patch.object(
                group_upload,
                "upload_group_image",
                new=mock.AsyncMock(
                    return_value={
                        "file_info": "image",
                        "file_uuid": "f",
                        "ttl": 100,
                    }
                ),
            )
        )
        self.now = datetime.datetime(2026, 11, 8, 12)
        self.gate = self.stack.enter_context(
            mock.patch.object(
                wife,
                "get_today_refresh_time",
                return_value=(self.now, self.now.replace(hour=8)),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                group_wife.time_utils, "beijing_now", return_value=self.now
            )
        )
        self.build = self.stack.enter_context(
            mock.patch.object(
                wife,
                "build_wife_list_image",
                new=mock.AsyncMock(side_effect=self.build_table),
            )
        )
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0

    async def build_table(self, *args: object, **kwargs: object) -> str:
        """Makes only a disposable table file, never touching catalog images."""
        self.table.write_bytes(b"table")
        return str(self.table)

    async def dispatch(
        self, content: str, group: str = "g", member: str = "m"
    ) -> None:
        """Creates a raw SDK group event with a retained display name."""
        self.counter += 1
        event = botpy_message.GroupMessage(
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
        setattr(event.author, "username", "小明")
        await self.manager.execute_group(event)

    def count(self) -> int:
        """Returns the number of group assignments only."""
        return self.dao.conn.execute(
            "SELECT COUNT(*) FROM group_wife_daily"
        ).fetchone()[0]

    async def test_daily_repeat_is_stable_and_channel_history_untouched(
        self,
    ) -> None:
        await self.dispatch("/来个老婆 && /我的老婆 今天")
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertIn("小明, 你的今日老婆：小红", calls[0].kwargs["content"])
        self.assertIn("2026-11-08的老婆是：小红", calls[1].kwargs["content"])
        self.dao.wives.set_enabled(self.wife_id, False)
        self.dao.wives.add("另一个", str(self.directory / "other.png"))
        await self.dispatch("/wife")
        self.assertIn(
            "小红", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertEqual(1, self.count())
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM user_wife_daily"
            ).fetchone()[0],
        )
        self.assertTrue(self.source.exists())

    async def test_group_member_and_date_isolation(self) -> None:
        await self.dispatch("/wife")
        await self.dispatch("/wife", group="other")
        await self.dispatch("/wife", member="other")
        tomorrow = self.now + datetime.timedelta(days=1)
        self.gate.return_value = (tomorrow, tomorrow.replace(hour=8))
        await self.dispatch("/wife")
        self.assertEqual(4, self.count())

    async def test_before_refresh_creates_nothing_and_stops_chain(self) -> None:
        self.gate.return_value = (
            self.now.replace(hour=7),
            self.now.replace(hour=8),
        )
        await self.dispatch("/wife && /time")
        self.assertEqual(0, self.count())
        self.upload.assert_not_awaited()
        self.assertEqual(1, self.api.post_group_message.await_count)
        self.assertIn(
            "还没有到", self.api.post_group_message.await_args.kwargs["content"]
        )

    async def test_empty_enabled_pool_creates_no_assignment(self) -> None:
        self.dao.wives.set_enabled(self.wife_id, False)
        await self.dispatch("/wife")
        self.assertEqual(0, self.count())
        self.assertIn(
            "获取老婆失败",
            self.api.post_group_message.await_args.kwargs["content"],
        )

    async def test_history_never_draws_or_reads_other_groups(self) -> None:
        await self.dispatch("/wife")
        await self.dispatch("/我的老婆 今天", group="other")
        self.assertIn(
            "没有老婆", self.api.post_group_message.await_args.kwargs["content"]
        )
        await self.dispatch("/我的老婆 昨天")
        self.assertIn(
            "2026-11-07没有老婆",
            self.api.post_group_message.await_args.kwargs["content"],
        )
        await self.dispatch("/我的老婆 nonsense && /time")
        self.assertIn(
            "无法解析日期",
            self.api.post_group_message.await_args.kwargs["content"],
        )
        self.assertEqual(1, self.count())

    async def test_upload_failure_preserves_draw_and_text(self) -> None:
        self.upload.side_effect = RuntimeError("upload failed")
        await self.dispatch("/wife")
        self.assertIn(
            "小红", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertIn(
            "图片暂时无法加载",
            self.api.post_group_message.await_args.kwargs["content"],
        )
        await self.dispatch("/wife")
        self.assertEqual(1, self.count())

    async def test_send_failure_is_not_retried_and_draw_survives(self) -> None:
        self.api.post_group_message.side_effect = [
            RuntimeError("send failed"),
            None,
        ]
        await self.dispatch("/wife && /time")
        self.upload.assert_awaited_once()
        self.assertEqual(1, self.count())
        self.assertEqual(2, self.api.post_group_message.await_count)

    async def test_catalog_search_detail_aliases_and_cleanup(self) -> None:
        for content in (
            "/老婆列表",
            "/wife_list 1",
            "/查老婆 小",
            "/wife_search 小",
            f"/wife_by_id {self.wife_id}",
        ):
            with self.subTest(content=content):
                await self.dispatch(content)
                self.assertEqual(
                    7, self.api.post_group_message.await_args.kwargs["msg_type"]
                )
                self.assertFalse(self.table.exists())
                self.assertTrue(self.source.exists())
        self.assertEqual(0, self.count())

    async def test_catalog_validation_and_missing_detail(self) -> None:
        for content, expected in (
            ("/老婆列表 0", "正整数"),
            ("/老婆列表 2", "不存在"),
            ("/查老婆", "用法"),
            ("/查老婆 不存在", "没有找到"),
            ("/老婆详情 abc", "用法"),
            ("/老婆详情 999", "没有找到"),
        ):
            await self.dispatch(content)
            self.assertIn(
                expected,
                self.api.post_group_message.await_args.kwargs["content"],
            )
        self.assertEqual(0, self.count())

    async def test_list_build_and_upload_failures_keep_full_text(self) -> None:
        self.build.side_effect = RuntimeError("draw failed")
        await self.dispatch("/老婆列表")
        self.assertIn(
            "小红", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.build.side_effect = self.build_table
        self.upload.side_effect = RuntimeError("upload failed")
        await self.dispatch("/查老婆 小")
        self.assertIn(
            "小红", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertFalse(self.table.exists())
        self.assertTrue(self.source.exists())

    async def test_list_send_failure_cleans_table_without_resending(
        self,
    ) -> None:
        self.api.post_group_message.side_effect = [
            RuntimeError("send failed"),
            None,
        ]
        await self.dispatch("/老婆列表 && /time")
        self.assertFalse(self.table.exists())
        self.assertEqual(2, self.api.post_group_message.await_count)
        self.upload.assert_awaited_once()

    async def test_remote_resource_uses_url_upload(self) -> None:
        self.dao.wives.update(
            self.wife_id, url="https://example.invalid/image.png"
        )
        await self.dispatch(f"/老婆详情 {self.wife_id}")
        self.api.post_group_file.assert_awaited_once_with(
            group_openid="g",
            file_type=1,
            url="https://example.invalid/image.png",
            srv_send_msg=False,
        )
        self.upload.assert_not_awaited()

    def test_administration_stays_channel_only(self) -> None:
        for alias in (
            "wife_add",
            "wife_update",
            "wife_enable",
        ):
            command = self.manager.commands[alias]
            self.assertFalse(command.supports_scene("group"))
            self.assertTrue(command.owner_only)
        self.assertIn("老婆列表", base.render_scene_help("group"))


class GroupWifeStorageTests(unittest.TestCase):
    """Checks parallel first draws and additive schema initialization."""

    def test_two_connections_draw_once_and_history_survives_reopen(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / "test.db")
            first, second = dao.Dao(path), dao.Dao(path)
            try:
                wife_id = first.wives.add("小红", "image.png")
                first.wives.get_or_draw("user", "channel", "guild")

                def draw(database: dao.Dao) -> int:
                    result = database.group_wives.get_or_draw(
                        "g", "m", "2026-11-08"
                    )
                    assert result is not None
                    return result.id

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=2
                ) as pool:
                    self.assertEqual(
                        [wife_id, wife_id],
                        list(pool.map(draw, [first, second])),
                    )
                self.assertEqual(
                    1,
                    first.conn.execute(
                        "SELECT COUNT(*) FROM group_wife_daily"
                    ).fetchone()[0],
                )
            finally:
                first.close()
                second.close()
            reopened = dao.Dao(path)
            try:
                result = reopened.group_wives.get_for_date(
                    "g", "m", "2026-11-08"
                )
                assert result is not None
                self.assertEqual(wife_id, result.id)
                self.assertEqual(
                    1,
                    reopened.conn.execute(
                        "SELECT COUNT(*) FROM user_wife_daily"
                    ).fetchone()[0],
                )
            finally:
                reopened.close()
