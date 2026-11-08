"""Repeat text and the first image attachment in channels and groups."""

import urllib.parse
import collections.abc

from botpy import message as botpy_message

from messaging import command_replies
from . import base
from . import help_catalog


def image_url(attachments: collections.abc.Sequence[object]) -> str | None:
    """Extracts only image attachments and normalizes SDK URL variants."""
    if not attachments:
        return None
    attachment = attachments[0]
    content_type = getattr(attachment, "content_type", None)
    if not isinstance(content_type,
                      str) or not content_type.startswith("image/"):
        return None
    url = getattr(attachment, "url", None)
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return url


@base.command("复读", "repeat", "echo")
class RepeatCommand(base.Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "repeat"
    cn_name = "复读"
    help = help_catalog.CommandHelp(
        title="复读",
        category="工具",
        summary="复读文字及第一张图片附件",
        usage="/复读 <文字> [图片附件]",
        examples=("/复读 你好",),
    )

    async def execute(self, message: botpy_message.Message,
                      args: list[str]) -> bool:
        """Preserves the legacy channel entry point."""
        return await self.execute_guild(message, args)

    async def execute_guild(self, message: botpy_message.Message,
                            args: list[str]) -> bool:
        """Keeps the channel author prefix and native image URL transport."""
        content = f"{message.author.username}: {' '.join(args)}"
        url = image_url(message.attachments)
        if url:
            await self.client.api.post_message(channel_id=message.channel_id,
                                               content=content,
                                               image=url,
                                               msg_id=message.id)
        else:
            await self.reply_guild(message, content)
        return True

    async def execute_group(self, message: botpy_message.GroupMessage,
                            args: list[str]) -> bool:
        """Uses available display names without printing member OpenIDs."""
        name = await self.group_display_name(message)
        content = f"{name or '一位朋友'}: {' '.join(args)}"
        url = image_url(message.attachments)
        if not url:
            await self.reply_group(message, content)
            return True
        try:
            await self.reply_group_image(message, content, url)
        except command_replies.GroupImageUploadError:
            await self.reply_group(message, content + "\n图片暂时无法加载。")
        return True
