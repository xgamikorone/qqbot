"""Opt-in, bounded single-message GET experiment using observed compact IDs."""

import asyncio

from botpy import api as botpy_api

from messaging import message_id
from . import channel_history

MAX_CANDIDATES = 50


async def read_range(
    api: botpy_api.BotAPI, channel: str, start_id: str, end_id: str
) -> list[channel_history.HistoryMessage]:
    """Queries each selected sequence once; any gap or mismatch fails closed.

    Candidates preserve the compact start's field 1, channel and timestamp.
    Timestamp equality is not assumed for the response: its actual timestamp
    must fall between the validated endpoints. No candidate is ever sent as
    a reply source. Unsupported expanded inputs require re-quoting messages.
    """
    try:
        first = message_id.decode_message_id(start_id)
        last = message_id.decode_message_id(end_id)
    except ValueError:
        raise channel_history.HistoryError(
            "实验模式需要紧凑格式的原始引用ID，请重新引用起止消息。"
        ) from None
    count = last.sequence - first.sequence + 1
    if (
        str(first.channel_id) != channel
        or first.channel_id != last.channel_id
        or first.guild_id != last.guild_id
    ):
        raise channel_history.HistoryError(
            "起止ID不属于同一频道作用域，停止实验查询。"
        )
    if not 1 <= count <= MAX_CANDIDATES or first.timestamp > last.timestamp:
        raise channel_history.HistoryError(
            "实验模式仅支持正向、最多50个连续序号，请缩小范围。"
        )
    async with asyncio.timeout(60):
        start = await channel_history.get_message(api, channel, start_id)
        end = (
            start
            if start_id == end_id
            else await channel_history.get_message(api, channel, end_id)
        )
        records: list[channel_history.HistoryMessage] = []
        for sequence in range(first.sequence, last.sequence + 1):
            if sequence == first.sequence:
                result = start
            elif sequence == last.sequence:
                result = end
            else:
                await asyncio.sleep(0.25)
                candidate = message_id.encode_message_id(
                    first.guild_id, first.channel_id, sequence, first.timestamp
                )
                try:
                    raw = await api.get_message(channel, candidate)
                except Exception:
                    raise channel_history.HistoryError(
                        "实验查询遇到缺失消息、权限或接口错误，已停止；不会总结不完整区间。"
                    ) from None
                result = channel_history._message(raw, channel)
            try:
                _, actual_channel, actual_sequence, actual_time = (
                    message_id.decode_lookup_identity(result.id)
                )
            except ValueError:
                raise channel_history.HistoryError(
                    "返回ID格式无法验证，已停止实验查询。"
                ) from None
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
                    "返回消息频道、序号或实际时间与范围不符，已停止实验查询。"
                )
            records.append(result)
        return records
