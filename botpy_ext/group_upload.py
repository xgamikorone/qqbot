"""Local group image uploads using QQ's multipart upload protocol."""

import asyncio
import dataclasses
import hashlib
import json
import logging
import pathlib
import urllib.parse

import aiohttp
from botpy import api as botpy_api
from botpy import http as botpy_http
from botpy.types import message as message_types

# Stay below the image soft limit rather than silently uploading as a file.
MAX_IMAGE_BYTES = 20_000_000
MD5_PREFIX_BYTES = 10_002_432
_LOG = logging.getLogger(__name__)


@dataclasses.dataclass
class UploadProgress:
    """Safe diagnostic state, containing no URLs or remote response values."""

    stage: str = "read"


async def upload_group_image(api: botpy_api.BotAPI, group_id: str,
                             path: str) -> message_types.Media:
    """Uploads an image and reports safe stage diagnostics on failure."""
    progress = UploadProgress()
    try:
        return await _upload_group_image(api, group_id, path, progress)
    except Exception as error:
        # Only our fixed validation messages are safe to log. SDK/network
        # exceptions can contain credentials, URLs or remote response bodies.
        safe_reasons = {
            "图片为空或超过 20 MB",
            "不支持的图片扩展名",
            "无效的预上传响应",
            "预上传响应缺少 upload_id",
            "预上传响应缺少分片列表",
            "无效的分片",
            "无效的分片大小",
            "无效的分片序号或地址",
            "分片地址必须为 HTTPS URL",
            "分片数量与文件大小不符",
            "分片顺序或大小与文件不符",
            "分片 PUT 失败",
            "上传控制请求失败",
            "合并响应无效",
            "合并响应缺少 file_info",
            "上传响应不是有效 JSON",
        }
        reason = str(error)
        reason = reason if reason in safe_reasons else type(error).__name__
        _LOG.error("群图片上传失败: stage=%s reason=%s", progress.stage, reason)
        raise


@dataclasses.dataclass(frozen=True)
class UploadPart:
    """Validated part of a server-provided upload plan."""

    index: int
    size: int
    url: str


def _snapshot(path: pathlib.Path) -> bytes:
    with path.open("rb") as source:
        data = source.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("图片为空或超过 20 MB")
    return data


def _positive_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("无效的分片大小")
    result = int(value)
    if result <= 0:
        raise ValueError("无效的分片大小")
    return result


def _plan(value: object, size: int) -> tuple[str, list[UploadPart]]:
    """Checks the untyped SDK response before reading or uploading chunks."""
    if not isinstance(value, dict):
        raise ValueError("无效的预上传响应")
    upload_id, raw_parts = value.get("upload_id"), value.get("parts")
    if not isinstance(upload_id, str) or not upload_id:
        raise ValueError("预上传响应缺少 upload_id")
    block_size = _positive_size(value.get("block_size"))
    if not isinstance(raw_parts, list):
        raise ValueError("预上传响应缺少分片列表")
    parts: list[UploadPart] = []
    for raw in raw_parts:
        if not isinstance(raw, dict):
            raise ValueError("无效的分片")
        index, url = raw.get("index"), raw.get("presigned_url")
        if type(index) is not int or not isinstance(url, str):
            raise ValueError("无效的分片序号或地址")
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password):
            raise ValueError("分片地址必须为 HTTPS URL")
        parts.append(
            UploadPart(index, _positive_size(raw.get("block_size")), url))
    parts.sort(key=lambda part: part.index)
    expected_count = (size + block_size - 1) // block_size
    if len(parts) != expected_count:
        raise ValueError("分片数量与文件大小不符")
    for index, part in enumerate(parts):
        if part.index != index or part.size != min(block_size,
                                                   size - index * block_size):
            raise ValueError("分片顺序或大小与文件不符")
    return upload_id, parts


async def _put(session: aiohttp.ClientSession, url: str, data: bytes) -> None:
    """Retries only idempotent PUTs, without QQ auth or redirect following."""
    for attempt in range(3):
        try:
            async with session.put(url, data=data,
                                   allow_redirects=False) as response:
                if not 200 <= response.status < 300:
                    raise ValueError("分片 PUT 失败")
                return
        except (aiohttp.ClientError, TimeoutError, ValueError):
            if attempt == 2:
                raise
            await asyncio.sleep(1)


async def _upload_group_image(api: botpy_api.BotAPI, group_id: str, path: str,
                              progress: UploadProgress) -> message_types.Media:
    """Uploads a local image and returns media without sending a message.

    The authenticated SDK transports QQ control requests. A separate HTTP
    session sends the immutable local snapshot to presigned storage URLs.
    Serial parts respect server concurrency limits; total time is bounded
    to leave room within the passive reply window. No URLs are logged.
    """
    async with asyncio.timeout(240):
        image_path = pathlib.Path(path)
        if image_path.suffix.lower() not in {
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"
        }:
            raise ValueError("不支持的图片扩展名")
        data = await asyncio.to_thread(_snapshot, image_path)
        prefix = "/v2/groups/{group_openid}"

        async def control(suffix: str, payload: dict[str, object]) -> object:
            # qq-botpy exposes no multipart methods; reuse its authenticated
            # transport instead of reading credentials or opening a bot client.
            result = await api._http.request(botpy_http.Route(
                "POST", prefix + suffix, group_openid=group_id),
                                             json=payload)
            # qq-botpy only calls response.json() for an exact
            # application/json header; headers with charset return text.
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except ValueError:
                    raise ValueError("上传响应不是有效 JSON") from None
            if result is None or (isinstance(result, dict) and
                                  result.get("code", 0) != 0):
                raise ValueError("上传控制请求失败")
            return result

        progress.stage = "prepare"
        prepared = await control(
            "/upload_prepare", {
                "file_type": 1,
                "file_size": str(len(data)),
                "file_name": image_path.name,
                "md5": hashlib.md5(data).hexdigest(),
                "sha1": hashlib.sha1(data).hexdigest(),
                "md5_10m": hashlib.md5(data[:MD5_PREFIX_BYTES]).hexdigest(),
            })
        progress.stage = "plan"
        upload_id, parts = _plan(prepared, len(data))
        _LOG.info("群图片预上传完成: bytes=%s parts=%s", len(data), len(parts))
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False,
        ) as session:
            offset = 0
            for part in parts:
                chunk = data[offset:offset + part.size]
                progress.stage = "put"
                await _put(session, part.url, chunk)
                progress.stage = "confirm"
                await control(
                    "/upload_part_finish", {
                        "upload_id": upload_id,
                        "part_index": part.index,
                        "block_size": str(len(chunk)),
                        "md5": hashlib.md5(chunk).hexdigest(),
                    })
                offset += len(chunk)
        progress.stage = "merge"
        media = await control(
            "/files", {
                "file_type": 1,
                "file_name": image_path.name,
                "upload_id": upload_id,
                "srv_send_msg": False,
            })
        progress.stage = "media"
        if not isinstance(media, dict):
            raise ValueError("合并响应无效")
        info = media.get("file_info")
        if not isinstance(info, str) or not info:
            raise ValueError("合并响应缺少 file_info")
        # SDK Media declares these response metadata fields required, even
        # though only file_info is consumed by message sending.
        return {
            "file_info": info,
            "file_uuid": str(media.get("file_uuid", "")),
            "ttl": int(media.get("ttl", 0))
        }
