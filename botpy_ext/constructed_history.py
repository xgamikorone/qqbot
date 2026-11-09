"""Bounded single-message history lookup using observed compact IDs."""

import asyncio
import dataclasses

from botpy import api as botpy_api

from messaging import message_id
from . import channel_history

MAX_CANDIDATES = 200
READ_TIMEOUT_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 15


@dataclasses.dataclass(frozen=True)
class HistoryRange:
    """Validated contiguous prefix and a safe explanation for an early stop."""

    records: list[channel_history.HistoryMessage]
    requested_count: int
    stop_reason: str = ""


def _validate(
    result: channel_history.HistoryMessage,
    first: message_id.MessageIDInfo,
    last: message_id.MessageIDInfo,
    sequence: int,
) -> None:
    """Rejects unsupported identities and messages outside the selected scope."""
    try:
        _, actual_channel, actual_sequence, actual_time = (
            message_id.decode_lookup_identity(result.id)
        )
    except ValueError:
        raise channel_history.HistoryError("返回ID格式无法验证。") from None
    if (
        actual_channel != first.channel_id
        or actual_sequence != sequence
        or not first.timestamp <= actual_time <= last.timestamp
        or (result.sequence is not None and result.sequence != sequence)
        or (
            result.timestamp is not None
            and int(result.timestamp) != actual_time
        )
    ):
        raise channel_history.HistoryError(
            "返回消息频道、序号或实际时间与范围不符。"
        )


async def read_range(
    api: botpy_api.BotAPI, channel: str, start_id: str, end_id: str
) -> HistoryRange:
    """Reads in order, returning only the verified prefix on the first failure.

    Candidates preserve the start's field 1, channel and timestamp. Actual
    endpoint IDs are used for endpoint GETs. No failed sequence is skipped and
    no candidate is used as a reply source. Cancellation still propagates.
    """
    try:
        first = message_id.decode_message_id(start_id)
        last = message_id.decode_message_id(end_id)
    except ValueError:
        raise channel_history.HistoryError(
            "逐条查询需要紧凑格式的原始引用ID，请重新引用起止消息。"
        ) from None
    count = last.sequence - first.sequence + 1
    if (
        str(first.channel_id) != channel
        or first.channel_id != last.channel_id
        or first.guild_id != last.guild_id
    ):
        raise channel_history.HistoryError("起止ID不属于同一频道作用域。")
    if not 1 <= count <= MAX_CANDIDATES or first.timestamp > last.timestamp:
        raise channel_history.HistoryError(
            f"逐条查询仅支持正向、最多{MAX_CANDIDATES}个连续序号，请缩小范围。"
        )
    if count == 1 and first != last:
        raise channel_history.HistoryError("同一序号的起止消息身份不一致。")
    records: list[channel_history.HistoryMessage] = []
    reason = ""
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            for sequence in range(first.sequence, last.sequence + 1):
                if records:
                    await asyncio.sleep(0.25)
                if sequence == first.sequence:
                    candidate = start_id
                elif sequence == last.sequence:
                    candidate = end_id
                else:
                    candidate = message_id.encode_message_id(
                        first.guild_id,
                        first.channel_id,
                        sequence,
                        first.timestamp,
                    )
                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                        if sequence in (first.sequence, last.sequence):
                            result = await channel_history.get_message(
                                api, channel, candidate
                            )
                        else:
                            raw = await api.get_message(channel, candidate)
                            result = channel_history._message(raw, channel)
                    _validate(result, first, last, sequence)
                except TimeoutError:
                    reason = "单条消息读取超时"
                    break
                except channel_history.HistoryError as error:
                    reason = str(error)
                    break
                except Exception:
                    reason = "消息缺失、权限不足或接口请求失败"
                    break
                records.append(result)
    except TimeoutError:
        reason = "达到消息读取总时限"
    if not records:
        raise channel_history.HistoryError(
            f"起点消息读取失败：{reason}；本次未调用模型。"
        )
    return HistoryRange(records, count, reason)
