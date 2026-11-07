from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

import aiohttp


DEFAULT_MAX_AGE_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 10


class LiveMonitorError(RuntimeError):
    """Live Monitor 健康检查无法完成或响应无效。"""


@dataclass(frozen=True)
class MonitorComponentHealth:
    name: str
    healthy: bool
    status: str
    age_seconds: float | None


@dataclass(frozen=True)
class LiveMonitorHealth:
    healthy: bool
    status: str
    components: tuple[MonitorComponentHealth, ...]

    def render(self) -> str:
        overall = "正常" if self.healthy else "异常"
        lines = [f"Live Monitor：{overall}（{self.status}）"]
        for component in self.components:
            state = "正常" if component.healthy else "异常"
            age = (
                f"，心跳 {component.age_seconds:.1f} 秒前"
                if component.age_seconds is not None
                else ""
            )
            lines.append(f"- {component.name}：{state}（{component.status}{age}）")
        return "\n".join(lines)


async def check_live_monitor_health(
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> LiveMonitorHealth:
    """使用仓库根目录 .env 已加载的配置检查 Live Monitor。"""

    if not 5 <= max_age_seconds <= 300:
        raise ValueError("max_age_seconds must be between 5 and 300")

    base_url = os.getenv("LIVE_MONITOR_BASE_URL")
    token = os.getenv("LIVE_MONITOR_API_TOKEN")
    if not base_url:
        raise LiveMonitorError("缺少 LIVE_MONITOR_BASE_URL 配置")
    if not token:
        raise LiveMonitorError("缺少 LIVE_MONITOR_API_TOKEN 配置")

    status_code, payload = await _request_health(
        base_url=base_url,
        token=token,
        max_age_seconds=max_age_seconds,
    )
    if status_code not in {200, 503}:
        raise LiveMonitorError(f"健康检查返回意外状态码 {status_code}")
    return _parse_health(payload, status_code=status_code)


async def _request_health(
    *,
    base_url: str,
    token: str,
    max_age_seconds: int,
) -> tuple[int, Any]:
    timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base_url.rstrip('/')}/monitor/health",
                headers={"Authorization": f"Bearer {token}"},
                params={"max_age_seconds": max_age_seconds},
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as error:
                    raise LiveMonitorError("健康检查返回了无效 JSON") from error
                return response.status, payload
    except (aiohttp.ClientError, TimeoutError) as error:
        raise LiveMonitorError("无法连接 Live Monitor") from error


def _parse_health(payload: Any, *, status_code: int) -> LiveMonitorHealth:
    if not isinstance(payload, Mapping):
        raise LiveMonitorError("健康检查响应必须是 JSON 对象")

    raw_status = payload.get("status")
    raw_components = payload.get("components")
    if not isinstance(raw_status, str) or not isinstance(raw_components, Mapping):
        raise LiveMonitorError("健康检查响应缺少 status 或 components")

    components = tuple(
        _parse_component(name, value) for name, value in raw_components.items()
    )
    declared_healthy = raw_status.lower() == "healthy"
    healthy = (
        status_code == 200
        and declared_healthy
        and all(component.healthy for component in components)
    )
    return LiveMonitorHealth(
        healthy=healthy,
        status=raw_status,
        components=components,
    )


def _parse_component(name: Any, payload: Any) -> MonitorComponentHealth:
    if not isinstance(name, str) or not isinstance(payload, Mapping):
        raise LiveMonitorError("健康检查包含无效的组件信息")

    healthy = payload.get("healthy")
    status = payload.get("status")
    age_seconds = payload.get("age_seconds")
    if not isinstance(healthy, bool) or not isinstance(status, str):
        raise LiveMonitorError(f"组件 {name} 缺少 healthy 或 status")
    if age_seconds is not None and (
        isinstance(age_seconds, bool) or not isinstance(age_seconds, (int, float))
    ):
        raise LiveMonitorError(f"组件 {name} 的 age_seconds 无效")

    return MonitorComponentHealth(
        name=name,
        healthy=healthy,
        status=status,
        age_seconds=float(age_seconds) if age_seconds is not None else None,
    )
