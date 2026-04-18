import asyncio
import os
import platform
from datetime import datetime
from textwrap import dedent
import traceback
from typing import Any, Dict, List, Optional

import aiohttp
import matplotlib
import pandas as pd
from botpy import logging
from botpy.message import Message
from dotenv import load_dotenv
from matplotlib import font_manager
from matplotlib import pyplot as plt

from commands.api import get_revenue_rank

# from utils.image_client import AsyncShuimoImageClient

from .base import Command, command, cooldown

load_dotenv()
SHUIMO_TOKEN = os.getenv("SHUIMO_TOKEN", None)

# 1️⃣ 字体路径（相对于当前文件）
font_path = os.path.join("fonts", "simhei.ttf")  # 确保这个路径存在

# 2️⃣ 生成字体对象
if os.path.exists(font_path):
    my_font = font_manager.FontProperties(fname=font_path, size=16)
else:
    # 如果没有 ttf 文件，就用 matplotlib 默认字体
    my_font = None

# 3️⃣ 解决负号显示问题
matplotlib.rcParams["axes.unicode_minus"] = False

_log = logging.get_logger()


url = "https://img.scdn.io/api/v1.php"


async def upload_image(
    file_path: str,
    cdn_domain: str = "img.scdn.io",
    timeout: int = 60,
) -> Optional[Dict[str, Any]]:
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            form = aiohttp.FormData()

            with open(file_path, "rb") as f:
                form.add_field(
                    name="image",
                    value=f,
                )
                form.add_field("cdn_domain", cdn_domain)
                form.add_field("outputFormat", "png")

                async with session.post(url, data=form) as resp:
                    resp.raise_for_status()
                    return await resp.json()

    except aiohttp.ClientResponseError as e:
        # HTTP 状态码错误（4xx / 5xx）
        print(f"[HTTP ERROR] {e.status}: {e.message}")

    except aiohttp.ClientError as e:
        # 网络层错误
        print(f"[NETWORK ERROR] {e}")

    except FileNotFoundError:
        print(f"[FILE ERROR] 文件不存在: {file_path}")

    except Exception as e:
        # 兜底
        print(f"[UNKNOWN ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()

    return None


def draw_rank_table(
    data: dict,
    top_n: Optional[int] = None,
):
    df = pd.DataFrame(data["anchors"])

    # df = pd.DataFrame(data['anchors'])

    # 排序 + 排名
    df = df.sort_values("total_revenue", ascending=False).reset_index(drop=True)
    if top_n is None:
        top_n = len(df)

    df = df.head(top_n)
    df["rank"] = df.index + 1

    # 状态文字
    df["status_text"] = df["status"].map({0: "未开播", 1: "直播中"})

    # 选择并重命名列
    df_table = df[
        [
            "rank",
            "anchor_name",
            "total_revenue",
            "attention",
            "status_text",
            "effective_days",
            "live_duration",
            "guard_1",
            "guard_2",
            "guard_3",
            "gift",
            "super_chat",
            "guard",
        ]
    ].copy()

    df_table.columns = [
        "排名",
        "主播",
        "总计",
        "粉丝数",
        "状态",
        "有效天数",
        "直播时长",
        "舰长",
        "提督",
        "总督",
        "礼物",
        "SC",
        "上舰",
    ]

    # 格式化数值（带逗号，小数点1位）
    for col in ["礼物", "SC", "上舰", "总计"]:
        df_table[col] = df_table[col].apply(lambda x: f"{float(x):,.1f}")

    # ── matplotlib 表格 ────────────────────────────────────────────────
    # plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    # plt.rcParams["axes.unicode_minus"] = False

    n_rows = len(df_table)
    n_cols = len(df_table.columns)

    # 动态尺寸
    height_per_row = 0.65
    fig_height = 0.8 + n_rows * height_per_row
    fig_width = max(12.0, min(22.0, 10 + n_cols * 1.05))

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))  # 宽度可根据列数调大
    # 留出更多上方空间给标题
    # plt.subplots_adjust(top=0.92, bottom=0.05, left=0.05, right=0.95)
    # fig.suptitle(
    #     "2026年01月 PSPlive 主播数据排行榜\n(按总计降序 | 刷新时间: 2026-01-31 08:58:45)",
    #     fontsize=14,
    #     fontweight="bold",
    #     y=0.96,  # 0.92 ~ 0.98 之间调整，越大越靠上
    # )
    ax.axis("off")

    # 创建表格
    table = ax.table(
        cellText=df_table.values,  # type: ignore
        colLabels=df_table.columns,  # type: ignore
        loc="upper center",
        bbox=[0.01, 0.01, 1.0, 0.96],  # 稍微下移一点 # type: ignore
        cellLoc="center",
        colLoc="center",
        edges="closed",
    )

    for (i, j), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=my_font)  # ✅ 正确方法
        # 可选：设置加粗表头

    table.auto_set_font_size(False)
    table.set_fontsize(16)

    table.scale(1.3, 1.5)  # 调整整体比例
    table.auto_set_column_width(col=list(range(len(df_table.columns))))

    # 然后针对特定列进行微调（单位是 字体大小的倍数，大约 0.1~2.0 之间常见）
    col_widths = {
        0: 0.6,  # 排名 - 很窄
        1: 1.8,  # 总计 - 最宽
        2: 1.4,  # 主播名 - 比较宽
        3: 0.9,  # 粉丝数
        4: 0.7,  # 状态
        5: 0.8,  # 有效天数
        6: 1.1,  # 直播时长
        7: 0.6,  # 舰长
        8: 0.6,  # 提督
        9: 0.6,  # 总督
        10: 1.0,  # 礼物
        11: 1.0,  # SC
        12: 1.2,  # 上舰
    }

    for col_idx, width_factor in col_widths.items():
        table.auto_set_column_width(col_idx)  # 先自动一次
        # 再手动乘以因子进行微调
        for row in range(len(df_table) + 1):  # +1 包含表头
            cell = table[(row, col_idx)]
            cell.set_width(width_factor * 0.018)  # 0.018 是经验值，可根据字体大小调整

    # 表头样式
    for j in range(len(df_table.columns)):
        cell = table[0, j]
        cell.set_facecolor("#00BFFF")
        cell.set_text_props(color="white", weight="bold", fontproperties=my_font)

    # 交替行背景 + 直播中高亮
    for i in range(len(df_table)):
        for j in range(len(df_table.columns)):
            cell = table[i + 1, j]
            if i % 2 == 1:
                cell.set_facecolor("#f5f5f5")
            if df_table.iloc[i]["状态"] == "直播中" and df_table.columns[j] == "状态":
                cell.set_text_props(color="red", weight="bold")
            # 数值列右对齐
            if df_table.columns[j] in [
                "礼物",
                "SC",
                "上舰",
                "总计",
                "粉丝数",
                "舰长",
                "提督",
                "总督",
                "有效天数",
            ]:
                cell.set_text_props(ha="right", fontproperties=my_font)

    # 标题
    filter_to_category = {
        "all": "VR+PSP",
        "psp": "PSP",
        "vr": "VR",
    }
    title = f"{data.get('month', datetime.now().strftime('%Y%m'))} {filter_to_category[data['filter']]}主播数据排行榜\n(按总计降序 | 刷新时间: {data['refresh_time']})"
    plt.title(title, fontsize=20, fontweight="bold", pad=0, fontproperties=my_font)

    # plt.tight_layout()

    # 保存图片（dpi越高越清晰）
    if not os.path.exists("imgs"):
        os.makedirs("imgs")
    save_path = f"imgs/revenue_rank_{data.get('month', datetime.now().strftime('%Y%m'))}_{data['filter']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    plt.savefig(save_path, dpi=50, bbox_inches="tight")
    print(f"图片已保存到 {save_path}")
    return save_path


@command("斗虫", "revenue_rank")
class RevenueRankCommand(Command):
    name = "revenue_rank"
    cn_name = "斗虫"

    @cooldown(60)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Executing {self.name} command with args: {args}")

        # 初始化默认值
        filter = "vr"
        month = datetime.now().strftime("%Y%m")
        top_n = None

        # 解析命名参数 /f /m /n
        i = 0
        while i < len(args):
            if args[i] == "/f" and i + 1 < len(args):
                filter = args[i + 1]
                i += 2
            elif args[i] == "/m" and i + 1 < len(args):
                month = args[i + 1]
                i += 2
            elif args[i] == "/n" and i + 1 < len(args):
                top_n = args[i + 1]
                i += 2
            else:
                i += 1

        # 验证参数
        if filter not in ["vr", "psp", "all"]:
            await self.send_reply(message, "过滤器错误，请使用vr/psp/all")
            return

        if not month.isdigit() or len(month) != 6:
            await self.send_reply(message, "月份格式错误，请使用YYYYMM格式")
            return

        if top_n is not None:
            if not top_n.isdigit():
                await self.send_reply(message, "显示数量错误，请使用数字")
                return
            top_n = int(top_n)

        retry = 3
        success = False

        while retry > 0:

            data = await get_revenue_rank(month, filter)
            _log.info(f"Got revenue rank data: {data}")
            if data is None or len(data.get("anchors", [])) == 0:

                retry -= 1
                await asyncio.sleep(1)
                continue

            success = True
            break

        if not success:
            await self.send_reply(message, "获取数据失败，请稍后再试")
            return

        await self.send_reply(
            message, f"正在生成{month} {filter}主播数据排行榜，请稍后……"
        )
        try:
            path = draw_rank_table(data, top_n)  # type: ignore
            print(f"File size: {os.path.getsize(path) / 1024} KB")
        except Exception as e:
            _log.error(f"Failed to draw rank table: {e}")
            await self.send_reply(message, "生成排行榜失败，请稍后再试")
            return

        # 上传图片
        # async with AsyncShuimoImageClient() as client:
        #     result = await client.upload_image(path, folder="img")
        #     data = result.get("data", {})

        # retry = 3
        # while retry > 0:
        #     data = await upload_image(path, cdn_domain="cloudflareimg.cdn.sn")

        #     await asyncio.sleep(1)  # 等待图片上传成功
        #     if data is not None:
        #         break
        #     retry -= 1
        # if retry == 0:
        #     await self.send_reply(message, "上传图片失败, 请稍后再试")
        #     return

        # # 删除本地图片文件
        # try:
        #     os.remove(path)
        # except Exception as e:
        #     _log.error(f"Failed to remove local image file: {e}")

        # if data is None or "url" not in data or data.get("success", False) is not True:
        #     await self.send_reply(message, "上传图片失败, 请稍后再试")
        #     return

        # image_url = data.get("url", "")
        retry = 3
        while retry > 0:
            try:
                await self.client.api.post_message(
                    channel_id=message.channel_id, file_image=path, msg_id=message.id
                )
                break
            except Exception as e:
                _log.error(f"Failed to send image: {e}")

                retry -= 1
        # 删除文件
        try:
            os.remove(path)
        except Exception as e:
            _log.error(f"Failed to remove local image file: {e}")
        return


revenue_rank_help_str = dedent(
    """\
    斗虫 指令用法:
    收到指令后，生成指定月份和类别的主播收入排行榜图片并上传。
    
    指令格式:
    斗虫 /f <filter> /m <month> /n <top_n>
    
    参数说明:
    /f <filter>   过滤器，指定类别。可选值:
                  vr - 仅VR主播(默认)
                  psp - 仅PSP主播
                  all - VR+PSP主播
    
    /m <month>    指定月份，格式为YYYYMM。例如: 202601表示2026年1月。默认为当前月份。
    
    /n <top_n>    显示前N名主播的数据。如果不指定，则显示全部主播。
    
    示例:
    斗虫 /f vr /m 202601 /n 20
    生成2026年1月VR主播收入排行榜，显示前20名主播的数据。
"""
)


@command("斗虫帮助", "revenue_rank_help")
class RevenueRankHelpCommand(Command):
    name = "revenue_rank_help"
    cn_name = "斗虫帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, revenue_rank_help_str)
        return
