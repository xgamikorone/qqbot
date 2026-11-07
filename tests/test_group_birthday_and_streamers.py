"""Offline dispatch and HTTP boundary coverage for two group migrations."""

import contextlib
import typing
import unittest
from unittest import mock

import aiohttp
from botpy import message as botpy_message
from botpy.types import gateway

import dao
from commands import base
from commands import birthday
from commands import manager
from commands import user


class GroupBirthdayAndStreamersTests(unittest.IsolatedAsyncioTestCase):
    """Exercises raw SDK messages with an isolated database and fake API."""

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
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0
        self.query = self.stack.enter_context(
            mock.patch.object(user,
                              "get_all_streamers",
                              new=mock.AsyncMock(return_value=[{
                                  "uid": 1,
                                  "name": "主播"
                              }])))

    async def dispatch(self,
                       content: str,
                       *,
                       guild: bool = False,
                       nickname: str = "") -> list[str]:
        """Dispatches an event and checks transport isolation and sequences."""
        self.counter += 1
        self.api.post_group_message.reset_mock()
        self.api.post_message.reset_mock()
        payload = typing.cast(
            gateway.MessagePayload, {
                "id": str(self.counter),
                "content": content,
                "group_openid": "group",
                "guild_id": "guild",
                "channel_id": "channel",
                "author": {
                    "id": "user",
                    "member_openid": "member",
                    "username": "用户"
                },
            })
        if guild:
            message = botpy_message.Message(self.api, "event", payload)
            await self.manager.execute_guild(message,
                                             ["<@!1>", *content.split()])
            calls = self.api.post_message.await_args_list
            self.api.post_group_message.assert_not_awaited()
        else:
            group_message = botpy_message.GroupMessage(self.api, "event",
                                                       payload)
            # The current SDK drops username; model a future retained field.
            setattr(group_message.author, "username", nickname)
            await self.manager.execute_group(group_message)
            calls = self.api.post_group_message.await_args_list
            self.assertEqual(list(range(1,
                                        len(calls) + 1)),
                             [call.kwargs["msg_seq"] for call in calls])
            self.api.post_message.assert_not_awaited()
        return [call.kwargs["content"] for call in calls]

    async def test_birthday_sender_defaults_and_override(self) -> None:
        self.assertEqual([
            birthday.birthday_template.format(to="小明",
                                              from_="<@!user>").strip()
        ], await self.dispatch("/生日快乐 小明", guild=True))
        for nickname, expected in (("", "一位朋友"), (" 小红 ", "小红")):
            self.assertEqual([
                birthday.birthday_template.format(to="小明",
                                                  from_=expected).strip()
            ], await self.dispatch("/生日快乐 小明", nickname=nickname))
        self.assertEqual(await self.dispatch("/生日快乐 小明 小红", guild=True), await
                         self.dispatch("/生日快乐 小明 小红"))

    async def test_birthday_missing_argument_stops_chain(self) -> None:
        self.assertEqual(["请输入生日的用户!"], await self.dispatch("/生日快乐 && /所有主播"))
        self.query.assert_not_awaited()
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT succeeded FROM group_command_records").fetchone()[0])

    async def test_birthday_alias_and_chained_reply(self) -> None:
        texts = await self.dispatch("/happy_birthday 小明 小红 && /所有主播")
        self.assertEqual(2, len(texts))
        self.assertIn("小红为你", texts[0])
        self.assertIn("主播: 1", texts[1])

    async def test_streamer_aliases_match_channel_output(self) -> None:
        for alias in ("所有主播", "收录主播", "all_streamers"):
            with self.subTest(alias=alias):
                self.assertEqual(await self.dispatch(f"/{alias}", guild=True),
                                 await self.dispatch(f"/{alias}"))

    async def test_long_streamer_list_is_preserved_across_chunks(self) -> None:
        self.query.return_value = [{
            "uid": i,
            "name": f"主播{i}"
        } for i in range(400)]
        guild = await self.dispatch("/所有主播", guild=True)
        group = await self.dispatch("/所有主播")
        self.assertGreater(len(group), 1)
        self.assertEqual(guild[0], "".join(group))
        self.assertTrue(all(len(chunk) <= 1500 for chunk in group))

    async def test_empty_list_and_failure_have_distinct_results(self) -> None:
        self.query.return_value = []
        self.assertEqual(["暂无收录主播。"], await self.dispatch("/所有主播"))
        self.query.return_value = None
        self.assertEqual(["获取主播列表时出错!"], await
                         self.dispatch("/所有主播 && /生日快乐 小明"))
        self.assertEqual([1, 0], [
            row[0] for row in self.dao.conn.execute(
                "SELECT succeeded FROM group_command_records ORDER BY rowid")
        ])

    def test_help_and_scene_capabilities(self) -> None:
        group_help = base.render_scene_help("group")
        self.assertIn("生日快乐", group_help)
        self.assertIn("所有主播", group_help)
        for cls in (birthday.BirthdayCommand, user.AllStreamersCommand):
            self.assertTrue(cls.supports_scene("group"))
            self.assertFalse(cls.supports_scene("user"))


class StreamerResponseTests(unittest.IsolatedAsyncioTestCase):
    """Validates external JSON without making HTTP requests."""

    async def test_response_validation_and_request_failures(self) -> None:
        response = mock.Mock()
        response.json = mock.AsyncMock()
        request = mock.AsyncMock()
        request.__aenter__.return_value = response
        session = mock.Mock()
        session.get.return_value = request
        session_context = mock.AsyncMock()
        session_context.__aenter__.return_value = session
        with (mock.patch.object(user, "api_url", "https://example.invalid"),
              mock.patch.object(user, "proxy", None),
              mock.patch.object(user.aiohttp,
                                "ClientSession",
                                return_value=session_context)):
            for data, expected in (
                ({
                    "users": [{
                        "uid": "1",
                        "name": "主播"
                    }]
                }, [{
                    "uid": "1",
                    "name": "主播"
                }]),
                ({
                    "users": []
                }, []),
                (None, None),
                ({
                    "users": {}
                }, None),
                ({
                    "users": [None]
                }, None),
                ({
                    "users": [{
                        "uid": True,
                        "name": "主播"
                    }]
                }, None),
                ({
                    "users": [{
                        "uid": 1
                    }]
                }, None),
            ):
                with self.subTest(data=data):
                    response.json.return_value = data
                    self.assertEqual(expected, await user.get_all_streamers())
            for error in (aiohttp.ClientError("private URL"), TimeoutError(),
                          ValueError()):
                response.json.side_effect = error
                with self.assertLogs(user._log, level="WARNING") as logs:
                    self.assertIsNone(await user.get_all_streamers())
                self.assertNotIn("private URL", "".join(logs.output))
            response.raise_for_status.assert_called()
