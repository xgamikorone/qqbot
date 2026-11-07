"""Example command sharing business logic across three original SDK events."""

import random
import textwrap

from botpy import message as botpy_message

from . import base
from . import help_catalog

with open("answer_book", encoding="utf-8") as answer_file:
    answers = [line.split()[1].strip() for line in answer_file if line.strip()]


@base.command("answer_book", "答案之书")
class AnswerBookCommand(base.Command):
    """Keeps SDK-specific presentation in small, explicitly typed entry points."""

    supported_scenes = frozenset({"guild", "group", "user"})
    name = "answer_book"
    cn_name = "答案之书"

    def build_answer(self, args: list[str]) -> str:
        """Builds the shared answer body, without transport or identity logic."""
        return (
            f"你的问题: {' '.join(args)}\n\n"
            f"答案之书的回答:\n{random.choice(answers)}"
        )

    async def execute_guild(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        """Uses the original channel author for the guild mention format."""
        if not args:
            await self.reply_guild(message, "你的问题呢？")
            return False
        await self.reply_guild(
            message, f"<@!{message.author.id}>\n{self.build_answer(args)}"
        )
        return True

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> bool:
        """Receives the full GroupMessage; no channel fields are fabricated."""
        if not args:
            await self.reply_group(message, "你的问题呢？")
            return False
        await self.reply_group(message, self.build_answer(args))
        return True

    async def execute_user(
        self, message: botpy_message.C2CMessage, args: list[str]
    ) -> bool:
        """Uses the same answer logic in C2C without leaking channel mentions."""
        if not args:
            await self.reply_user(message, "你的问题呢？")
            return False
        await self.reply_user(message, self.build_answer(args))
        return True


answer_book_help_str = textwrap.dedent("""\
    /答案之书 [问题] 向答案之书提问，获取回答。
    例子: /答案之书 我今天会中奖吗？

    说明：答案之书的回答仅供参考，请不要盲目相信。
    """)


@base.command("answer_book_help", "答案之书帮助")
class AnswerBookHelpCommand(base.Command):
    supported_scenes = frozenset({"guild", "group", "user"})
    name = "answer_book_help"
    cn_name = "答案之书帮助"
    help = help_catalog.CommandHelp(
        title="答案之书",
        category="娱乐",
        summary="向答案之书提问",
        details=answer_book_help_str,
        lookup_names=("答案之书", "answer_book"),
    )

    async def execute_guild(
        self, message: botpy_message.Message, args: list[str]
    ) -> None:
        """Sends channel help."""
        await self.reply_guild(message, answer_book_help_str)

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> None:
        """Sends group help."""
        await self.reply_group(message, answer_book_help_str)

    async def execute_user(
        self, message: botpy_message.C2CMessage, args: list[str]
    ) -> None:
        """Sends C2C help."""
        await self.reply_user(message, answer_book_help_str)
