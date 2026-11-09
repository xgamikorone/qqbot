"""Bounded channel history retrieval using official message sequence fields."""

import dataclasses
import datetime
import json
import logging

from botpy import api as botpy_api
from botpy import http as botpy_http
from messaging import message_id

_LOG = logging.getLogger(__name__)


def _same_id(reference: str, returned: str, channel: str) -> bool:
    """Checks observed lookup representations without creating new IDs."""
    if reference == returned:
        return True
    try:
        first = message_id.decode_lookup_identity(reference)
        second = message_id.decode_lookup_identity(returned)
    except ValueError:
        return False
    if first[0] == second[0] == "compact":
        return (
            message_id.decode_message_id(reference)
            == message_id.decode_message_id(returned)
            and str(first[1]) == channel
        )
    if {first[0], second[0]} == {"compact", "expanded"}:
        return first[1:] == second[1:] and str(first[1]) == channel
    return reference.lower() == returned.lower() and str(first[1]) == channel


class HistoryError(ValueError):
    """Safe user-facing failure without message bodies or request URLs."""


@dataclasses.dataclass(frozen=True)
class HistoryMessage:
    """Minimal transient text-only representation of one visible message."""

    id: str
    sequence: int | None
    author: str
    content: str
    timestamp: float | None = None


def _json(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            raise HistoryError("消息接口未返回有效 JSON。") from None
    return value


def _message(value: object, channel: str) -> HistoryMessage:
    value = _json(value)
    if isinstance(value, dict) and isinstance(value.get("message"), dict):
        value = value["message"]
    if not isinstance(value, dict) or value.get("channel_id") != channel:
        raise HistoryError("消息不属于当前子频道或接口数据不完整。")
    identifier, seq = value.get("id"), value.get("seq_in_channel")
    if not isinstance(identifier, str) or not identifier:
        raise HistoryError("消息缺少有效 ID 或频道序号。")
    try:
        sequence = (
            int(seq)
            if isinstance(seq, (str, int)) and not isinstance(seq, bool)
            else -1
        )
    except ValueError:
        sequence = -1
    stamp = value.get("timestamp")
    timestamp = None
    if isinstance(stamp, str):
        try:
            parsed_time = datetime.datetime.fromisoformat(
                stamp.replace("Z", "+00:00")
            )
            if parsed_time.tzinfo is not None:
                timestamp = parsed_time.timestamp()
        except (ValueError, OverflowError, OSError):
            pass
    if sequence < 0 and timestamp is None:
        raise HistoryError(
            "接口没有返回有效频道序号或带时区的发送时间，无法确定消息范围。"
        )
    author = value.get("author")
    name = author.get("username") if isinstance(author, dict) else None
    content = value.get("content")
    text = content if isinstance(content, str) else ""
    attachments = value.get("attachments")
    if isinstance(attachments, list) and attachments:
        text += f" [附件{len(attachments)}项，未读取内容]"
    return HistoryMessage(
        identifier,
        sequence if sequence >= 0 else None,
        name if isinstance(name, str) else "用户",
        text,
        timestamp,
    )


async def get_message(
    api: botpy_api.BotAPI, channel: str, identifier: str
) -> HistoryMessage:
    """Validates an endpoint using QQ's single-message interface."""
    result = await api.get_message(channel, identifier)
    parsed = _message(result, channel)
    if not _same_id(identifier, parsed.id, channel):
        _LOG.warning(
            "频道消息ID校验失败: requested_id=%r returned_id=%r channel_id=%r",
            identifier[:256],
            parsed.id[:256],
            channel[:128],
        )
        raise HistoryError("接口返回的消息与引用不一致。")
    return parsed


async def read_range(
    api: botpy_api.BotAPI,
    channel: str,
    start_id: str,
    end_id: str,
    limit: int = 500,
) -> list[HistoryMessage]:
    """Walks backwards to the exact start; never summarizes a partial range."""
    start = await get_message(api, channel, start_id)
    end = await get_message(api, channel, end_id)
    if start.id == end.id:
        return [start]
    use_sequence = start.sequence is not None and end.sequence is not None

    def order(message: HistoryMessage) -> int | float:
        value = message.sequence if use_sequence else message.timestamp
        if value is None:
            raise HistoryError("分页消息缺少一致的排序信息，无法完整读取区间。")
        return value

    if order(start) > order(end):
        raise HistoryError("起点晚于终点，请重新标记范围。")
    if order(start) == order(end):
        raise HistoryError(
            "起止消息排序值相同且无法区分先后，请选择发送时间不同的边界消息。"
        )
    messages = {end.id: end}
    cursor = end
    for _ in range(26):
        page = _json(
            await api._http.request(
                botpy_http.Route(
                    "GET", "/channels/{channel_id}/messages", channel_id=channel
                ),
                params={"before": cursor.id, "limit": "20"},
            )
        )
        if not isinstance(page, list) or not page:
            raise HistoryError(
                "未能完整读取起止区间，可能已删除消息或没有历史读取权限。"
            )
        parsed = sorted(
            (_message(row, channel) for row in page),
            key=order,
            reverse=True,
        )
        for row in parsed:
            # Single-message and list endpoints may use different observed
            # representations. Preserve actual API IDs; never synthesize one.
            if _same_id(start.id, row.id, channel):
                row = dataclasses.replace(row, id=start.id)
            elif _same_id(end.id, row.id, channel):
                row = dataclasses.replace(row, id=end.id)
            if (
                not use_sequence
                and order(row) == order(start)
                and row.id != start.id
            ):
                raise HistoryError(
                    "起点附近多条消息时间相同且缺少序号，请重新选择时间不同的起点。"
                )
            if order(start) <= order(row) <= order(end):
                messages[row.id] = row
        if len(messages) > limit:
            raise HistoryError(f"区间超过 {limit} 条消息，请缩小范围。")
        if start.id in messages:
            return sorted(messages.values(), key=order)
        oldest = parsed[-1]
        if order(oldest) <= order(start) or order(oldest) >= order(cursor):
            raise HistoryError("分页未能到达起点，请重新选择较小的范围。")
        if (
            not use_sequence
            and sum(order(row) == order(oldest) for row in parsed) > 1
        ):
            raise HistoryError(
                "分页边界多条消息时间相同且缺少序号，请缩小总结范围。"
            )
        cursor = oldest
    raise HistoryError("消息区间过大，请缩小范围。")
