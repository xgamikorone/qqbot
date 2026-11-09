"""Offline refresh scope isolation, authorization and draw gate tests."""

import contextlib
import datetime
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from botpy_ext import group_events
from botpy_ext import group_members
from botpy import connection as botpy_connection
from commands import manager
from commands import wife


class ScopedRefreshTests(unittest.IsolatedAsyncioTestCase):
    """Exercises real dispatch with memory storage and mocked member API."""

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
        self.api.post_message = mock.AsyncMock()
        self.fetch = self.stack.enter_context(
            mock.patch.object(
                group_members,
                "fetch_member_name",
                new=mock.AsyncMock(
                    return_value=group_members.MemberName(
                        permission_denied=True
                    )
                ),
            )
        )
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0

    async def dispatch(
        self,
        content: str,
        scope: str = "same",
        *,
        guild: bool = False,
        role: str = "",
        roles: list[str] | None = None,
    ) -> str:
        """Builds a raw event with platform roles, returning the latest reply."""
        self.counter += 1
        payload = typing.cast(
            gateway.MessagePayload,
            {
                "id": str(self.counter),
                "content": content,
                "group_openid": scope,
                "guild_id": scope,
                "channel_id": "channel",
                "author": {
                    "id": "user",
                    "username": "小明",
                    "member_openid": "member",
                },
                "member": {"roles": roles or []},
            },
        )
        if guild:
            await self.manager.execute_guild(
                botpy_message.Message(self.api, "event", payload),
                ["<@!1>", *content.split()],
            )
            return self.api.post_message.await_args.kwargs["content"]
        message = botpy_message.GroupMessage(self.api, "event", payload)
        setattr(message.author, "member_role", role)
        setattr(message.author, "username", "小明")
        await self.manager.execute_group(message)
        return self.api.post_group_message.await_args.kwargs["content"]

    async def test_defaults_and_identical_ids_stay_separate(self) -> None:
        self.dao.settings.set_wife_refresh_time("07:30")
        self.assertIn("07:30", await self.dispatch("/老婆刷新时间"))
        await self.dispatch("/设置老婆刷新时间 09:00", role="owner")
        await self.dispatch("/设置老婆刷新时间 10:00", guild=True, roles=["2"])
        self.assertEqual(
            "09:00", self.dao.settings.get_wife_refresh_time("group", "same")
        )
        self.assertEqual(
            "10:00", self.dao.settings.get_wife_refresh_time("guild", "same")
        )
        self.assertEqual(
            "07:30", self.dao.settings.get_wife_refresh_time("group", "other")
        )
        self.assertEqual("07:30", self.dao.settings.wife_refresh_time)

    async def test_public_query_never_requests_role(self) -> None:
        await self.dispatch("/老婆刷新时间")
        await self.dispatch("/老婆刷新时间 查询", guild=True)
        self.fetch.assert_not_awaited()

    async def test_group_current_member_denied_without_api_escalation(
        self,
    ) -> None:
        self.assertIn(
            "权限",
            await self.dispatch("/设置老婆刷新时间 09:00", role="member"),
        )
        self.fetch.assert_not_awaited()
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM wife_refresh_settings"
            ).fetchone()[0],
        )

    async def test_group_api_admin_allowed_but_failure_denied(self) -> None:
        self.assertIn("不允许", await self.dispatch("/设置老婆刷新时间 09:00"))
        self.fetch.return_value = group_members.MemberName(role="admin")
        self.assertIn("已设置", await self.dispatch("/设置老婆刷新时间 09:00"))
        self.fetch.return_value = group_members.MemberName(role="member")
        self.assertIn("不允许", await self.dispatch("/设置老婆刷新时间 11:00"))
        self.assertEqual(
            "09:00", self.dao.settings.get_wife_refresh_time("group", "same")
        )

    async def test_guild_role_validation_and_group_isolation(self) -> None:
        for roles in ([], ["1"], ["5"], ["arbitrary"]):
            self.assertIn(
                "不允许",
                await self.dispatch(
                    "/设置老婆刷新时间 09:00", guild=True, roles=roles
                ),
            )
        for role in ("2", "4"):
            self.assertIn(
                "已设置",
                await self.dispatch(
                    "/设置老婆刷新时间 09:00", guild=True, roles=[role]
                ),
            )

    async def test_bad_time_or_extra_args_never_write(self) -> None:
        for value in ("24:00", "09:60", "abc", "09:00 extra", "查询 extra"):
            self.assertIn(
                "格式错误",
                await self.dispatch("/设置老婆刷新时间 " + value, role="admin"),
            )
        self.fetch.assert_not_awaited()
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM wife_refresh_settings"
            ).fetchone()[0],
        )

    async def test_current_scope_gate_blocks_both_draw_paths(self) -> None:
        self.dao.settings.set_scoped_wife_refresh_time("guild", "same", "23:00")
        self.dao.settings.set_scoped_wife_refresh_time("group", "same", "22:00")
        observed: list[str] = []

        def gate(value: str) -> tuple[datetime.datetime, datetime.datetime]:
            observed.append(value)
            now = datetime.datetime(2026, 11, 9, 12)
            return now, now.replace(hour=23)

        with mock.patch.object(
            wife, "get_today_refresh_time", side_effect=gate
        ):
            await self.dispatch("/wife", guild=True)
            await self.dispatch("/wife")
        self.assertEqual(["23:00", "22:00"], observed)
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM user_wife_daily"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_wife_daily"
            ).fetchone()[0],
        )

    def test_parser_preserves_role_from_raw_event(self) -> None:
        dispatch = mock.Mock()
        connection = botpy_connection.ConnectionSession(
            1, mock.AsyncMock(), dispatch, api=self.api
        )
        group_events.install_group_parser(connection)
        connection.parser["group_at_message_create"](
            {
                "id": "event",
                "d": {
                    "id": "message",
                    "group_openid": "g",
                    "author": {"member_openid": "m", "member_role": "admin"},
                },
            }
        )
        self.assertEqual("admin", dispatch.call_args.args[1].author.member_role)
