import re
from typing import List

from botpy.message import Message

from dao import get_dao
from .base import Command, command


def _parse_user_id(value: str) -> str | None:
    match = re.fullmatch(r"<@!?(\d+)>", value)
    if match:
        return match.group(1)
    if value.isdigit():
        return value
    return None


def _get_target_user_id(message: Message, args: List[str]) -> str | None:
    mentions = getattr(message, "mentions", None) or []
    users = [user for user in mentions if not getattr(user, "bot", False)]
    if users:
        return str(users[0].id)

    if args:
        return _parse_user_id(args[0])

    return None


def _mention_user(user_id: str) -> str:
    return f"<@!{user_id}>"


async def _is_user_in_current_guild(command: Command, message: Message, user_id: str) -> bool:
    try:
        await command.client.api.get_guild_member(message.guild_id, user_id)
        return True
    except Exception:
        return False


@command("添加作者", "add_owner")
class AddOwnerCommand(Command):
    name = "add_owner"
    cn_name = "添加作者"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        user_id = _get_target_user_id(message, args)
        if not user_id:
            await self.send_reply(message, "用法：/添加作者 @用户 [备注]")
            return

        if not await _is_user_in_current_guild(self, message, user_id):
            await self.send_reply(message, f"该用户不在当前频道：{_mention_user(user_id)}")
            return

        note = " ".join(args[1:])
        if get_dao().add_bot_owner(user_id, note):
            await self.send_reply(message, f"已添加作者：{_mention_user(user_id)}")
        else:
            await self.send_reply(message, f"添加作者失败：{_mention_user(user_id)}")


@command("删除作者", "remove_owner")
class RemoveOwnerCommand(Command):
    name = "remove_owner"
    cn_name = "删除作者"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        user_id = _get_target_user_id(message, args)
        if not user_id:
            await self.send_reply(message, "用法：/删除作者 @用户")
            return

        if not await _is_user_in_current_guild(self, message, user_id):
            await self.send_reply(message, f"该用户不在当前频道：{_mention_user(user_id)}")
            return

        if get_dao().remove_bot_owner(user_id):
            await self.send_reply(message, f"已删除作者：{_mention_user(user_id)}")
        else:
            await self.send_reply(message, f"未找到作者：{_mention_user(user_id)}")


@command("作者列表", "list_owners")
class ListOwnersCommand(Command):
    name = "list_owners"
    cn_name = "作者列表"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        owners = get_dao().get_bot_owners()
        if not owners:
            await self.send_reply(message, "数据库中还没有作者。")
            return

        lines = ["当前频道的作者列表："]
        for owner in owners:
            user_id = owner["user_id"]
            if not await _is_user_in_current_guild(self, message, user_id):
                continue

            note = f" ({owner['note']})" if owner["note"] else ""
            lines.append(f"{_mention_user(user_id)}{note}")

        if len(lines) == 1:
            await self.send_reply(message, "当前频道没有数据库作者。")
            return

        await self.send_reply(message, "\n".join(lines))
