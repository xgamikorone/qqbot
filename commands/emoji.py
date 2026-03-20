import asyncio
import re
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging


_log = logging.get_logger()


@command("贴表情", "emoji")
class EmojiCommand(Command):

    name = "emoji"
    cn_name = "贴表情"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Emoji command received: {message.content}")
        if not args:
            _log.info("No emoji specified")
            return
        reactions: List[tuple[int, str]] = []
        for arg in args:
            # Extract <emoji:\d+> formats
            for match in re.finditer(r'<emoji:(\d+)>', arg):
                reactions.append((1, match.group(1)))
            # Remove matched parts
            arg = re.sub(r'<emoji:\d+>', '', arg)
            # Extract standalone digits
            for num in re.findall(r'\d+', arg):
                reactions.append((1, num))
            # Remove digits
            arg = re.sub(r'\d+', '', arg)
            # Remaining characters are assumed to be unicode emojis
            for char in arg.strip():
                if char and not char.isspace():  # Skip spaces and empty
                    reactions.append((2, str(ord(char))))
            _log.info(f"Parsed arg: {arg}")
        if message.message_reference.message_id is not None:
            message_id = message.message_reference.message_id
        else:
            message_id = message.id
        for emoji_type, emoji_id in reactions:
            await self.client.api.put_reaction(
                channel_id=message.channel_id,
                message_id=message_id,
                emoji_type=emoji_type,
                emoji_id=emoji_id,
            )
            # sleep for 1 second to avoid rate limiting
            await asyncio.sleep(1)
