import asyncio
import os
from datetime import datetime
from typing import Any

import aiohttp
import matplotlib
import pandas as pd
from botpy import logging
from botpy.message import Message
from dotenv import load_dotenv
from matplotlib import font_manager
from matplotlib import pyplot as plt

from utils.async_retry import retry_empty
from utils.revenue_rank_v2 import (
    RevenuePeriodOptions,
    format_month_label,
    merge_realtime_revenue,
    parse_revenue_period_args,
)

from .base import Command, command, cooldown
from .help_catalog import CommandHelp
from .tags import tags_map


load_dotenv()
_log = logging.get_logger()

matplotlib.rcParams["axes.unicode_minus"] = False
FONT_PATH = os.path.join("fonts", "simhei.ttf")
TABLE_FONT = (
    font_manager.FontProperties(fname=FONT_PATH, size=14)
    if os.path.exists(FONT_PATH)
    else None
)


async def _fetch_realtime_revenue_once(
    start_time: datetime,
    end_time: datetime,
    tag_id: int,
) -> Any | None:
    base_url = os.getenv("LIVE_MONITOR_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("LIVE_MONITOR_API_TOKEN", "").strip()
    if not base_url or not token:
        _log.error("Live Monitor API configuration is incomplete")
        return None

    params = {
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "tag_id": tag_id,
    }
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base_url}/revenue_by_period_realtime",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                response.raise_for_status()
                return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
        _log.warning(f"Live Monitor realtime revenue request failed: {error}")
        return None


async def fetch_realtime_revenue(
    start_time: datetime, end_time: datetime, tag_id: int
) -> Any | None:
    return await retry_empty(
        lambda: _fetch_realtime_revenue_once(start_time, end_time, tag_id),
        max_attempts=3,
        retry_delay=1,
        on_retry=lambda attempt, total: _log.warning(
            f"获取实时营收失败，第 {attempt}/{total} 次尝试，即将重试"
        ),
    )


def draw_realtime_revenue_table(
    rows: list[dict[str, Any]], options: RevenuePeriodOptions
) -> str:
    frame = pd.DataFrame(rows)
    frame.insert(0, "rank", range(1, len(frame) + 1))
    table_frame = frame[
        [
            "rank",
            "name",
            "total_income",
            "gift_income",
            "guard_income",
            "super_chat_income",
        ]
    ].copy()
    table_frame.columns = ["排名", "主播", "总收入", "礼物", "上舰", "SC"]
    for column in ["总收入", "礼物", "上舰", "SC"]:
        table_frame[column] = table_frame[column].map(lambda value: f"{value:,.1f}")

    figure_height = max(3.8, 1.7 + len(table_frame) * 0.52)
    figure, axis = plt.subplots(figsize=(12, figure_height))
    figure.patch.set_facecolor("#F7FAFE")
    figure.subplots_adjust(left=0.02, right=0.98, bottom=0.075, top=0.84)
    axis.axis("off")
    table = axis.table(
        cellText=table_frame.values,
        colLabels=table_frame.columns,
        loc="upper center",
        cellLoc="center",
        colLoc="center",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.scale(1.1, 1.4)
    table.auto_set_column_width(col=list(range(len(table_frame.columns))))

    medal_colors = {1: "#F5B51B", 2: "#9EA4AA", 3: "#D78232"}
    numeric_columns = {2, 3, 4, 5}
    for (row_index, column_index), cell in table.get_celld().items():
        cell.set_edgecolor("#D8E4F2")
        cell.set_linewidth(0.8)
        cell.set_text_props(color="#17233D", fontproperties=TABLE_FONT)
        if row_index == 0:
            cell.set_facecolor("#2F80ED")
            cell.set_text_props(color="white", weight="bold", fontproperties=TABLE_FONT)
        else:
            cell.set_facecolor("#FFFFFF" if row_index % 2 else "#F1F6FC")
            if column_index == 1:
                cell.set_text_props(ha="left", fontproperties=TABLE_FONT)
            elif column_index in numeric_columns:
                cell.set_text_props(ha="right", fontproperties=TABLE_FONT)
            if column_index == 2:
                cell.set_text_props(
                    ha="right", weight="bold", color="#102A56", fontproperties=TABLE_FONT
                )
            if column_index == 0 and row_index in medal_colors:
                text = cell.get_text()
                text.set_color("white")
                text.set_weight("bold")
                text.set_bbox(
                    {
                        "boxstyle": "circle,pad=0.35",
                        "facecolor": medal_colors[row_index],
                        "edgecolor": "none",
                    }
                )

    period = format_month_label(options.months)
    figure.text(
        0.5,
        0.975,
        "斗虫 v2 · 实时营收排行榜",
        ha="center",
        va="top",
        fontproperties=TABLE_FONT,
        fontsize=22,
        fontweight="bold",
        color="#102A56",
    )
    figure.text(
        0.5,
        0.915,
        f"{period}  |  分类：{options.tag.upper()}  |  数据截至 {options.end_time:%m-%d %H:%M}",
        ha="center",
        va="top",
        fontproperties=TABLE_FONT,
        fontsize=12,
        color="#52657D",
    )
    figure.text(
        0.025,
        0.025,
        "注：本排行榜仅统计直播期间的营收",
        ha="left",
        va="bottom",
        fontproperties=TABLE_FONT,
        fontsize=10,
        color="#6D7E91",
    )
    figure.text(
        0.975,
        0.025,
        "制图：丸子bot",
        ha="right",
        va="bottom",
        fontproperties=TABLE_FONT,
        fontsize=10,
        color="#6D7E91",
    )

    os.makedirs("imgs", exist_ok=True)
    path = os.path.join("imgs", f"revenue_rank_v2_{datetime.now():%Y%m%d%H%M%S%f}.png")
    try:
        figure.savefig(path, dpi=100, bbox_inches="tight")
    finally:
        plt.close(figure)
    return path


@command("斗虫v2", "斗虫V2", "revenue_rank_v2")
class RevenueRankV2Command(Command):
    name = "revenue_rank_v2"
    cn_name = "斗虫v2"
    help = CommandHelp(
        title="斗虫v2",
        category="直播数据",
        summary=(
            "查看指定月份及分类的实时营收排行榜；默认本月和 vr，"
            "月份支持 YYYYMM、逗号分隔、连续区间及常用时间词"
        ),
        usage="/斗虫v2 [/f 分类] [/m 月份] [/n 数量]",
        examples=(
            "/斗虫v2",
            "/斗虫v2 /f psp /m 202608 /n 20",
            "/斗虫v2 /f vr /m 202606-202608 /n 10",
            "/斗虫v2 /f wan /m 今年 /n 20",
        ),
        lookup_names=("斗虫v2", "revenue_rank_v2"),
    )

    @cooldown(60)
    async def execute(self, message: Message, args: list[str]):
        try:
            options = parse_revenue_period_args(args)
        except ValueError as error:
            await self.send_reply(message, f"参数错误：{error}\n输入 /帮助 斗虫v2 查看用法。")
            return

        if options.tag not in tags_map:
            await self.send_reply(
                message,
                f"分类错误：{options.tag}\n可用分类：{', '.join(tags_map)}",
            )
            return
        tag_id = tags_map[options.tag]

        await self.send_reply(message, "正在获取实时营收并生成斗虫 v2 排行榜，请稍候……")
        payloads = await asyncio.gather(
            *(
                fetch_realtime_revenue(start, end, tag_id)
                for start, end in options.periods
            )
        )
        rows = merge_realtime_revenue(payloads, options.top_n)
        if not rows:
            await self.send_reply(message, "未获取到营收数据，请稍后再试或调整时间范围。")
            return

        path = None
        try:
            path = await asyncio.to_thread(draw_realtime_revenue_table, rows, options)
            for attempt in range(1, 4):
                try:
                    await self.client.api.post_message(
                        channel_id=message.channel_id,
                        file_image=path,
                        msg_id=message.id,
                    )
                    return
                except Exception as error:
                    _log.warning(f"发送斗虫 v2 图片失败 {attempt}/3: {error}")
                    if attempt < 3:
                        await asyncio.sleep(1)
            await self.send_reply(message, "排行榜图片发送失败，请稍后再试。")
        except Exception as error:
            _log.exception(f"生成斗虫 v2 排行榜失败: {error}")
            await self.send_reply(message, "生成排行榜失败，请稍后再试。")
        finally:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError as error:
                    _log.warning(f"清理斗虫 v2 临时图片失败: {error}")
