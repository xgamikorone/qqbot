import asyncio
import logging
from typing import BinaryIO, cast
import uuid

from botpy.api import BotAPI
from botpy.http import Route
from botpy.types import message as message_types
from messaging import audits as message_audits

from .models import (
    GlobalMenuResponse, Menu, Panel, PanelCreatedResponse, PanelListResponse,
    PanelRecord, PanelScope, TargetType, VersionResponse, GenerateURLLinkResponse,
)

_LOG = logging.getLogger("botpy.channel_send")


def _log_id(value: object) -> str:
    """Bounds untrusted IDs; callers use repr formatting to escape controls."""
    return str(value)[:256] if value is not None and value != "" else "-"


class APIInputError(ValueError):
    """Invalid extension input, rejected before making an HTTP request."""


def _panel_route(method: str, panel_id: str, suffix: str = "") -> Route:
    # Panel IDs are opaque identifiers, not paths or query strings.
    if not isinstance(panel_id, str) or not panel_id or not all(
        char.isascii() and (char.isalnum() or char in "_-") for char in panel_id
    ):
        raise APIInputError("panel_id 必须是非空 ID，仅支持字母、数字、下划线和连字符")
    return Route(method, "/v2/panels/{panel_id}" + suffix, panel_id=panel_id)


def _scope(scope: str) -> None:
    if scope not in {"c2c", "group", "channel", "dm"}:
        raise APIInputError("scope 仅支持 c2c/group/channel/dm")


def _targets(user_openids, group_openids) -> dict:
    result = {}
    for key, value in (("user_openids", user_openids), ("group_openids", group_openids)):
        if value is not None:
            if not isinstance(value, list) or not 1 <= len(value) <= 20 or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise APIInputError(f"{key} 必须包含 1 到 20 个非空字符串")
            result[key] = value
    if len(result) > 1:
        raise APIInputError("user_openids 和 group_openids 不能同时传入")
    return result


def _configuration(value, name: str, maximum: int) -> None:
    if not isinstance(value, dict):
        raise APIInputError(f"{name} 必须是 JSON 对象")
    if "items" in value and (
        not isinstance(value["items"], list) or len(value["items"]) > maximum
        or any(not isinstance(item, dict) for item in value["items"])
    ):
        raise APIInputError(f"{name}.items 必须是对象数组，最多 {maximum} 项")


class ExtendedBotAPI(BotAPI):
    """Extend the installed BotAPI without replacing its HTTP client or credentials."""

    async def post_message(
        self,
        channel_id: str,
        content: str | None = None,
        embed: message_types.Embed | None = None,
        ark: message_types.Ark | None = None,
        message_reference: message_types.Reference | None = None,
        image: str | None = None,
        file_image: bytes | BinaryIO | str | None = None,
        msg_id: str | None = None,
        event_id: str | None = None,
        markdown: message_types.MarkdownPayload | None = None,
        keyboard: message_types.Keyboard | None = None,
    ) -> message_types.Message | None:
        """Sends with metadata-only attempt/result logs and no added retries.

        Arguments retain the SDK interface. Mode describes the supplied reply
        parameters, not QQ's private quota accounting. Content, image data,
        credentials, and exception response bodies are never logged here.
        """
        attempt_id = uuid.uuid4().hex[:12]
        mode = "reply" if msg_id else "event_reply" if event_id else "proactive"
        context = (
            attempt_id, _log_id(channel_id), mode, _log_id(msg_id),
        )
        _LOG.info(
            "QQ channel send start: attempt=%s channel_id=%r "
            "mode=%s msg_id=%r", *context,
        )
        try:
            result = await super().post_message(
                channel_id=channel_id, content=content, embed=embed, ark=ark,
                message_reference=message_reference, image=image,
                file_image=file_image, msg_id=msg_id, event_id=event_id,
                markdown=markdown, keyboard=keyboard,
            )
        except asyncio.CancelledError:
            _LOG.warning(
                "QQ channel send end: attempt=%s channel_id=%r "
                "mode=%s msg_id=%r status=cancelled_unknown", *context,
            )
            raise
        except Exception as error:
            _LOG.warning(
                "QQ channel send end: attempt=%s channel_id=%r "
                "mode=%s msg_id=%r status=error error_type=%s",
                *context, type(error).__name__,
            )
            raise
        # botpy's response typing does not include audit/error response bodies.
        response = cast(object, result)
        sent_id = response.get("id") if isinstance(response, dict) else None
        code = response.get("code") if isinstance(response, dict) else None
        if isinstance(sent_id, str) and sent_id:
            status = "sent"
        elif code in (304023, 304024):
            status = "audit"
        elif type(code) is int and code != 0:
            status = "rejected"
        else:
            status = "unknown"
        _LOG.info(
            "QQ channel send end: attempt=%s channel_id=%r "
            "mode=%s msg_id=%r status=%s message_id=%r code=%s audit_id=%r",
            *context, status,
            _log_id(sent_id if isinstance(sent_id, str) else None),
            code if type(code) is int else "-",
            _log_id(message_audits.audit_id_from_response(response)),
        )
        return result

    async def generate_url_link(
        self, callback_data: str | None = None,
    ) -> GenerateURLLinkResponse | None:
        """Generate a bot friend invitation URL (50 QPS).

        Optional callback_data (up to 32 characters) is returned by QQ when
        a user adds the bot via this URL. Event handling is a separate concern.
        """
        payload = {}
        if callback_data is not None:
            if not isinstance(callback_data, str) or len(callback_data) > 32:
                raise APIInputError("callback_data 必须是字符串，最多 32 个字符")
            payload["callback_data"] = callback_data
        return await self._http.request(Route("POST", "/v2/generate_url_link"), json=payload)

    async def get_global_menu(self) -> GlobalMenuResponse | None:
        """Query GET /v2/menu (30 QPM); menu may be null before configuration.

        SDK authentication, sandbox selection and error handling are reused.
        A None response follows botpy's existing timeout behavior. No menu is
        created or modified, and this method is never called automatically.
        """
        return await self._http.request(Route("GET", "/v2/menu"))

    async def update_global_menu(self, menu: Menu) -> VersionResponse | None:
        """Replace the complete global C2C menu (5 QPM)."""
        _configuration(menu, "menu", 10)
        return await self._http.request(Route("PUT", "/v2/menu"), json={"menu": menu})

    async def get_panels(
        self, scope: PanelScope, cursor: str | None = None, limit: int | None = None,
    ) -> PanelListResponse | None:
        """List panels in a scope, newest first (30 QPM)."""
        _scope(scope)
        params = {"scope": scope}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            if type(limit) is not int or not 1 <= limit <= 50:
                raise APIInputError("limit 必须是 1 到 50 的整数")
            params["limit"] = limit
        return await self._http.request(Route("GET", "/v2/panels"), params=params)

    async def create_panel(
        self, scope: PanelScope, target_type: TargetType, panel: Panel,
        user_openids: list[str] | None = None, group_openids: list[str] | None = None,
    ) -> PanelCreatedResponse | None:
        """Create a panel; only c2c/group support specific targets (10 QPM)."""
        _scope(scope)
        _configuration(panel, "panel", 20)
        targets = _targets(user_openids, group_openids)
        if target_type not in {"all", "specific"}:
            raise APIInputError("target_type 仅支持 all/specific")
        if target_type == "specific":
            expected = {"c2c": "user_openids", "group": "group_openids"}.get(scope)
            if expected is None or set(targets) != {expected}:
                raise APIInputError("specific 仅支持 c2c 的 user_openids 或 group 的 group_openids")
        elif targets:
            raise APIInputError("全局面板不能指定关联对象")
        return await self._http.request(Route("POST", "/v2/panels"), json={
            "scope": scope, "target_type": target_type, "panel": panel, **targets,
        })

    async def get_panel(self, panel_id: str) -> PanelRecord | None:
        """Get panel details and associated targets (30 QPM)."""
        return await self._http.request(_panel_route("GET", panel_id))

    async def update_panel(self, panel_id: str, panel: Panel) -> VersionResponse | None:
        """Replace panel contents without changing targets (10 QPM)."""
        _configuration(panel, "panel", 20)
        return await self._http.request(_panel_route("PUT", panel_id), json={"panel": panel})

    async def delete_panel(self, panel_id: str) -> dict | None:
        """Delete a panel, disabling it for all its targets (10 QPM)."""
        return await self._http.request(_panel_route("DELETE", panel_id))

    async def update_panel_targets(
        self, panel_id: str, op: str, user_openids: list[str] | None = None,
        group_openids: list[str] | None = None,
    ) -> dict | None:
        """Add/remove up to 20 targets on a specific c2c/group panel (60 QPM)."""
        if op not in {"add", "del"}:
            raise APIInputError("op 仅支持 add/del")
        targets = _targets(user_openids, group_openids)
        if not targets:
            raise APIInputError("必须指定 user_openids 或 group_openids")
        return await self._http.request(
            _panel_route("PUT", panel_id, "/target"), json={"op": op, **targets},
        )
