import random
from commands.utils import is_admin
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from botpy.types.channel import ChannelType, ChannelSubType
from typing import List
from textwrap import dedent

@command("create")
class CreateCommand(Command):
    name = "create"
    cn_name = "创建"
    async def execute(self, message: Message, args: List[str]):
        guild_id = message.guild_id
        name = args[0]

        await self.client.api.create_channel(
            guild_id,
            name,
            type=ChannelType.TEXT_CHANNEL,
            sub_type=ChannelSubType.TALK
        )
