"""Shared image query execution with scene-specific native transports."""

import collections.abc
import asyncio
import threading
import time
import typing

from botpy import message as botpy_message

from . import base
from . import text_query

ImageSender = collections.abc.Callable[[str], collections.abc.Awaitable[None]]
_PARAMS = typing.ParamSpec("_PARAMS")
_DRAW_LOCK = threading.Lock()


async def render_chart(draw: collections.abc.Callable[_PARAMS, str], *args:
                       _PARAMS.args, **kwargs: _PARAMS.kwargs) -> str:
    """Serializes matplotlib work off the event loop across both charts."""

    def render() -> str:
        with _DRAW_LOCK:
            return draw(*args, **kwargs)

    return await asyncio.to_thread(render)


class ImageQueryCommand(base.Command):
    """Runs chart queries without converting original SDK messages."""

    supported_scenes = frozenset({"guild", "group"})
    cooldown_seconds = 0

    async def query_and_reply(self, args: list[str],
                              reply: text_query.TextSender,
                              send_image: ImageSender) -> bool:
        """Generates a chart, awaits its send, and cleans up its own files."""
        raise NotImplementedError

    async def execute(self, message: botpy_message.Message,
                      args: list[str]) -> bool:
        """Preserves legacy direct channel callers."""
        return await self.execute_guild(message, args)

    async def execute_guild(self, message: botpy_message.Message,
                            args: list[str]) -> bool:
        """Sends local files with the existing channel multipart transport."""

        async def reply(content: str) -> None:
            await self.send_reply(message, content)

        async def send_image(path: str) -> None:
            await self.client.api.post_message(channel_id=message.channel_id,
                                               file_image=path,
                                               msg_id=message.id)

        return await self._run(args, reply, send_image)

    async def execute_group(self, message: botpy_message.GroupMessage,
                            args: list[str]) -> bool:
        """Uses QQ multipart upload and the shared event reply sequence."""

        async def reply(content: str) -> None:
            for chunk in text_query.split_group_text(content):
                await self.reply_group(message, chunk)

        async def send_image(path: str) -> None:
            await self.reply_group_local_image(message, path)

        return await self._run(args, reply, send_image)

    async def _run(self, args: list[str], reply: text_query.TextSender,
                   send_image: ImageSender) -> bool:
        # Retain global per-command cooldown, including aliases and scenes.
        if self.name in base._running_commands:
            await reply("命令正在执行，请稍后再试")
            return False
        previous = base.last_used.get(self.name)
        remaining = self.cooldown_seconds - (
            time.monotonic() - previous) if previous is not None else 0
        if remaining > 0:
            await reply(f"命令冷却中，还需等待 {remaining:.1f} 秒")
            return False
        base._running_commands.add(self.name)
        try:
            try:
                succeeded = await self.query_and_reply(args, reply, send_image)
            except TimeoutError:
                await reply("查询超时，请稍后再试。")
                return False
            if succeeded:
                base.last_used[self.name] = time.monotonic()
            return succeeded
        finally:
            base._running_commands.discard(self.name)
