"""Read-only tools using fixed DeepSeek endpoints, never local page requests."""

import asyncio
import ipaddress
import json
import logging
from urllib import parse

import aiohttp

_LOG = logging.getLogger("botpy.chat_web")
_BASE = "https://api.deepseek.com/v1/tools/"


def public_url(value: object) -> str | None:
    """Accepts bounded public HTTPS URLs without embedded credentials."""
    if (not isinstance(value, str) or len(value) > 512 or any(
            character.isspace() or ord(character) < 32 for character in value)):
        return None
    try:
        url = parse.urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (url.scheme != "https" or not host or url.username or url.password or
                url.port not in (None, 443) or "." not in host or host.endswith(
                    (".localhost", ".local", ".internal"))):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except ValueError:
        return None


def definitions() -> list[dict[str, object]]:
    """Returns the only tools exposed to the model."""
    return [{
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    argument: {
                        "type": "string"
                    }
                },
                "required": [argument],
                "additionalProperties": False
            },
        }
    } for name, argument, description in (
        ("web_search", "query", "检索最新或不确定的信息，只传必要关键词，最多128字符。"),
        ("web_fetch", "url", "读取本轮搜索结果中已有的网页。"),
    )]


class WebTools:
    """Owns per-turn budgets and result URLs; only DeepSeek fetches webpages.

    No website receives the bot's credentials or local HTTP requests. Remote
    Fetch redirect/DNS behavior remains the search provider's responsibility.
    """

    def __init__(self, session: aiohttp.ClientSession, key: str,
                 max_searches: int, max_fetches: int,
                 context_chars: int) -> None:
        self.session = session
        self._key = key
        self.remaining = {"web_search": max_searches, "web_fetch": max_fetches}
        self.chars_left = context_chars
        self.sources: dict[str, str] = {}
        self.fetched: set[str] = set()
        self.failed = False

    async def _request(self, endpoint: str,
                       payload: dict[str, object]) -> dict[str, object]:
        async with self.session.post(
                _BASE + endpoint,
                json=payload,
                headers={"Authorization": "Bearer " + self._key},
                timeout=aiohttp.ClientTimeout(total=12),
                allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise ValueError("Search unavailable")
            body = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                body.extend(chunk)
                if len(body) > 262144:
                    raise ValueError("Search response too large")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("Invalid search response")
            return data

    async def execute(self, name: str, arguments: object) -> str:
        """Executes an allowlisted call, returning bounded untrusted material."""
        if name not in self.remaining or self.remaining[name] <= 0:
            self.failed = True
            return '{"error":"工具未知或调用预算已用完"}'
        self.remaining[name] -= 1
        try:
            if not isinstance(arguments, str) or len(arguments) > 2048:
                raise ValueError("Invalid arguments")
            args = json.loads(arguments)
            key = "query" if name == "web_search" else "url"
            if not isinstance(args, dict) or set(args) != {key}:
                raise ValueError("Invalid arguments")
            value = args[key]
            if self.chars_left < 100:
                raise ValueError("Context budget exhausted")
            if name == "web_search":
                if not isinstance(value,
                                  str) or not 1 <= len(value.strip()) <= 128:
                    raise ValueError("Invalid query")
                data = await self._request("search", {
                    "query": value.strip(),
                    "count": 3,
                    "need_content": False,
                })
                records = data.get("results")
                if not isinstance(records, list):
                    raise ValueError("Invalid results")
                results = []
                for item in records[:3]:
                    if not isinstance(item, dict):
                        continue
                    url = public_url(item.get("url"))
                    if url is None:
                        continue
                    title = " ".join(str(item.get("title", "")).split())[:100]
                    title = title.replace("<", "＜").replace(">", "＞")
                    summary = str(
                        item.get("summary") or item.get("snippet") or "")[:1200]
                    self.sources[url] = title
                    results.append({
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "date": str(item.get("date", ""))[:40]
                    })
                material: object = {"results": results}
            else:
                if public_url(value) is None or value not in self.sources:
                    raise ValueError("Fetch requires a search result URL")
                data = await self._request("fetch", {"url": value})
                content = data.get("content")
                if not isinstance(content, str):
                    raise ValueError("Invalid page content")
                self.fetched.add(value)
                material = {"url": value, "content": content[:4000]}
            text = json.dumps(material, ensure_ascii=False)[:self.chars_left]
            self.chars_left -= len(text)
            _LOG.info("Chat web tool completed: tool=%s chars=%d", name,
                      len(text))
            return json.dumps({"untrusted_web_data": text}, ensure_ascii=False)
        except (ValueError, TypeError, aiohttp.ClientError,
                asyncio.TimeoutError):
            self.failed = True
            _LOG.warning("Chat web tool failed: tool=%s", name)
            return '{"error":"联网查询失败或参数受限；不能声称已查证"}'

    def citations(self) -> str:
        """Builds plain-text citations only from actual returned URLs."""
        urls = [url for url in self.sources if url in self.fetched] or list(
            self.sources)
        references = (
            "\n\n来源：\n" +
            "\n".join(f"{index}. {self.sources[url]} {url}"
                      for index, url in enumerate(urls[:3], 1))) if urls else ""
        warning = "\n\n注：部分联网查询失败，未取得的资料不能视为已核实。" if self.failed else ""
        return references + warning
