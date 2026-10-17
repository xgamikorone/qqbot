"""Async Baidu general translation adapter; never log signed request data."""

import asyncio
from dataclasses import dataclass
from hashlib import md5
import os
import secrets

import aiohttp


TRANSLATE_URL = "https://api.fanyi.baidu.com/api/trans/vip/translate"
MAX_TEXT_LENGTH = 1000  # Conservative bot-side cap, independent of paid plan.
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5)


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
        messages = {
            "52001": "翻译服务超时，请稍后再试。",
            "52002": "翻译服务暂时不可用，请稍后再试。",
            "52003": "翻译服务尚未授权，请联系管理员检查应用及服务开通状态。",
            "54001": "翻译服务鉴权失败，请联系管理员检查配置。",
            "54003": "翻译请求过于频繁，请稍后再试。",
            "54004": "翻译服务额度或余额不足，请联系管理员。",
            "54005": "翻译请求过于频繁，请稍后再试。",
            "58000": "翻译服务 IP 配置有误，请联系管理员。",
            "58001": "不支持该翻译语言方向，请检查语言代码。",
            "58002": "翻译服务已关闭，请联系管理员。",
            "90107": "翻译服务认证尚未生效，请联系管理员。",
            "20003": "该文本无法翻译，请调整内容后再试。",
        }
        # Never echo error_msg: providers may include original request details.
        raise TranslationError(messages.get(code, "翻译服务拒绝了请求，请稍后重试或联系管理员。"))
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
