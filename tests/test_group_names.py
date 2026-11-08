"""Offline event nickname retention, member lookup and cache coverage."""

import asyncio
import contextlib
import json
import types
import typing
import unittest
from unittest import mock

from botpy import client as botpy_client
from botpy import connection as botpy_connection
from botpy import errors as botpy_errors
from botpy import message as botpy_message
from botpy.types import gateway

import dao
from botpy_ext import group_events
from botpy_ext import group_members
from commands import manager
from messaging import group_names


class GroupNamesTests(unittest.IsolatedAsyncioTestCase):
    """Keeps names isolated by group and leaves permissions unchanged."""

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
        self.fetch = self.stack.enter_context(
            mock.patch.object(
                group_members,
                "fetch_member_name",
                new=mock.AsyncMock(
                    return_value=group_members.MemberName("接口昵称")
                ),
            )
        )
        self.clock = 100.0
        self.stack.enter_context(
            mock.patch.object(
                group_names,
                "time",
                types.SimpleNamespace(monotonic=lambda: self.clock),
            )
        )
        self.resolver = group_names.GroupNameResolver(self.api, self.dao.groups)
        self.counter = 0

    def message(
        self, group: str = "group", name: str = "", content: str = "/复读 你好"
    ) -> botpy_message.GroupMessage:
        """Builds a raw SDK event with a retained username when requested."""
        self.counter += 1
        result = botpy_message.GroupMessage(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": str(self.counter),
                    "group_openid": group,
                    "content": content,
                    "author": {"member_openid": "member"},
                },
            ),
        )
        if name:
            setattr(result.author, "username", name)
        return result

    async def test_event_name_wins_without_api_and_is_cached(self) -> None:
        self.assertEqual(
            "事件昵称",
            await self.resolver.resolve(self.message(name=" 事件昵称 ")),
        )
        self.assertEqual(
            "事件昵称", await self.resolver.resolve(self.message())
        )
        self.fetch.assert_not_awaited()

    async def test_lookup_result_is_shared_and_scoped_by_group(self) -> None:
        first = self.message()
        self.assertEqual("接口昵称", await self.resolver.resolve(first))
        self.assertEqual("接口昵称", getattr(first.author, "username"))
        await self.resolver.resolve(self.message())
        self.fetch.assert_awaited_once_with(self.api, "group", "member")
        self.clock += 3
        self.fetch.return_value = group_members.MemberName("另一个群昵称")
        self.assertEqual(
            "另一个群昵称", await self.resolver.resolve(self.message("other"))
        )
        self.assertEqual(
            "接口昵称", await self.resolver.resolve(self.message())
        )

    async def test_permission_failure_suppresses_queries_for_one_hour(
        self,
    ) -> None:
        self.fetch.return_value = group_members.MemberName(
            permission_denied=True
        )
        self.assertEqual("", await self.resolver.resolve(self.message()))
        self.clock += 100
        self.assertEqual("", await self.resolver.resolve(self.message("other")))
        self.fetch.assert_awaited_once()
        self.clock += 3600
        self.fetch.return_value = group_members.MemberName("已开通")
        self.assertEqual(
            "已开通", await self.resolver.resolve(self.message("other"))
        )

    async def test_persisted_name_survives_lookup_failure(self) -> None:
        self.dao.conn.execute(
            "INSERT INTO group_members (group_openid, member_openid, display_name) VALUES (?, ?, ?)",
            ("group", "member", "已记录昵称"),
        )
        self.fetch.return_value = group_members.MemberName()
        self.assertEqual(
            "已记录昵称", await self.resolver.resolve(self.message())
        )
        self.clock += 61
        self.assertEqual(
            "已记录昵称", await self.resolver.resolve(self.message())
        )
        self.assertEqual(
            "", self.dao.groups.get_display_name("other", "member")
        )

    async def test_concurrent_lookups_do_not_duplicate_requests(self) -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def fetch(*args: object) -> group_members.MemberName:
            entered.set()
            await release.wait()
            return group_members.MemberName("接口昵称")

        self.fetch.side_effect = fetch
        first = asyncio.create_task(self.resolver.resolve(self.message()))
        await entered.wait()
        second = asyncio.create_task(self.resolver.resolve(self.message()))
        release.set()
        self.assertEqual(
            ["接口昵称", "接口昵称"], await asyncio.gather(first, second)
        )
        self.fetch.assert_awaited_once()

    async def test_new_event_name_wins_over_slow_api_response(self) -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def fetch(*args: object) -> group_members.MemberName:
            entered.set()
            await release.wait()
            return group_members.MemberName("旧接口昵称")

        self.fetch.side_effect = fetch
        task = asyncio.create_task(self.resolver.resolve(self.message()))
        await entered.wait()
        self.assertEqual(
            "新事件昵称",
            await self.resolver.resolve(self.message(name="新事件昵称")),
        )
        release.set()
        self.assertEqual("新事件昵称", await task)

    async def test_rate_limit_and_bounded_cache(self) -> None:
        await self.resolver.resolve(self.message())
        self.assertEqual("", await self.resolver.resolve(self.message("other")))
        self.fetch.assert_awaited_once()
        self.clock += 4
        await self.resolver.resolve(self.message("other"))
        self.assertEqual(2, self.fetch.await_count)
        for index in range(2050):
            await self.resolver.resolve(self.message(str(index), name="昵称"))
        self.assertLessEqual(len(self.resolver._cache), 2048)

    async def test_commands_share_lookup_and_persist_resolved_name(
        self,
    ) -> None:
        command_manager = manager.CommandManager(mock.Mock(api=self.api))
        await command_manager.execute_group(
            self.message(content="/复读 你好 && /生日快乐 小明")
        )
        self.fetch.assert_awaited_once()
        calls = self.api.post_group_message.await_args_list
        self.assertEqual("接口昵称: 你好", calls[0].kwargs["content"])
        self.assertIn("接口昵称为你", calls[1].kwargs["content"])
        self.assertEqual(
            "接口昵称", self.dao.groups.get_display_name("group", "member")
        )

    async def test_explicit_birthday_sender_does_not_lookup(self) -> None:
        command_manager = manager.CommandManager(mock.Mock(api=self.api))
        await command_manager.execute_group(
            self.message(content="/生日快乐 小明 小红")
        )
        self.fetch.assert_not_awaited()
        self.assertIn(
            "小红为你", self.api.post_group_message.await_args.kwargs["content"]
        )


class GroupParserTests(unittest.IsolatedAsyncioTestCase):
    """Exercises connection parser installation without logging in a bot."""

    async def test_parser_preserves_raw_sdk_message_fields_and_username(
        self,
    ) -> None:
        dispatch = mock.Mock()
        api = mock.Mock()
        connection = botpy_connection.ConnectionSession(
            max_async=1, connect=mock.AsyncMock(), dispatch=dispatch, api=api
        )
        original_channel_parser = connection.parser["at_message_create"]
        group_events.install_group_parser(connection)
        connection.parser["group_at_message_create"](
            {
                "id": "event",
                "d": {
                    "id": "message",
                    "group_openid": "group",
                    "content": "/复读 你好",
                    "author": {"member_openid": "member", "username": " 昵称 "},
                    "attachments": [
                        {
                            "url": "https://example.invalid/image.png",
                            "content_type": "image/png",
                        }
                    ],
                },
            }
        )
        event, message = dispatch.call_args.args
        self.assertEqual("group_at_message_create", event)
        self.assertIsInstance(message, botpy_message.GroupMessage)
        self.assertEqual("昵称", message.author.username)
        self.assertEqual("member", message.author.member_openid)
        self.assertEqual("group", message.group_openid)
        self.assertEqual("message", message.id)
        self.assertEqual(
            "https://example.invalid/image.png", message.attachments[0].url
        )
        self.assertIs(
            original_channel_parser, connection.parser["at_message_create"]
        )

    async def test_client_installs_parser_after_sdk_login(self) -> None:
        client = object.__new__(group_events.GroupNicknameClient)
        connection = mock.Mock(parser={})

        async def login(*args: object) -> None:
            client._connection = connection

        with mock.patch.object(botpy_client.Client, "_bot_login", new=login):
            await client._bot_login(mock.Mock())
        self.assertIn("group_at_message_create", connection.parser)


class MemberLookupTests(unittest.IsolatedAsyncioTestCase):
    """Checks the optional endpoint response and permission boundary."""

    async def test_endpoint_json_text_and_permission_errors(self) -> None:
        api = mock.Mock()
        api._http.request = mock.AsyncMock()
        for payload, name, denied in (
            ({"username": " 昵称 "}, "昵称", False),
            (json.dumps({"username": "昵称"}), "昵称", False),
            ({"code": 11253}, "", True),
            (None, "", False),
            ({"username": None}, "", False),
        ):
            with self.subTest(payload=payload):
                api._http.request.return_value = payload
                result = await group_members.fetch_member_name(
                    api, "group", "member"
                )
                self.assertEqual(
                    (name, denied), (result.name, result.permission_denied)
                )
        call = api._http.request.await_args
        assert call is not None
        route = call.args[0]
        self.assertEqual("GET", route.method)
        self.assertEqual(
            "/v2/groups/{group_openid}/members/{member_openid}", route.path
        )
        for error in (
            TimeoutError(),
            RuntimeError("private URL"),
            botpy_errors.ForbiddenError("denied"),
            RuntimeError("应用无接口访问权限"),
        ):
            api._http.request.side_effect = error
            result = await group_members.fetch_member_name(
                api, "group", "member"
            )
            self.assertEqual("", result.name)
            self.assertEqual(
                isinstance(error, botpy_errors.ForbiddenError)
                or "应用无接口访问权限" in str(error),
                result.permission_denied,
            )
