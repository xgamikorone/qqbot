"""Group chat entry, scoping, quota and transport behaviour."""

import asyncio
import json
import sqlite3
import tempfile
import typing
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from botpy import message as botpy_message
from botpy.types import gateway

from chat.config import ChatConfig, load_config
from chat.model_client import GenerationResult
from chat.service import ChatService
from commands import chat as chat_commands
from commands.chat import ChatCommand
from database.repositories.chat_repository import (
    ChatRepository,
    group_session_key,
    session_key,
)
from database.schema import initialize_schema
from messaging import command_replies


def group_payload(
    member: str = "M1", group: str = "G1"
) -> gateway.MessagePayload:
    """Builds the original SDK payload for one group event."""
    return typing.cast(
        gateway.MessagePayload,
        {
            "id": "msg-1",
            "content": "/聊天 你好",
            "group_openid": group,
            "author": {"member_openid": member},
        },
    )


class GroupChatCommandTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the real service with a fake QQ transport."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        initialize_schema(self.conn)
        self.repo = ChatRepository(self.conn)
        self.model = mock.Mock(
            generate=mock.AsyncMock(
                return_value=GenerationResult("回答", "fake")
            ),
            close=mock.AsyncMock(),
        )
        self.config = replace(
            ChatConfig(),
            enabled=True,
            allowed_channel_ids=("123",),
            allowed_group_ids=("G1", "G2"),
        )
        self.service = ChatService(self.config, self.repo, self.model)
        self.api = mock.Mock()
        self.api.post_group_message = mock.AsyncMock(
            return_value={"id": "sent"}
        )
        self.api.post_message = mock.AsyncMock(return_value={"id": "sent"})
        self.client = mock.Mock(chat_service=self.service, api=self.api)
        self.command = ChatCommand(self.client)

    async def asyncTearDown(self) -> None:
        await self.service.close()
        self.conn.close()

    async def run_group(
        self,
        args: list[str] | None = None,
        member: str = "M1",
        group: str = "G1",
    ) -> bool:
        """Sends one event through the command under a reply scope."""
        message = botpy_message.GroupMessage(
            self.api, "event", group_payload(member, group)
        )
        with command_replies.reply_scope(message):
            # The registry decorator widens the class type to Command, whose
            # execute_group is annotated bool | None.
            return bool(
                await self.command.execute_group(message, args or ["你好"])
            )

    async def test_group_reply_uses_event_identity_and_sequence(self) -> None:
        self.assertTrue(await self.run_group())
        call = self.api.post_group_message.await_args
        self.assertEqual("G1", call.kwargs["group_openid"])
        self.assertEqual("msg-1", call.kwargs["msg_id"])
        self.assertEqual(1, call.kwargs["msg_seq"])
        self.assertEqual("回答", call.kwargs["content"])
        self.assertEqual(
            [("你好", "回答")],
            self.repo.history(group_session_key("G1", "M1"), 7),
        )

    async def test_members_and_groups_keep_separate_contexts(self) -> None:
        await self.run_group(member="M1")
        await self.run_group(member="M2")
        await self.run_group(member="M1", group="G2")
        keys = [
            group_session_key("G1", "M1"),
            group_session_key("G1", "M2"),
            group_session_key("G2", "M1"),
        ]
        for key in keys:
            self.assertEqual([("你好", "回答")], self.repo.history(key, 7))
        # The second turn of one member only sees that member's history.
        self.assertEqual(3, self.model.generate.await_count)
        self.assertEqual(2, len(self.model.generate.await_args.args[0]))

    async def test_unsupported_group_is_rejected_without_model_call(
        self,
    ) -> None:
        self.assertFalse(await self.run_group(group="G3"))
        self.model.generate.assert_not_awaited()
        reply = self.api.post_group_message.await_args.kwargs["content"]
        self.assertIn("尚未开放", reply)

    async def test_long_answer_is_split_with_increasing_sequences(self) -> None:
        self.model.generate.return_value = GenerationResult("x" * 3500, "fake")
        self.assertTrue(await self.run_group(args=["长"]))
        calls = self.api.post_group_message.await_args_list
        self.assertEqual([1, 2, 3], [call.kwargs["msg_seq"] for call in calls])
        self.assertEqual(
            [1500, 1500, 500], [len(call.kwargs["content"]) for call in calls]
        )
        self.assertEqual(
            [("长", "x" * 3500)],
            self.repo.history(group_session_key("G1", "M1"), 7),
        )

    async def test_send_failure_keeps_quota_but_not_context(self) -> None:
        # The failing send is the answer; the error notice still reaches QQ.
        self.api.post_group_message.side_effect = [
            RuntimeError("private"),
            {"id": "sent"},
        ]
        self.assertFalse(await self.run_group())
        self.assertEqual(
            [], self.repo.history(group_session_key("G1", "M1"), 7)
        )
        self.assertIn(
            "未能发送", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) FROM chat_requests").fetchone()[
                0
            ],
        )

    async def test_unconfirmed_chunk_stops_remaining_answer_and_history(
        self,
    ) -> None:
        self.model.generate.return_value = GenerationResult("x" * 3500, "fake")
        key = group_session_key("G1", "M1")
        for failed_index in (0, 1):
            for response in (None, {}, {"code": 304023}, {"code": 304024}):
                with self.subTest(index=failed_index, response=response):
                    self.api.post_group_message.reset_mock()
                    self.api.post_group_message.side_effect = [
                        {"id": "sent"}
                    ] * failed_index + [response, {"id": "error-notice"}]
                    await self.run_group()
                    answer_calls = [
                        call
                        for call in self.api.post_group_message.await_args_list
                        if call.kwargs["content"].startswith("x")
                    ]
                    self.assertEqual(failed_index + 1, len(answer_calls))
                    self.assertEqual([], self.repo.history(key, 7))
                    expected = (
                        "pending"
                        if response and response.get("code")
                        else "unknown"
                    )
                    self.assertEqual(
                        expected, self.repo.list_deliveries()[0]["status"]
                    )

    async def test_group_prompt_overflow_does_not_use_model_or_quota(
        self,
    ) -> None:
        self.service.config = replace(
            self.config, max_context_chars=len(self.config.prompt) + 2000
        )
        self.assertFalse(await self.run_group(args=["x" * 2000]))
        self.model.generate.assert_not_awaited()
        self.assertEqual(
            0,
            self.conn.execute("SELECT COUNT(*) FROM chat_requests").fetchone()[
                0
            ],
        )
        self.assertEqual({}, self.service.tasks)
        self.assertIn(
            "上下文长度",
            self.api.post_group_message.await_args.kwargs["content"],
        )

    async def test_exact_group_budget_discards_history_but_keeps_input(
        self,
    ) -> None:
        await self.run_group()
        self.model.generate.reset_mock()
        text = "刚好容纳的输入"
        cap = len(
            self.config.prompt + "\n\n" + chat_commands.GROUP_PROMPT_SUFFIX
        ) + len(text)
        self.service.config = replace(self.config, max_context_chars=cap)
        self.assertTrue(await self.run_group(args=[text]))
        messages = self.model.generate.await_args.args[0]
        self.assertEqual(
            ["system", "user"], [item["role"] for item in messages]
        )
        self.assertEqual(text, messages[-1]["content"])
        self.assertEqual(cap, sum(len(item["content"]) for item in messages))

    async def test_audit_response_is_not_used_as_context(self) -> None:
        self.api.post_group_message.return_value = {"code": 304023}
        self.assertTrue(await self.run_group())
        self.assertEqual(
            [], self.repo.history(group_session_key("G1", "M1"), 7)
        )

    async def test_reset_only_clears_the_requesting_member(self) -> None:
        await self.run_group(member="M1")
        await self.run_group(member="M2")
        self.assertTrue(await self.run_group(args=["/reset"], member="M1"))
        self.assertEqual(
            [], self.repo.history(group_session_key("G1", "M1"), 7)
        )
        self.assertEqual(
            [("你好", "回答")],
            self.repo.history(group_session_key("G1", "M2"), 7),
        )

    async def test_group_quota_is_separate_from_channel_quota(self) -> None:
        self.service.config = replace(self.config, daily_requests_per_user=1)
        self.assertTrue(await self.run_group())
        self.assertFalse(await self.run_group())
        reply = self.api.post_group_message.await_args.kwargs["content"]
        self.assertIn("额度已用完", reply)

        message = botpy_message.Message(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": "ch-1",
                    "channel_id": "123",
                    "guild_id": "g",
                    "author": {"id": "u"},
                },
            ),
        )
        self.assertTrue(await self.command.execute_guild(message, ["你好"]))
        self.api.post_message.assert_awaited_once()

    async def test_group_prompt_suffix_is_appended(self) -> None:
        await self.run_group()
        system = self.model.generate.await_args.args[0][0]["content"]
        self.assertIn(self.config.prompt, system)
        self.assertIn("QQ 群聊", system)
        self.assertIn("500 字以内", system)

    async def test_persona_is_scoped_and_survives_conversation_reset(
        self,
    ) -> None:
        preference = "语气冷静，少用表情"
        self.assertTrue(await self.run_group(["人格", "设置", preference]))
        self.assertTrue(await self.run_group(["人格", "查看"]))
        self.assertIn(
            preference, self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertTrue(await self.run_group(["人格", "查看"], member="M2"))
        self.assertIn(
            "默认人格", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertTrue(await self.run_group(["人格", "查看"], group="G2"))
        self.assertIn(
            "默认人格", self.api.post_group_message.await_args.kwargs["content"]
        )
        self.assertTrue(await self.run_group(["/reset"]))
        self.model.generate.assert_not_awaited()
        self.assertEqual(
            0,
            self.conn.execute("SELECT COUNT(*) FROM chat_requests").fetchone()[
                0
            ],
        )

        self.assertTrue(await self.run_group(["问题"]))
        messages = self.model.generate.await_args.args[0]
        self.assertNotIn(preference, messages[0]["content"])
        self.assertIn("QQ 群聊", messages[0]["content"])
        self.assertEqual(
            {"style_preference": preference, "question": "问题"},
            json.loads(messages[-1]["content"]),
        )
        self.assertTrue(await self.run_group(["人格", "清除"]))
        self.assertEqual(
            [("问题", "回答")],
            self.repo.history(group_session_key("G1", "M1"), 7),
        )
        self.assertTrue(await self.run_group(["继续"]))
        self.assertEqual(
            "继续", self.model.generate.await_args.args[0][-1]["content"]
        )

    async def test_persona_counts_against_input_budget_before_quota(
        self,
    ) -> None:
        self.assertFalse(await self.run_group(["人格", "设置", "嗨" * 501]))
        self.assertTrue(await self.run_group(["人格", "设置", "嗨" * 500]))
        plain_chars = len(
            self.config.prompt + "\n\n" + chat_commands.GROUP_PROMPT_SUFFIX
        )
        self.service.config = replace(
            self.config, max_context_chars=plain_chars + 10
        )
        self.assertFalse(await self.run_group(["问题"]))
        self.model.generate.assert_not_awaited()
        self.assertEqual(
            0,
            self.conn.execute("SELECT COUNT(*) FROM chat_requests").fetchone()[
                0
            ],
        )

    async def test_persona_change_discards_old_answer_if_model_ignores_cancel(
        self,
    ) -> None:
        started = asyncio.Event()

        async def generate(messages: list[dict[str, str]]) -> GenerationResult:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return GenerationResult("过时回答", "fake")
            return GenerationResult("过时回答", "fake")

        self.model.generate.side_effect = generate
        running = asyncio.create_task(self.run_group(["问题"]))
        await started.wait()
        self.assertTrue(await self.run_group(["人格", "设置", "严肃"]))
        self.assertFalse(await running)
        self.assertEqual(
            [], self.repo.history(group_session_key("G1", "M1"), 7)
        )
        self.assertNotIn(
            "过时回答",
            [
                call.kwargs["content"]
                for call in self.api.post_group_message.await_args_list
            ],
        )

    async def test_guild_path_keeps_plain_prompt(self) -> None:
        message = botpy_message.Message(
            self.api,
            "event",
            typing.cast(
                gateway.MessagePayload,
                {
                    "id": "ch-1",
                    "channel_id": "123",
                    "guild_id": "g",
                    "author": {"id": "u"},
                },
            ),
        )
        self.assertTrue(await self.command.execute_guild(message, ["你好"]))
        system = self.model.generate.await_args.args[0][0]["content"]
        self.assertEqual(self.config.prompt, system)
        self.assertEqual(
            [("你好", "回答")],
            self.repo.history(session_key("g", "123", "u"), 7),
        )

    async def test_stop_returns_without_waiting_for_generation(self) -> None:
        started = asyncio.Event()

        async def generate(messages):
            started.set()
            await asyncio.Event().wait()

        self.model.generate.side_effect = generate
        message = botpy_message.GroupMessage(self.api, "event", group_payload())
        with command_replies.reply_scope(message):
            running = asyncio.create_task(
                self.command.execute_group(message, ["你好"])
            )
            await started.wait()
            self.assertTrue(
                await self.command.execute_group(message, ["/stop"])
            )
            self.assertFalse(await running)


class GroupChatConfigTests(unittest.TestCase):
    """Validates the new group allowlist without touching real config."""

    def write(self, directory: str, body: str) -> Path:
        path = Path(directory) / "chat.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_accepts_opaque_group_openids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory, 'enabled: true\nallowed_group_ids: ["G1", "a-b_9"]\n'
            )
            self.assertEqual(
                ("G1", "a-b_9"), load_config(path).allowed_group_ids
            )

    def test_empty_default_keeps_groups_closed(self) -> None:
        self.assertEqual((), load_config().allowed_group_ids)

    def test_rejects_malformed_group_lists(self) -> None:
        bodies = (
            'allowed_group_ids: "G1"\n',
            'allowed_group_ids: [""]\n',
            'allowed_group_ids: ["G1", "G1"]\n',
            "allowed_group_ids: [1]\n",
            'allowed_group_ids: ["has space"]\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            for body in bodies:
                with self.subTest(body=body):
                    path = self.write(directory, body)
                    with self.assertRaises(ValueError):
                        load_config(path)


if __name__ == "__main__":
    unittest.main()
