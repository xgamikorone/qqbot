"""Offline migration coverage for public streamer queries in guilds/groups."""

import contextlib
import types
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from commands import base
from commands import guards
from commands import manager
from commands import online
from commands import revenue
from commands import text_query


class GroupLiveQueryTests(unittest.IsolatedAsyncioTestCase):
    """Exercises actual dispatch with no production keys or network requests."""

    def setUp(self) -> None:
        self.dao = dao.Dao(":memory:")
        self.addCleanup(self.dao.close)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            mock.patch.object(dao, "_dao_instance", self.dao)
        )
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.api.post_message = mock.AsyncMock()
        self.api.post_c2c_message = mock.AsyncMock()
        self.manager = manager.CommandManager(mock.Mock(api=self.api))
        self.counter = 0
        self.on_live = self.stack.enter_context(
            mock.patch.object(
                online,
                "get_on_live_sessions",
                new=mock.AsyncMock(
                    return_value=[
                        {"uid": 100 + i, "name": f"直播{i}", "online_count": i}
                        for i in range(12)
                    ]
                ),
            )
        )
        self.stack.enter_context(
            mock.patch.object(online, "always_show_categories", [])
        )
        self.stack.enter_context(
            mock.patch.object(
                guards,
                "get_tagged_streamers",
                new=mock.AsyncMock(return_value=[{"uid": 1}, {"uid": 2}]),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                guards,
                "get_users_name_like",
                new=mock.AsyncMock(return_value=[{"uid": 1}, {"uid": 2}]),
            )
        )
        self.user_infos = self.stack.enter_context(
            mock.patch.object(
                guards,
                "get_user_info_by_uids",
                new=mock.AsyncMock(
                    return_value={
                        "1": {"name": "主播1", "room_id": 101},
                        "2": {"name": "主播2", "room_id": None},
                    }
                ),
            )
        )
        self.guard_counts = self.stack.enter_context(
            mock.patch.object(
                guards,
                "get_num_guards",
                new=mock.AsyncMock(
                    return_value={
                        "1": {
                            "num_guards": 3,
                            "guard_num_1": 0,
                            "guard_num_2": 0,
                            "guard_num_3": 3,
                        }
                    }
                ),
            )
        )
        self.fans = self.stack.enter_context(
            mock.patch.object(
                guards,
                "get_num_followers",
                new=mock.AsyncMock(
                    return_value={"1": {"num_followers": 20, "delta": 2}}
                ),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_name_from_uid",
                new=mock.AsyncMock(side_effect=lambda uid: f"主播{uid}"),
            )
        )
        self.last_session = self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_last_session_id",
                new=mock.AsyncMock(return_value=10),
            )
        )
        self.revenue_data = self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_session_revenue",
                new=mock.AsyncMock(
                    return_value={
                        "revenue": {
                            "guards": 10,
                            "gifts": 20,
                            "super_chats": 30,
                            "total": 60,
                        }
                    }
                ),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_session_info",
                new=mock.AsyncMock(
                    return_value={
                        "title": "测试直播",
                        "start_time": "2026-11-01T10:00:00",
                        "end_time": None,
                    }
                ),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_online_members",
                new=mock.AsyncMock(return_value={"max": 100, "avg": 50.5}),
            )
        )
        self.super_chats = self.stack.enter_context(
            mock.patch.object(
                revenue,
                "get_super_chats",
                new=mock.AsyncMock(
                    return_value=[
                        {
                            "user_name": "观众",
                            "message": "加油",
                            "record_time": "今天",
                            "price": 30,
                        }
                    ]
                ),
            )
        )
        self.stack.enter_context(
            mock.patch.object(
                revenue,
                "asyncio",
                types.SimpleNamespace(sleep=mock.AsyncMock()),
            )
        )

    async def run_command(
        self, content: str, scene: str = "group"
    ) -> list[str]:
        """Dispatches a fresh real SDK message and returns its emitted texts."""
        self.counter += 1
        self.api.post_group_message.reset_mock()
        self.api.post_message.reset_mock()
        if scene == "group":
            message = botpy_message.GroupMessage(
                self.api,
                "event",
                typing.cast(
                    gateway.MessagePayload,
                    {
                        "id": str(self.counter),
                        "content": content,
                        "group_openid": "group",
                        "author": {"member_openid": "member"},
                    },
                ),
            )
            await self.manager.execute_group(message)
            calls = self.api.post_group_message.await_args_list
            self.assertEqual(
                list(range(1, len(calls) + 1)),
                [call.kwargs["msg_seq"] for call in calls],
            )
            self.api.post_message.assert_not_awaited()
        else:
            guild_message = botpy_message.Message(
                self.api,
                "event",
                typing.cast(
                    gateway.MessagePayload,
                    {
                        "id": str(self.counter),
                        "content": content,
                        "guild_id": "guild",
                        "channel_id": "channel",
                        "author": {"id": "user", "username": "用户"},
                    },
                ),
            )
            await self.manager.execute_guild(
                guild_message, ["<@!1>", *content.split()]
            )
            calls = self.api.post_message.await_args_list
            self.api.post_group_message.assert_not_awaited()
        return [call.kwargs["content"] for call in calls]

    async def test_all_five_queries_match_channel_output_and_record_group_usage(
        self,
    ) -> None:
        for content in ("/营收 1", "/高能", "/粉丝", "/舰长", "/查SCv2 1"):
            with self.subTest(content=content):
                group = await self.run_command(content)
                guild = await self.run_command(content, "guild")
                self.assertEqual(guild, group)
        self.assertEqual(
            5,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_command_records WHERE succeeded = 1"
            ).fetchone()[0],
        )

    async def test_counts_progress_then_results_and_missing_data(self) -> None:
        messages = await self.run_command("/粉丝")
        self.assertEqual(2, len(messages))
        self.assertIn("正在查询", messages[0])
        self.assertIn("主播1: 20 (+2)", messages[1])
        self.assertIn("主播2: 获取失败", messages[1])
        messages = await self.run_command("/舰长")
        self.assertIn("主播2：暂无直播间", messages[-1])
        self.guard_counts.assert_awaited_with([1], [101])

    async def test_failed_counts_stop_chains_and_record_failure(self) -> None:
        self.fans.return_value = None
        messages = await self.run_command("/粉丝 && /高能")
        self.assertEqual(2, len(messages))
        self.assertIn("失败", messages[-1])
        self.on_live.assert_not_awaited()
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT succeeded FROM group_command_records"
            ).fetchone()[0],
        )

    async def test_timeout_has_friendly_reply_after_progress(self) -> None:
        self.guard_counts.side_effect = TimeoutError
        messages = await self.run_command("/舰长")
        self.assertIn("正在查询", messages[0])
        self.assertIn("查询超时", messages[-1])

    async def test_group_query_replies_share_sequence_with_next_command(
        self,
    ) -> None:
        messages = await self.run_command("/粉丝 && /time")
        self.assertEqual(3, len(messages))
        self.assertIn("北京时间", messages[-1])

    async def test_online_limits_all_empty_and_invalid_arguments(self) -> None:
        messages = await self.run_command("/高能 2")
        self.assertIn("top 2:", messages[0])
        self.assertIn("还有10位", messages[0])
        messages = await self.run_command("/同接 all")
        self.assertIn("top all:", messages[0])
        self.assertNotIn("已折叠", messages[0])
        self.on_live.return_value = []
        self.assertIn("无人开播", (await self.run_command("/gn"))[0])
        self.on_live.reset_mock()
        self.assertIn("参数错误", (await self.run_command("/高能 -1"))[0])
        self.on_live.assert_not_awaited()

    async def test_nickname_exact_and_fuzzy_resolution_and_limit(self) -> None:
        for uid in range(1, 8):
            self.dao.nicknames.add(uid, f"测试{uid}")
        messages = await self.run_command("/营收 测试1")
        self.assertIn("主播1的最近", messages[0])
        self.last_session.reset_mock()
        messages = await self.run_command("/营收 测试")
        self.assertEqual(5, self.last_session.await_count)
        self.assertIn("主播5的最近", messages[0])
        self.assertNotIn("主播6的最近", messages[0])

    async def test_revenue_empty_payload_and_no_sessions(self) -> None:
        self.revenue_data.return_value = None
        self.assertIn("数据失败", (await self.run_command("/营收 1"))[0])
        self.last_session.return_value = revenue.ErrorCode.NO_LIVE_SESSIONS
        self.assertIn("没有直播记录", (await self.run_command("/营收 1"))[0])

    async def test_invalid_uid_page_and_missing_args_do_not_query(self) -> None:
        for content in (
            "/营收",
            "/营收 uid:abc",
            "/营收 0",
            "/查SCv2",
            "/查SCv2 1 abc",
            "/查SCv2 uid:",
        ):
            with self.subTest(content=content):
                messages = await self.run_command(content)
                self.assertEqual(1, len(messages))
        self.last_session.assert_not_awaited()
        self.super_chats.assert_not_awaited()

    async def test_sc_pagination_negative_page_and_empty_page(self) -> None:
        await self.run_command("/查SCv2 1 2")
        self.super_chats.assert_awaited_with(1, 20, 30)
        self.super_chats.return_value = []
        messages = await self.run_command("/查SCv2 uid:1 -1")
        self.super_chats.assert_awaited_with(1, 0, 10)
        self.assertIn("暂无SC记录", messages[0])

    async def test_sc_keeps_results_from_every_matched_streamer(self) -> None:
        self.dao.nicknames.add(1, "模糊1")
        self.dao.nicknames.add(2, "模糊2")
        messages = await self.run_command("/查SCv2 模糊")
        self.assertIn("主播 主播1", messages[0])
        self.assertIn("主播 主播2", messages[0])

    async def test_group_long_sc_is_split_without_losing_content(self) -> None:
        self.super_chats.return_value[0]["message"] = "很长的内容" * 800
        group = await self.run_command("/查SCv2 1")
        guild = await self.run_command("/查SCv2 1", "guild")
        self.assertGreater(len(group), 1)
        self.assertTrue(
            all(len(chunk) <= text_query.GROUP_TEXT_CHARS for chunk in group)
        )
        self.assertEqual(guild[0], "".join(group))

    async def test_help_and_capabilities_do_not_expose_user_history_or_c2c(
        self,
    ) -> None:
        content = base.render_scene_help("group")
        for title in ("营收", "同接", "粉丝", "舰长", "查SCv2"):
            self.assertIn(title, content)
        self.assertNotIn("查用户SC", content)
        self.assertNotIn("查用户舰长", content)
        for alias in ("营收", "高能", "粉丝", "舰长", "查SCv2"):
            self.assertFalse(
                self.manager.commands[alias].supports_scene("user")
            )
        self.assertFalse(self.manager.commands["查SC"].supports_scene("group"))


if __name__ == "__main__":
    unittest.main()
