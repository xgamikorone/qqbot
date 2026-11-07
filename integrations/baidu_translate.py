"""Async Baidu general translation adapter; never log signed request data."""

import asyncio
from dataclasses import dataclass
from hashlib import md5
import logging
import os
import secrets

import aiohttp


TRANSLATE_URL = "https://api.fanyi.baidu.com/api/trans/vip/translate"
MAX_TEXT_LENGTH = 1000  # Conservative bot-side cap, independent of paid plan.
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5)
_log = logging.getLogger(__name__)

# Meanings from the supplied official error-code table, not error_msg echoes.
ERROR_DETAILS = {
    "52001": ("请求超时", "检查原文及源/目标语言是否受支持，稍后再试。"),
    "52002": ("系统错误", "请稍后再试。"),
    "52003": ("未授权用户", "请联系管理员检查 APPID 和对应服务是否已开通。"),
    "54000": ("必填参数为空", "请联系管理员检查是否漏传或误传参数。"),
    "54001": ("签名错误", "鉴权失败，请联系管理员检查密钥配置及签名生成方法。"),
    "54003": ("访问频率受限", "调用过于频繁，请降低频率或联系管理员检查服务版本。"),
    "54004": ("账户余额不足", "请联系管理员检查余额；当天用量费用也可能已超过账户余额。"),
    "54005": ("长 query 请求频繁", "请降低长文本请求频率，至少等待 3 秒后再试。"),
    "58000": ("客户端 IP 非法", "请联系管理员检查服务器 IP 与平台配置是否一致；动态 IP 可按平台说明留空。"),
    "58001": ("译文语言方向不支持", "请检查语言代码及账号版本支持的语言范围。"),
    "58002": ("服务当前已关闭", "请联系管理员在百度翻译管理控制台开启服务。"),
    "58003": ("此 IP 已被封禁", "同一 IP 当日使用多个 APPID 可能触发封禁，次日解封；请联系管理员排查。"),
    "90107": ("认证未通过或未生效", "请联系管理员查看百度翻译平台认证进度。"),
    "20003": ("请求内容存在安全风险", "请调整原文内容后再试。"),
}


class TranslationError(ValueError):
    """A safe, user-facing message without upstream response or credentials."""


@dataclass(frozen=True)
class TranslationResult:
    source: str
    target: str
    text: str


def build_payload(appid: str, appkey: str, text: str, source: str, target: str) -> dict:
    salt = secrets.token_hex(16)
    sign = md5((appid + text + salt + appkey).encode("utf-8")).hexdigest()
    return {"appid": appid, "q": text, "from": source, "to": target, "salt": salt, "sign": sign}


def parse_response(payload: object) -> TranslationResult:
    if not isinstance(payload, dict):
        raise TranslationError("翻译服务返回了无效数据，请稍后再试。")
    code = str(payload.get("error_code", "52000"))
    if code != "52000":
        meaning, advice = ERROR_DETAILS.get(code, (
            "未知错误", "翻译服务拒绝了请求，请稍后重试或联系管理员检查官方错误码说明。",
        ))
        safe_code = code if len(code) == 5 and code.isascii() and code.isdigit() else "未知"
        message = f"百度翻译失败（{safe_code}：{meaning}）\n处理建议：{advice}"
        _log.warning("%s", message)
        raise TranslationError(message)
    items = payload.get("trans_result")
    if not isinstance(items, list) or not items or any(
        not isinstance(item, dict) or not isinstance(item.get("dst"), str)
        for item in items
    ):
        raise TranslationError("翻译服务未返回有效译文，请稍后再试。")
    text = "\n".join(item["dst"] for item in items)
    if not text.strip():
        raise TranslationError("翻译服务未返回有效译文，请稍后再试。")
    source, target = payload.get("from"), payload.get("to")
    if not isinstance(source, str) or not isinstance(target, str):
        raise TranslationError("翻译服务返回了无效数据，请稍后再试。")
    return TranslationResult(source, target, text)


async def translate(text: str, source: str = "auto", target: str = "zh") -> TranslationResult:
    if not text.strip():
        raise TranslationError("请输入要翻译的文本。")
    if len(text) > MAX_TEXT_LENGTH:
        raise TranslationError(f"单次最多翻译 {MAX_TEXT_LENGTH} 个字符，请分段发送。")
    appid = os.getenv("BAIDU_TRANSLATE_APP_ID", "").strip()
    appkey = os.getenv("BAIDU_TRANSLATE_APP_KEY", "").strip()
    if not appid or not appkey or appid.startswith("your_") or appkey.startswith("your_"):
        raise TranslationError("翻译功能尚未配置，请联系管理员。")
    payload = build_payload(appid, appkey, text, source, target)
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            # Form body, not URL params: avoid putting text/signatures in URLs.
            async with session.post(TRANSLATE_URL, data=payload, allow_redirects=False) as response:
                if response.status != 200:
                    raise TranslationError("翻译服务暂时不可用，请稍后再试。")
                result = await response.json(content_type=None)
    except asyncio.TimeoutError:
        raise TranslationError("翻译请求超时，请稍后再试。") from None
    except (aiohttp.ClientError, ValueError) as error:
        if isinstance(error, TranslationError):
            raise
        raise TranslationError("无法连接翻译服务或响应格式异常，请稍后再试。") from None
    return parse_response(result)
