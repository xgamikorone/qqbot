"""Shared query logic with original SDK messages at each transport entry."""

import collections.abc

from botpy import message as botpy_message

from . import base

TextSender = collections.abc.Callable[[str], collections.abc.Awaitable[None]]

# Application chunk size, not a promise about the platform's reply quota.
GROUP_TEXT_CHARS = 1500


def split_group_text(content: str) -> list[str]:
    """Splits on line boundaries when possible, preserving all characters."""
    chunks: list[str] = []
    while len(content) > GROUP_TEXT_CHARS:
        newline = content.rfind("\n", 0, GROUP_TEXT_CHARS)
        end = newline + 1 if newline >= 0 else GROUP_TEXT_CHARS
        chunks.append(content[:end])
        content = content[end:]
    if content:
        chunks.append(content)
    return chunks


class TextQueryCommand(base.Command):
    """Reuses queries without passing guild-shaped messages into group code."""

    supported_scenes = frozenset({"guild", "group"})

    async def query_and_reply(self, args: list[str], reply: TextSender) -> bool:
        """Queries and renders data; subclasses need no SDK message fields."""
        raise NotImplementedError

    async def execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        """Retains compatibility with direct callers of old channel commands."""
        return await self.execute_guild(message, args)

    async def execute_guild(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        """Preserves channel reply behavior and existing send_reply overrides."""

        async def reply(content: str) -> None:
            await self.send_reply(message, content)

        return await self._run_query(args, reply)

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> bool:
        """Shares progress/result/chunk sequences through the event sender."""

        async def reply(content: str) -> None:
            for chunk in split_group_text(content):
                await self.reply_group(message, chunk)

        return await self._run_query(args, reply)

    async def _run_query(self, args: list[str], reply: TextSender) -> bool:
        try:
            return await self.query_and_reply(args, reply)
        except TimeoutError:
            await reply("查询超时，请稍后再试。")
            return False
