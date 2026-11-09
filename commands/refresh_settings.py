"""Scoped wife refresh command behavior shared by guild and group entry points."""

import collections.abc
import typing

import dao
from . import text_query


async def run(
    scene: typing.Literal["guild", "group"],
    scope_id: str,
    args: list[str],
    reply: text_query.TextSender,
    authorize: collections.abc.Callable[[], collections.abc.Awaitable[bool]],
) -> bool:
    """Allows public queries but authorizes every scoped write separately."""
    from . import wife

    label = "当前频道" if scene == "guild" else "当前群聊"
    if not args or (len(args) == 1 and args[0] in ("查看", "查询", "current")):
        await reply(
            f"{label}老婆刷新时间：{dao.get_dao().settings.get_wife_refresh_time(scene, scope_id)}"
        )
        return True
    value = wife.parse_refresh_time(args[0]) if len(args) == 1 else None
    if value is None:
        await reply("格式错误，应为 /设置老婆刷新时间 <HH:MM>，例如：08:00")
        return False
    if not await authorize():
        await reply(
            "需要当前频道作者/管理员或本群群主/管理员权限；无法确认身份时不允许修改。"
        )
        return False
    if dao.get_dao().settings.set_scoped_wife_refresh_time(
        scene, scope_id, value
    ):
        await reply(f"{label}老婆刷新时间已设置为：{value}")
        return True
    await reply("设置老婆刷新时间失败，请稍后再试！")
    return False
