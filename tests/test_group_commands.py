"""Offline contracts for original SDK event dispatch and scene isolation."""

import asyncio
import typing
import unittest
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

import dao
from commands import base
from commands import manager
from messaging import command_replies


class SceneCommandTests(unittest.IsolatedAsyncioTestCase):
    """Exercises real registered commands using memory storage and fake APIs."""

    def setUp(self) -> None:
        self.dao = dao.Dao(":memory:")
        self.dao_patch = mock.patch.object(dao, "_dao_instance", self.dao)
        self.dao_patch.start()
        self.addCleanup(self.dao.close)
        self.addCleanup(self.dao_patch.stop)
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock()
        self.api.post_c2c_message = mock.AsyncMock()
        self.api.post_message = mock.AsyncMock()
        self.manager = manager.CommandManager(mock.Mock(api=self.api))

    def group_message(
        self, content: str, group: str = "group-a", message_id: str = "trigger"
    ) -> botpy_message.GroupMessage:
        """Builds a real SDK event; its payload stub omits group author fields."""
        return botpy_message.GroupMessage(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": message_id,
                    "content": content,
                    "group_openid": group,
                    "author": {"member_openid": "member-a"},
                },
            ),
        )

    def user_message(self, content: str) -> botpy_message.C2CMessage:
        """Builds C2C, not the unrelated channel DirectMessage type."""
        return botpy_message.C2CMessage(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": "trigger",
                    "content": content,
                    "author": {"user_openid": "user-a"},
                },
            ),
        )

    def guild_message(self, content: str) -> botpy_message.Message:
        """Keeps guild and channel fields available to commands and hooks."""
        return botpy_message.Message(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": "guild-message",
                    "content": content,
                    "guild_id": "guild",
                    "channel_id": "channel",
                    "author": {"id": "guild-user", "username": "昵称"},
                    "member": {"roles": ["1"]},
                },
            ),
        )

    async def test_group_chain_shared_sequence_and_separate_records(
        self,
    ) -> None:
        await self.manager.execute_group(
            self.group_message("/time && /答案之书 今天会开心吗")
        )
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertTrue(
            all(call.kwargs["msg_id"] == "trigger" for call in calls)
        )
        self.assertNotIn("<@!", calls[1].kwargs["content"])
        self.api.post_message.assert_not_awaited()
        self.assertEqual(
            2,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_command_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM command_records"
            ).fetchone()[0],
        )

    async def test_original_group_object_reaches_command_and_hook(self) -> None:
        message = self.group_message("/答案之书 测试")
        command = self.manager.commands["答案之书"]
        with mock.patch.object(
            command, "execute_group", wraps=command.execute_group
        ) as run:
            with mock.patch.object(
                command,
                "after_execute_group",
                wraps=command.after_execute_group,
            ) as hook:
                await self.manager.execute_group(message)
        assert run.await_args is not None
        assert hook.await_args is not None
        self.assertIs(message, run.await_args.args[0])
        self.assertIs(message, hook.await_args.args[0])

    async def test_guild_fields_and_mention_are_preserved(self) -> None:
        message = self.guild_message("<@!bot> /答案之书 测试")
        command = self.manager.commands["答案之书"]
        with mock.patch.object(
            command, "execute_guild", wraps=command.execute_guild
        ) as run:
            await self.manager.execute_guild(message, message.content.split())
        assert run.await_args is not None
        self.assertIs(message, run.await_args.args[0])
        self.assertIn(
            "<@!guild-user>", self.api.post_message.await_args.kwargs["content"]
        )
        row = self.dao.conn.execute("SELECT * FROM command_records").fetchone()
        self.assertEqual("guild", row["guild_id"])
        self.assertEqual("channel", row["channel_id"])
        self.assertEqual("guild-user", row["user_id"])
        self.assertEqual("昵称", row["user_name"])

    async def test_legacy_execute_and_after_execute_still_work(self) -> None:
        command = self.manager.commands["time"]
        message = self.guild_message("<@!bot> /time")
        with mock.patch.object(
            command, "execute", wraps=command.execute
        ) as run:
            with mock.patch.object(
                command, "after_execute", wraps=command.after_execute
            ) as hook:
                await self.manager.execute(message, message.content.split())
        assert run.await_args is not None
        assert hook.await_args is not None
        self.assertIs(message, run.await_args.args[0])
        self.assertIs(message, hook.await_args.args[0])

    async def test_c2c_uses_original_object_and_private_metadata_table(
        self,
    ) -> None:
        message = self.user_message("/答案之书 私密问题 && /答案之书帮助")
        command = self.manager.commands["答案之书"]
        with mock.patch.object(
            command, "execute_user", wraps=command.execute_user
        ) as run:
            await self.manager.execute_user(message)
        assert run.await_args is not None
        self.assertIs(message, run.await_args.args[0])
        calls = self.api.post_c2c_message.await_args_list
        self.assertEqual([1, 2], [call.kwargs["msg_seq"] for call in calls])
        self.assertEqual("user-a", calls[0].kwargs["openid"])
        self.assertNotIn("<@!", calls[0].kwargs["content"])
        self.assertEqual(
            2,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM c2c_command_records"
            ).fetchone()[0],
        )
        columns = {
            row[1]
            for row in self.dao.conn.execute(
                "PRAGMA table_info(c2c_command_records)"
            )
        }
        self.assertNotIn("content", columns)
        self.assertNotIn("command_args", columns)
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_members"
            ).fetchone()[0],
        )

    async def test_unsupported_and_owner_commands_are_not_executed(
        self,
    ) -> None:
        await self.manager.execute_group(self.group_message("/开创"))
        command = self.manager.commands["time"]
        with mock.patch.object(command, "owner_only", True):
            with mock.patch.object(command, "execute_group") as run:
                await self.manager.execute_group(self.group_message("/time"))
                run.assert_not_awaited()
        self.assertIn(
            "作者本人", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_command_records"
            ).fetchone()[0],
        )

    def test_declaration_without_implementation_does_not_enable_scene(
        self,
    ) -> None:
        class UnimplementedCommand(base.Command):
            supported_scenes = frozenset({"guild", "group", "user"})

        self.assertFalse(UnimplementedCommand.supports_scene("guild"))
        self.assertFalse(UnimplementedCommand.supports_scene("group"))
        self.assertFalse(UnimplementedCommand.supports_scene("user"))

    async def test_help_filters_by_scene(self) -> None:
        await self.manager.execute_group(self.group_message("/帮助"))
        content = self.api.post_group_message.await_args.kwargs["content"]
        self.assertIn("答案之书", content)
        self.assertIn("当前时间", content)
        self.assertNotIn("/聊天", content)
        await self.manager.execute_user(self.user_message("/帮助"))
        content = self.api.post_c2c_message.await_args.kwargs["content"]
        self.assertIn("答案之书", content)
        self.assertNotIn("当前时间", content)

    async def test_empty_unknown_and_invalid_chain(self) -> None:
        for content in ("", "/不存在", "/time &&"):
            await self.manager.execute_group(self.group_message(content))
        self.assertEqual(4, self.api.post_group_message.await_count)

    async def test_false_return_stops_chain_and_records_failure(self) -> None:
        await self.manager.execute_group(
            self.group_message("/答案之书 && /time")
        )
        self.assertEqual(1, self.api.post_group_message.await_count)
        row = self.dao.conn.execute(
            "SELECT succeeded FROM group_command_records"
        ).fetchone()
        self.assertEqual(0, row[0])

    async def test_exception_stops_chain_and_records_failure(self) -> None:
        command = self.manager.commands["time"]
        with mock.patch.object(
            command, "execute_group", side_effect=RuntimeError
        ):
            await self.manager.execute_group(
                self.group_message("/time && /time")
            )
        self.assertEqual(1, self.api.post_group_message.await_count)
        self.assertEqual(
            0,
            self.dao.conn.execute(
                "SELECT succeeded FROM group_command_records"
            ).fetchone()[0],
        )

    async def test_groups_and_duplicate_usage_are_isolated(self) -> None:
        for group in ("group-a", "group-a", "group-b"):
            await self.manager.execute_group(self.group_message("/time", group))
        self.assertEqual(
            2,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_members"
            ).fetchone()[0],
        )
        self.assertEqual(
            2,
            self.dao.conn.execute(
                "SELECT COUNT(*) FROM group_command_records"
            ).fetchone()[0],
        )

    async def test_failed_send_consumes_sequence(self) -> None:
        message = self.group_message("/time")
        command = self.manager.commands["time"]
        self.api.post_group_message.side_effect = [RuntimeError(), None]
        with command_replies.reply_scope(message):
            with self.assertRaises(RuntimeError):
                await command.reply_group(message, "first")
            await command.reply_group(message, "second")
        self.assertEqual(
            [1, 2],
            [
                call.kwargs["msg_seq"]
                for call in self.api.post_group_message.await_args_list
            ],
        )

    async def test_concurrent_events_do_not_share_sequences(self) -> None:
        async def send(message: botpy_message.GroupMessage) -> None:
            with command_replies.reply_scope(message):
                self.assertEqual(1, command_replies.next_sequence(message))
                await asyncio.sleep(0)
                self.assertEqual(2, command_replies.next_sequence(message))

        await asyncio.gather(
            send(self.group_message("", message_id="one")),
            send(self.group_message("", message_id="two")),
        )
        with self.assertRaises(RuntimeError):
            command_replies.next_sequence(self.group_message(""))

    async def test_missing_identity_is_rejected_before_sending(self) -> None:
        message = self.group_message("/time")
        message.author.member_openid = None
        self.assertFalse(await self.manager.execute_group(message))
        self.api.post_group_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
