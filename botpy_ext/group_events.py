"""Preserve group event display names before the SDK drops unknown fields."""

import typing

import botpy
from botpy import connection as botpy_connection
from botpy import message as botpy_message
from botpy import robot as botpy_robot
from botpy.types import gateway


def install_group_parser(
    connection: botpy_connection.ConnectionSession,
) -> None:
    """Replaces only this connection's group parser, retaining SDK messages."""

    def parse(payload: dict[str, object]) -> None:
        data = payload.get("d")
        if not isinstance(data, dict):
            return
        # The SDK payload TypedDict predates the group event fields. Pass the
        # original event data through its normal constructor, then retain name.
        message = botpy_message.GroupMessage(
            connection.state.api,
            payload.get("id"),
            typing.cast(gateway.MessagePayload, data),
        )
        author = data.get("author")
        role = author.get("member_role") if isinstance(author, dict) else None
        setattr(
            message.author,
            "member_role",
            role if role in ("member", "admin", "owner") else "",
        )
        name = author.get("username") if isinstance(author, dict) else None
        setattr(
            message.author,
            "username",
            name.strip() if isinstance(name, str) else "",
        )
        connection.dispatch("group_at_message_create", message)

    connection.parser["group_at_message_create"] = parse


class GroupNicknameClient(botpy.Client):
    """Installs the connection-local parser after SDK login, before events."""

    async def _bot_login(self, token: botpy_robot.Token) -> None:
        await super()._bot_login(token)
        if self._connection is None:
            raise RuntimeError("SDK 未创建事件连接")
        install_group_parser(self._connection)
