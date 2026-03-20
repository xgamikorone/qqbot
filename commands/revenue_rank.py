import asyncio
import os
import platform
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
from utils.time_utils import beijing_now_str, to_beijing_time_str

# from utils.image_client import AsyncShuimoImageClient

from .base import Command, command, cooldown

load_dotenv()
SHUIMO_TOKEN = os.getenv("SHUIMO_TOKEN", None)

# 1锔忊儯 瀛椾綋璺緞锛堢浉瀵逛簬褰撳墠鏂囦欢锛?
font_path = os.path.join("fonts", "simhei.ttf")  # 纭繚杩欎釜璺緞瀛樺湪

# 2锔忊儯 鐢熸垚瀛椾綋瀵硅薄
if os.path.exists(font_path):
    my_font = font_manager.FontProperties(fname=font_path, size=16)
else:
    # 濡傛灉娌℃湁 ttf 鏂囦欢锛屽氨鐢?matplotlib 榛樿瀛椾綋
    my_font = None

# 3锔忊儯 瑙ｅ喅璐熷彿鏄剧ず闂
matplotlib.rcParams["axes.unicode_minus"] = False

_log = logging.get_logger()


async def get_revenue_rank(month: str, filter: str):
    cur_month = beijing_now_str("%Y%m")
    is_cur_month = month == cur_month
    if is_cur_month:
        url = "https://dc.hihivr.top/gift"
    else:
        url = "https://dc.hihivr.top/gift/by_month"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"month": month, "filter": filter},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                return None
    except aiohttp.ClientError as e:
        _log.error(f"Failed to get revenue rank: {e}")
        return None


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
        # HTTP 鐘舵€佺爜閿欒锛?xx / 5xx锛?
        print(f"[HTTP ERROR] {e.status}: {e.message}")

    except aiohttp.ClientError as e:
        # 缃戠粶灞傞敊璇?
        print(f"[NETWORK ERROR] {e}")

    except FileNotFoundError:
        print(f"[FILE ERROR] 鏂囦欢涓嶅瓨鍦? {file_path}")

    except Exception as e:
        # 鍏滃簳
        print(f"[UNKNOWN ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()

    return None


def draw_rank_table(
    data: dict,
    top_n: Optional[int] = None,
):
    df = pd.DataFrame(data["anchors"])

    # df = pd.DataFrame(data['anchors'])

    # 鎺掑簭 + 鎺掑悕
    df = df.sort_values(
        "total_revenue", ascending=False).reset_index(drop=True)
    if top_n is None:
        top_n = len(df)

    df = df.head(top_n)
    df["rank"] = df.index + 1

    # 鐘舵€佹枃瀛?
    df["status_text"] = df["status"].map({0: "鏈紑鎾?, 1: "鐩存挱涓?})

    # 閫夋嫨骞堕噸鍛藉悕鍒?
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
        "鎺掑悕",
        "涓绘挱",
        "鎬昏",
        "绮変笣鏁?,
        "鐘舵€?,
        "鏈夋晥澶╂暟",
        "鐩存挱鏃堕暱",
        "鑸伴暱",
        "鎻愮潱",
        "鎬荤潱",
        "绀肩墿",
        "SC",
        "涓婅埌",
    ]

    # 鏍煎紡鍖栨暟鍊硷紙甯﹂€楀彿锛屽皬鏁扮偣1浣嶏級
    for col in ["绀肩墿", "SC", "涓婅埌", "鎬昏"]:
        df_table[col] = df_table[col].apply(lambda x: f"{float(x):,.1f}")

    # 鈹€鈹€ matplotlib 琛ㄦ牸 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    # plt.rcParams["axes.unicode_minus"] = False

    n_rows = len(df_table)
    n_cols = len(df_table.columns)

    # 鍔ㄦ€佸昂瀵?
    height_per_row = 0.65
    fig_height = 0.8 + n_rows * height_per_row
    fig_width = max(12.0, min(22.0, 10 + n_cols * 1.05))

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))  # 瀹藉害鍙牴鎹垪鏁拌皟澶?
    # 鐣欏嚭鏇村涓婃柟绌洪棿缁欐爣棰?
    # plt.subplots_adjust(top=0.92, bottom=0.05, left=0.05, right=0.95)
    # fig.suptitle(
    #     "2026骞?1鏈?PSPlive 涓绘挱鏁版嵁鎺掕姒淺n(鎸夋€昏闄嶅簭 | 鍒锋柊鏃堕棿: 2026-01-31 08:58:45)",
    #     fontsize=14,
    #     fontweight="bold",
    #     y=0.96,  # 0.92 ~ 0.98 涔嬮棿璋冩暣锛岃秺澶ц秺闈犱笂
    # )
    ax.axis("off")

    # 鍒涘缓琛ㄦ牸
    table = ax.table(
        cellText=df_table.values, # type: ignore
        colLabels=df_table.columns, # type: ignore
        loc="upper center",
        bbox=[0.01, 0.01, 1.0, 0.96],  # 绋嶅井涓嬬Щ涓€鐐?# type: ignore
        cellLoc="center",
        colLoc="center",
        edges="closed",
    )

    for (i, j), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=my_font)  # 鉁?姝ｇ‘鏂规硶
        # 鍙€夛細璁剧疆鍔犵矖琛ㄥご

    table.auto_set_font_size(False)
    table.set_fontsize(16)

    table.scale(1.3, 1.5)  # 璋冩暣鏁翠綋姣斾緥
    table.auto_set_column_width(col=list(range(len(df_table.columns))))

    # 鐒跺悗閽堝鐗瑰畾鍒楄繘琛屽井璋冿紙鍗曚綅鏄?瀛椾綋澶у皬鐨勫€嶆暟锛屽ぇ绾?0.1~2.0 涔嬮棿甯歌锛?
    col_widths = {
        0: 0.6,  # 鎺掑悕 - 寰堢獎
        1: 1.8,  # 鎬昏 - 鏈€瀹?
        2: 1.4,  # 涓绘挱鍚?- 姣旇緝瀹?
        3: 0.9,  # 绮変笣鏁?
        4: 0.7,  # 鐘舵€?
        5: 0.8,  # 鏈夋晥澶╂暟
        6: 1.1,  # 鐩存挱鏃堕暱
        7: 0.6,  # 鑸伴暱
        8: 0.6,  # 鎻愮潱
        9: 0.6,  # 鎬荤潱
        10: 1.0,  # 绀肩墿
        11: 1.0,  # SC
        12: 1.2,  # 涓婅埌
    }

    for col_idx, width_factor in col_widths.items():
        table.auto_set_column_width(col_idx)  # 鍏堣嚜鍔ㄤ竴娆?
        # 鍐嶆墜鍔ㄤ箻浠ュ洜瀛愯繘琛屽井璋?
        for row in range(len(df_table) + 1):  # +1 鍖呭惈琛ㄥご
            cell = table[(row, col_idx)]
            cell.set_width(width_factor * 0.018)  # 0.018 鏄粡楠屽€硷紝鍙牴鎹瓧浣撳ぇ灏忚皟鏁?

    # 琛ㄥご鏍峰紡
    for j in range(len(df_table.columns)):
        cell = table[0, j]
        cell.set_facecolor("#00BFFF")
        cell.set_text_props(color="white", weight="bold",
                            fontproperties=my_font)

    # 浜ゆ浛琛岃儗鏅?+ 鐩存挱涓珮浜?
    for i in range(len(df_table)):
        for j in range(len(df_table.columns)):
            cell = table[i + 1, j]
            if i % 2 == 1:
                cell.set_facecolor("#f5f5f5")
            if df_table.iloc[i]["鐘舵€?] == "鐩存挱涓? and df_table.columns[j] == "鐘舵€?:
                cell.set_text_props(color="red", weight="bold")
            # 鏁板€煎垪鍙冲榻?
            if df_table.columns[j] in [
                "绀肩墿",
                "SC",
                "涓婅埌",
                "鎬昏",
                "绮変笣鏁?,
                "鑸伴暱",
                "鎻愮潱",
                "鎬荤潱",
                "鏈夋晥澶╂暟",
            ]:
                cell.set_text_props(ha="right", fontproperties=my_font)

    # 鏍囬
    filter_to_category = {
        "all": "VR+PSP",
        "psp": "PSP",
        "vr": "VR",
    }
    title = f"{data.get('month', beijing_now_str('%Y%m'))} {filter_to_category[data['filter']]}涓绘挱鏁版嵁鎺掕姒淺n(鎸夋€昏闄嶅簭 | 鍒锋柊鏃堕棿: {to_beijing_time_str(data.get('refresh_time', ''))})"
    plt.title(title, fontsize=20, fontweight="bold",
              pad=0, fontproperties=my_font)

    # plt.tight_layout()

    # 淇濆瓨鍥剧墖锛坉pi瓒婇珮瓒婃竻鏅帮級
    if not os.path.exists("imgs"):
        os.makedirs("imgs")
    save_path = f"imgs/revenue_rank_{data.get('month', beijing_now_str('%Y%m'))}_{data['filter']}_{beijing_now_str('%Y%m%d%H%M%S')}.png"
    plt.savefig(save_path, dpi=50, bbox_inches="tight")
    print(f"鍥剧墖宸蹭繚瀛樺埌 {save_path}")
    return save_path


@command("鏂楄櫕", "revenue_rank")
class RevenueRankCommand(Command):
    name = "revenue_rank"
    cn_name = "鏂楄櫕"

    @cooldown(60)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Executing {self.name} command with args: {args}")

        # 鍒濆鍖栭粯璁ゅ€?
        filter = "vr"
        month = beijing_now_str("%Y%m")
        top_n = None

        # 瑙ｆ瀽鍛藉悕鍙傛暟 /f /m /n
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

        # 楠岃瘉鍙傛暟
        if filter not in ["vr", "psp", "all"]:
            await self.send_reply(message, "杩囨护鍣ㄩ敊璇紝璇蜂娇鐢╲r/psp/all")
            return

        if not month.isdigit() or len(month) != 6:
            await self.send_reply(message, "鏈堜唤鏍煎紡閿欒锛岃浣跨敤YYYYMM鏍煎紡")
            return

        if top_n is not None:
            if not top_n.isdigit():
                await self.send_reply(message, "鏄剧ず鏁伴噺閿欒锛岃浣跨敤鏁板瓧")
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
            await self.send_reply(message, "鑾峰彇鏁版嵁澶辫触锛岃绋嶅悗鍐嶈瘯")
            return

        await self.send_reply(
            message, f"姝ｅ湪鐢熸垚{month} {filter}涓绘挱鏁版嵁鎺掕姒滐紝璇风◢鍚庘€︹€?
        )
        try:
            path = draw_rank_table(data, top_n) # type: ignore
            print(f"File size: {os.path.getsize(path) / 1024} KB")
        except Exception as e:
            _log.error(f"Failed to draw rank table: {e}")
            await self.send_reply(message, "鐢熸垚鎺掕姒滃け璐ワ紝璇风◢鍚庡啀璇?)
            return

        # 涓婁紶鍥剧墖
        # async with AsyncShuimoImageClient() as client:
        #     result = await client.upload_image(path, folder="img")
        #     data = result.get("data", {})

        # retry = 3
        # while retry > 0:
        #     data = await upload_image(path, cdn_domain="cloudflareimg.cdn.sn")

        #     await asyncio.sleep(1)  # 绛夊緟鍥剧墖涓婁紶鎴愬姛
        #     if data is not None:
        #         break
        #     retry -= 1
        # if retry == 0:
        #     await self.send_reply(message, "涓婁紶鍥剧墖澶辫触, 璇风◢鍚庡啀璇?)
        #     return

        # # 鍒犻櫎鏈湴鍥剧墖鏂囦欢
        # try:
        #     os.remove(path)
        # except Exception as e:
        #     _log.error(f"Failed to remove local image file: {e}")

        # if data is None or "url" not in data or data.get("success", False) is not True:
        #     await self.send_reply(message, "涓婁紶鍥剧墖澶辫触, 璇风◢鍚庡啀璇?)
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
        # 鍒犻櫎鏂囦欢
        try:
            os.remove(path)
        except Exception as e:
            _log.error(f"Failed to remove local image file: {e}")
        return


revenue_rank_help_str = dedent("""\
    鏂楄櫕 鎸囦护鐢ㄦ硶:
    鏀跺埌鎸囦护鍚庯紝鐢熸垚鎸囧畾鏈堜唤鍜岀被鍒殑涓绘挱鏀跺叆鎺掕姒滃浘鐗囧苟涓婁紶銆?
    
    鎸囦护鏍煎紡:
    鏂楄櫕 /f <filter> /m <month> /n <top_n>
    
    鍙傛暟璇存槑:
    /f <filter>   杩囨护鍣紝鎸囧畾绫诲埆銆傚彲閫夊€?
                  vr - 浠匳R涓绘挱(榛樿)
                  psp - 浠匬SP涓绘挱
                  all - VR+PSP涓绘挱
    
    /m <month>    鎸囧畾鏈堜唤锛屾牸寮忎负YYYYMM銆備緥濡? 202601琛ㄧず2026骞?鏈堛€傞粯璁や负褰撳墠鏈堜唤銆?
    
    /n <top_n>    鏄剧ず鍓峃鍚嶄富鎾殑鏁版嵁銆傚鏋滀笉鎸囧畾锛屽垯鏄剧ず鍏ㄩ儴涓绘挱銆?
    
    绀轰緥:
    鏂楄櫕 /f vr /m 202601 /n 20
    鐢熸垚2026骞?鏈圴R涓绘挱鏀跺叆鎺掕姒滐紝鏄剧ず鍓?0鍚嶄富鎾殑鏁版嵁銆?
"""
                               )


@command("鏂楄櫕甯姪", "revenue_rank_help")
class RevenueRankHelpCommand(Command):
    name = "revenue_rank_help"
    cn_name = "鏂楄櫕甯姪"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, revenue_rank_help_str)
        return




