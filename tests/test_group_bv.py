"""Offline BV cover upload, reply sequencing and failure-path tests."""

import contextlib
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from commands import base
from commands import bv
from commands import manager


class GroupBVTests(unittest.IsolatedAsyncioTestCase):
    """Uses real SDK events, a memory database and mocked upstream APIs."""

    def setUp(self) -> None:
        self.dao = dao.Dao(":memory:")
        self.addCleanup(self.dao.close)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            mock.patch.object(dao, "_dao_instance", self.dao))
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.api.post_message = mock.AsyncMock()
        self.api.post_group_file = mock.AsyncMock(return_value={
            "file_info": "uploaded-cover",
            "file_uuid": "file-id",
            "ttl": 300,
        })
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.response: bv.VideoResponse = {
            "code": 0,
            "data": {
                "title": "测试视频",
                "bvid": "BV1xx411c7mD",
                "pic": "https://example.invalid/cover.jpg",
                "pubdate": 0,
                "owner": {
                    "name": "测试UP"
                },
                "stat": {
                    "view": 1,
                    "danmaku": 2,
                    "like": 3,
                    "reply": 4,
                    "favorite": 5
                },
            },
        }
        self.fetch = self.stack.enter_context(
            mock.patch.object(bv.live_data,
                              "get_bv_info",
                              new=mock.AsyncMock(return_value=self.response)))
        self.stack.enter_context(
            mock.patch.object(bv.async_retry.asyncio,
                              "sleep",
                              new=mock.AsyncMock()))

    async def dispatch(self, content: str, *, guild: bool = False) -> None:
        """Passes the original SDK event through the command manager."""
        payload = typing.cast(
            gateway.MessagePayload, {
                "id": "incoming",
                "content": content,
                "group_openid": "group",
                "channel_id": "channel",
                "guild_id": "guild",
                "author": {
                    "id": "user",
                    "username": "用户",
                    "member_openid": "member"
                },
            })
        if guild:
            await self.manager.execute_guild(
                botpy_message.Message(self.api, "event", payload),
                ["<@!1>", *content.split()])
        else:
            await self.manager.execute_group(
                botpy_message.GroupMessage(self.api, "event", payload))

    async def test_group_upload_then_media_reply_and_chain_sequence(
            self) -> None:
        await self.dispatch("/查bv BV1xx411c7mD && /time")
        self.api.post_group_file.assert_awaited_once_with(
            group_openid="group",
            file_type=1,
            url="https://example.invalid/cover.jpg",
            srv_send_msg=False)
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertEqual(7, calls[0].kwargs["msg_type"])
        self.assertEqual("uploaded-cover",
                         calls[0].kwargs["media"]["file_info"])
        self.assertEqual("incoming", calls[0].kwargs["msg_id"])
        self.assertIn("1970-01-01 08:00:00", calls[0].kwargs["content"])
        self.api.post_message.assert_not_awaited()
        self.assertEqual(
            2,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_command_records WHERE succeeded=1").
            fetchone()[0])

    async def test_channel_keeps_url_cover_and_same_text(self) -> None:
        await self.dispatch("/查视频 BV1xx411c7mD", guild=True)
        channel = self.api.post_message.await_args.kwargs
        self.assertEqual("https://example.invalid/cover.jpg", channel["image"])
        self.api.post_group_file.assert_not_awaited()
        await self.dispatch("/查BV BV1xx411c7mD")
        self.assertEqual(
            channel["content"],
            self.api.post_group_message.await_args.kwargs["content"])

    async def test_upload_failure_falls_back_to_text(self) -> None:
        self.api.post_group_file.side_effect = RuntimeError("upload rejected")
        await self.dispatch("/查bv BV1xx411c7mD && /time")
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertNotIn("media", calls[0].kwargs)
        self.assertIn("标题: 测试视频", calls[0].kwargs["content"])
        self.assertIn("封面暂时无法加载", calls[0].kwargs["content"])

    async def test_missing_file_info_never_sends_invalid_media(self) -> None:
        for response in (None, {}, {"file_info": ""}, {"file_info": 1}):
            with self.subTest(response=response):
                self.api.post_group_file.return_value = response
                self.api.post_group_message.reset_mock()
                await self.dispatch("/查bv BV1xx411c7mD")
                call = self.api.post_group_message.await_args.kwargs
                self.assertNotIn("media", call)
                self.assertIn("封面暂时无法加载", call["content"])

    async def test_send_failure_does_not_retry_video_or_continue_chain(
            self) -> None:
        self.api.post_group_message.side_effect = [
            RuntimeError("send failed"), None
        ]
        await self.dispatch("/查bv BV1xx411c7mD && /time")
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertIn("media", calls[0].kwargs)
        self.assertNotIn("media", calls[1].kwargs)
        self.assertIn("执行命令时发生错误", calls[1].kwargs["content"])
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT succeeded FROM group_command_records").fetchone()[0])

    async def test_missing_argument_stops_chain_without_query(self) -> None:
        await self.dispatch("/查bv && /time")
        self.fetch.assert_not_awaited()
        self.api.post_group_file.assert_not_awaited()
        self.assertEqual(1, self.api.post_group_message.await_count)
        self.assertIn("请输入",
                      self.api.post_group_message.await_args.kwargs["content"])

    async def test_empty_business_error_and_malformed_results(self) -> None:
        for response in (None, {
                "code": -400,
                "message": "请求错误"
        }, {
                "code": 0
        }, {
                "code": 0,
                "data": {}
        }, {
                "code": 0,
                "data": {
                    "pubdate": "invalid"
                }
        }):
            with self.subTest(response=response):
                self.fetch.return_value = response
                self.api.post_group_message.reset_mock()
                await self.dispatch("/查bv BV1xx411c7mD && /time")
                self.api.post_group_file.assert_not_awaited()
                self.assertEqual(1, self.api.post_group_message.await_count)
                self.assertIn(
                    "查询遇到错误",
                    self.api.post_group_message.await_args.kwargs["content"])

    def test_group_help_lists_bv_without_opening_c2c(self) -> None:
        self.assertIn("查BV", base.render_scene_help("group"))
        self.assertFalse(bv.SearchBVCommand.supports_scene("user"))
