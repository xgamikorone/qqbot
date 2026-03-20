from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging

_log = logging.get_logger()

@command("复读", "repeat", "echo")
class RepeatCommand(Command):
    name = "repeat"
    cn_name = "复读"
    
    async def execute(self, message: Message, args: List[str]):
        user_name = message.author.username
        reply_content = f"{user_name}: {' '.join(args)}"
        _log.info(f"回复内容: {reply_content}")
        if message.attachments:
            attachment = message.attachments[0]
            _log.info(f"附件: {attachment.url}")
            url = attachment.url
            if not url.startswith("https"):
                url = f"https://{url}"
            try:
                await self.client.api.post_message(
                    message.channel_id,
                    content=reply_content,
                    image=url,
                    msg_id=message.id
                )
            except Exception as e:
                _log.error(f"发送失败: {e}")
                await self.send_reply(message, reply_content)
        else:
            await self.send_reply(message, reply_content)
            

