import asyncio
import os
from dataclasses import dataclass
import aiohttp

class ChatError(Exception):
    """Safe user-facing failure."""

@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

class ModelClient:
    """OpenAI-compatible text adapter; no tools, streaming or retries."""
    def __init__(self, config):
        self.config = config
        self.session = None

    async def generate(self, messages):
        key = os.getenv("CHAT_API_KEY") or os.getenv("ZHIPU_API_KEY", "")
        if not key or key.startswith("your_"):
            raise ChatError("聊天模型尚未配置，请联系管理员。")
        base = os.getenv("CHAT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").strip().rstrip("/")
        if not base.startswith("https://"):
            raise ChatError("聊天模型地址必须使用 HTTPS。")
        model = os.getenv("CHAT_MODEL", "glm-4.5-flash")
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.request_timeout_seconds))
        try:
            async with self.session.post(base + "/chat/completions", headers={"Authorization": "Bearer " + key}, json={"model": model, "messages": messages, "stream": False, "max_tokens": self.config.max_output_tokens}, allow_redirects=False) as response:
                if response.status in (401, 403):
                    raise ChatError("聊天模型鉴权失败，请联系管理员。")
                if response.status == 429:
                    raise ChatError("聊天模型限流或额度不足，请稍后再试。")
                if response.status != 200:
                    raise ChatError("聊天模型暂时不可用。")
                data = await response.json()
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ChatError("模型未返回有效回答。")
            usage = data.get("usage") or {}
            return GenerationResult(text, model, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        except asyncio.TimeoutError:
            raise ChatError("聊天模型请求超时，请稍后再试。") from None
        except (aiohttp.ClientError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ChatError("聊天模型连接失败或返回格式异常。") from None

    async def close(self):
        if self.session is not None:
            await self.session.close()
