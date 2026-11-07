"""Offline raw-event dispatch coverage for charts and repeat."""

import asyncio
import contextlib
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
from commands import manager
from commands import revenue_rank
from commands import revenue_rank_v2
from utils import revenue_rank_cache


class GroupImageCommandsTests(unittest.IsolatedAsyncioTestCase):
    """Isolates databases, charts, upstream data and all QQ transports."""

    def setUp(self) -> None:
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.dao = dao.Dao(":memory:")
        self.addCleanup(self.dao.close)
        self.stack.enter_context(
            mock.patch.object(dao, "_dao_instance", self.dao))
        self.stack.enter_context(mock.patch.dict(base.last_used, {},
                                                 clear=True))
        self.stack.enter_context(
            mock.patch.object(base, "_running_commands", set()))
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = pathlib.Path(self.temp) / "chart.png"
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.api.post_message = mock.AsyncMock()
        self.api.post_group_file = mock.AsyncMock(return_value={
            "file_info": "remote",
            "file_uuid": "f",
            "ttl": 300
        })
        self.upload = self.stack.enter_context(
            mock.patch.object(
                group_upload,
                "upload_group_image",
                new=mock.AsyncMock(return_value={
                    "file_info": "local",
                    "file_uuid": "f",
                    "ttl": 300
                })))
        self.old_fetch = self.stack.enter_context(
            mock.patch.object(
                revenue_rank,
                "get_revenue_rank_with_retry",
                new=mock.AsyncMock(return_value=revenue_rank_cache.
                                   RevenueRankFetchResult(data={
                                       "month": "202611",
                                       "anchors": [{
                                           "name": "主播"
                                       }]
                                   },
                                                          source="remote",
                                                          cached_at=None))))
        self.new_fetch = self.stack.enter_context(
            mock.patch.object(revenue_rank_v2,
                              "fetch_realtime_revenue",
                              new=mock.AsyncMock(return_value=[{
                                  "uid": 1,
                                  "name": "主播",
                                  "total_income": 10
                              }])))
        self.draw_old = self.stack.enter_context(
            mock.patch.object(revenue_rank,
                              "draw_rank_table",
                              side_effect=self.draw))
        self.draw_new = self.stack.enter_context(
            mock.patch.object(revenue_rank_v2,
                              "draw_realtime_revenue_table",
                              side_effect=self.draw))
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0

    def draw(self, *args: object) -> str:
        """Produces a disposable file without using matplotlib."""
        self.path.write_bytes(b"chart")
        return str(self.path)

    async def dispatch(self,
                       content: str,
                       *,
                       guild: bool = False,
                       attachment: bool = False,
                       mime: str = "image/png") -> None:
        """Creates the same raw SDK events received by production handlers."""
        self.counter += 1
        payload = typing.cast(
            gateway.MessagePayload, {
                "id":
                    str(self.counter),
                "content":
                    content,
                "group_openid":
                    "group",
                "channel_id":
                    "channel",
                "guild_id":
                    "guild",
                "author": {
                    "id": "user",
                    "username": "用户",
                    "member_openid": "member"
                },
                "attachments": [{
                    "url": "//example.invalid/image.png",
                    "content_type": mime
                }] if attachment else [],
            })
        if guild:
            await self.manager.execute_guild(
                botpy_message.Message(self.api, "event", payload),
                ["<@!1>", *content.split()])
        else:
            await self.manager.execute_group(
                botpy_message.GroupMessage(self.api, "event", payload))

    async def test_both_charts_send_progress_image_and_chain_then_cleanup(
            self) -> None:
        for command in ("斗虫", "斗虫v2"):
            with self.subTest(command=command):
                self.api.post_group_message.reset_mock()
                await self.dispatch(f"/{command} && /time")
                calls = self.api.post_group_message.await_args_list
                self.assertEqual([1, 2, 3],
                                 [call.kwargs["msg_seq"] for call in calls])
                self.assertEqual(7, calls[1].kwargs["msg_type"])
                self.assertEqual("local", calls[1].kwargs["media"]["file_info"])
                self.assertFalse(self.path.exists())
        self.api.post_message.assert_not_awaited()

    async def test_channel_still_uses_local_file_transport(self) -> None:
        for command in ("斗虫", "斗虫v2"):
            await self.dispatch(f"/{command}", guild=True)
            self.assertEqual(
                str(self.path),
                self.api.post_message.await_args.kwargs["file_image"])
            self.assertFalse(self.path.exists())
        self.upload.assert_not_awaited()

    async def test_success_cooldown_is_shared_across_scene_and_alias(
            self) -> None:
        await self.dispatch("/斗虫v2")
        await self.dispatch("/revenue_rank_v2", guild=True)
        self.new_fetch.assert_awaited_once()
        self.assertIn("冷却", self.api.post_message.await_args.kwargs["content"])

    async def test_invalid_arguments_do_not_consume_cooldown(self) -> None:
        await self.dispatch("/斗虫v2 /m nonsense && /time")
        self.assertNotIn("revenue_rank_v2", base.last_used)
        self.new_fetch.assert_not_awaited()
        self.assertEqual(1, self.api.post_group_message.await_count)

    async def test_upload_failure_cleans_file_and_stops_chain(self) -> None:
        self.upload.side_effect = RuntimeError("upload failed")
        await self.dispatch("/斗虫 && /time")
        self.assertFalse(self.path.exists())
        self.assertNotIn("revenue_rank", base.last_used)
        self.assertNotIn("revenue_rank", base._running_commands)
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertTrue(all("media" not in call.kwargs for call in calls))

    async def test_image_send_failure_never_retries_or_starts_cooldown(
            self) -> None:
        self.api.post_group_message.side_effect = [
            None, RuntimeError("send failed"), None
        ]
        await self.dispatch("/斗虫v2 && /time")
        self.upload.assert_awaited_once()
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2, 3], [call.kwargs["msg_seq"] for call in calls])
        self.assertEqual(1, sum("media" in call.kwargs for call in calls))
        self.assertFalse(self.path.exists())
        self.assertNotIn("revenue_rank_v2", base.last_used)

    async def test_running_guard_blocks_other_scene(self) -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def query(*args: object) -> list[dict[str, object]]:
            entered.set()
            await release.wait()
            return [{"uid": 1, "name": "主播", "total_income": 10}]

        self.new_fetch.side_effect = query
        task = asyncio.create_task(self.dispatch("/斗虫v2"))
        try:
            await entered.wait()
            await self.dispatch("/斗虫v2", guild=True)
            self.assertIn("正在执行",
                          self.api.post_message.await_args.kwargs["content"])
        finally:
            release.set()
            await task

    async def test_repeat_group_attachment_and_text_alias(self) -> None:
        await self.dispatch("/复读 你好", attachment=True)
        self.api.post_group_file.assert_awaited_once_with(
            group_openid="group",
            file_type=1,
            url="https://example.invalid/image.png",
            srv_send_msg=False)
        call = self.api.post_group_message.await_args.kwargs
        self.assertEqual("一位朋友: 你好", call["content"])
        self.assertEqual(7, call["msg_type"])
        await self.dispatch("/echo 文字")
        self.assertNotIn("media", self.api.post_group_message.await_args.kwargs)

    async def test_repeat_non_image_and_upload_failure(self) -> None:
        await self.dispatch("/repeat 文件",
                            attachment=True,
                            mime="application/pdf")
        self.api.post_group_file.assert_not_awaited()
        self.api.post_group_file.side_effect = RuntimeError("upload failed")
        await self.dispatch("/repeat 图片", attachment=True)
        self.assertIn("图片暂时无法加载",
                      self.api.post_group_message.await_args.kwargs["content"])

    async def test_repeat_channel_keeps_author_and_cover(self) -> None:
        await self.dispatch("/复读 你好", guild=True, attachment=True)
        self.assertEqual("用户: 你好",
                         self.api.post_message.await_args.kwargs["content"])
        self.assertEqual("https://example.invalid/image.png",
                         self.api.post_message.await_args.kwargs["image"])

    async def test_group_chart_help(self) -> None:
        await self.dispatch("/斗虫帮助")
        self.assertIn(
            "斗虫 指令用法",
            self.api.post_group_message.await_args_list[0].kwargs["content"])
