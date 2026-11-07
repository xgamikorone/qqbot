"""Per-event reply sequencing without replacing SDK message objects."""

import contextlib
import contextvars
import dataclasses
import typing


class GroupImageUploadError(RuntimeError):
    """The image upload failed before any group reply was attempted."""


@dataclasses.dataclass
class ReplyState:
    """Mutable sending state belonging to one incoming event."""

    message: object
    sequence: int = 0


_STATE: contextvars.ContextVar[ReplyState | None] = contextvars.ContextVar(
    "command_reply_state", default=None
)


@contextlib.contextmanager
def reply_scope(message: object) -> typing.Iterator[None]:
    """Shares sequence allocation within a chain, isolating concurrent events."""
    token = _STATE.set(ReplyState(message))
    try:
        yield
    finally:
        _STATE.reset(token)


def next_sequence(message: object) -> int:
    """Allocates before awaiting transport; failed sends consume a sequence."""
    state = _STATE.get()
    if state is None or state.message is not message:
        raise RuntimeError("群聊/单聊回复必须在对应事件的 reply_scope 中发送")
    state.sequence += 1
    return state.sequence


def require_id(value: object) -> str:
    """Validates opaque IDs at the SDK's incompletely typed boundary."""
    if not isinstance(value, str) or not value:
        raise ValueError("消息缺少有效标识")
    return value
