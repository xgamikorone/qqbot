"""Local-only authenticated control panel for selected QQ Bot API operations."""

import base64
import binascii
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiohttp import web

from admin_operations import AdminOperation, get_operation, list_operations


_log = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).resolve().parent / "admin_ui"
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class OperationInputError(ValueError):
    """A browser supplied invalid input for an allowed operation."""


def _decode_field(field_kind: str, value: Any) -> Any:
    if field_kind in {"text", "textarea"}:
        if not isinstance(value, str):
            raise OperationInputError("文本参数必须是字符串")
        return value
    if field_kind == "number":
        if isinstance(value, bool):
            raise OperationInputError("数字参数不能是布尔值")
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise OperationInputError("数字参数必须是整数") from error
    if field_kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise OperationInputError("布尔参数必须是 true 或 false")
    if field_kind in {"json", "permission"}:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as error:
                raise OperationInputError("JSON 参数格式错误") from error
        if not isinstance(value, (dict, list)):
            raise OperationInputError("JSON 参数必须是对象或数组")
        if field_kind == "permission":
            if not isinstance(value, dict):
                raise OperationInputError("权限参数必须是 JSON 对象")
            from botpy.flags import Permission

            try:
                return Permission(**value)
            except (TypeError, ValueError) as error:
                raise OperationInputError("权限参数无效") from error
        return value
    if field_kind == "file":
        if not isinstance(value, str) or ";base64," not in value:
            raise OperationInputError("文件必须使用 base64 编码")
        try:
            encoded = value.split(";base64,", 1)[1]
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise OperationInputError("文件编码无效") from error
        if len(decoded) > _MAX_UPLOAD_BYTES:
            raise OperationInputError("文件不能超过 8 MB")
        return decoded
    raise OperationInputError("不支持的参数类型")


async def invoke_operation(
    client: Any, operation: AdminOperation | None, payload: dict[str, Any]
) -> Any:
    if operation is None:
        raise OperationInputError("不允许调用该操作")
    if not isinstance(payload, dict):
        raise OperationInputError("请求体必须是 JSON 对象")

    fields = {field.name: field for field in operation.fields}
    unknown_fields = set(payload) - set(fields)
    if unknown_fields:
        raise OperationInputError(f"未知参数: {', '.join(sorted(unknown_fields))}")

    arguments: dict[str, Any] = {}
    for name, definition in fields.items():
        value = payload.get(name)
        if value is None or value == "":
            if definition.required:
                raise OperationInputError(f"缺少参数: {definition.label}")
            continue
        decoded = _decode_field(definition.kind, value)
        if definition.expand:
            if not isinstance(decoded, dict):
                raise OperationInputError(f"{definition.label} 必须是 JSON 对象")
            overlap = set(arguments) & set(decoded)
            if overlap:
                raise OperationInputError(f"{definition.label} 不能覆盖已有参数")
            arguments.update(decoded)
        else:
            arguments[name] = decoded

    api_method = getattr(client.api, operation.api_method, None)
    if api_method is None or not callable(api_method):
        raise OperationInputError("当前 Bot SDK 不支持该操作")
    return await api_method(**arguments)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class BotAdminServer:
    def __init__(self, client: Any):
        self.client = client
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._token = os.getenv("BOT_ADMIN_TOKEN", "").strip()

    @property
    def running(self) -> bool:
        return self._site is not None

    async def start(self) -> bool:
        if self.running:
            return True
        if not self._token or self._token.startswith("your_"):
            _log.warning("Bot admin panel is disabled: BOT_ADMIN_TOKEN is not configured")
            return False

        host = os.getenv("BOT_ADMIN_HOST", "127.0.0.1").strip()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            _log.error("Bot admin panel must bind to localhost, got %s", host)
            return False
        try:
            port = int(os.getenv("BOT_ADMIN_PORT", "8090"))
        except ValueError:
            _log.error("BOT_ADMIN_PORT must be an integer")
            return False

        application = web.Application(middlewares=[self._auth_middleware])
        application.router.add_get("/", self._index)
        application.router.add_get("/api/status", self._status)
        application.router.add_get("/api/operations", self._operations)
        application.router.add_post("/api/operations/{operation_id}", self._invoke)
        application.router.add_static("/assets", _STATIC_DIR)
        self._runner = web.AppRunner(application)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=host, port=port)
        await self._site.start()
        _log.info("Bot admin panel started at http://%s:%s", host, port)
        return True

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        if request.path.startswith("/api/"):
            authorization = request.headers.get("Authorization", "")
            expected = f"Bearer {self._token}"
            if not hmac.compare_digest(authorization, expected):
                raise web.HTTPUnauthorized(text="管理令牌无效")
        return await handler(request)

    async def _index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(_STATIC_DIR / "index.html")

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ready", "operations": len(list_operations())})

    async def _operations(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"operations": [operation.as_dict() for operation in list_operations()]}
        )

    async def _invoke(self, request: web.Request) -> web.Response:
        operation = get_operation(request.match_info["operation_id"])
        if operation is None:
            raise web.HTTPNotFound(text="未知操作")
        try:
            payload = await request.json()
            result = await invoke_operation(self.client, operation, payload)
        except json.JSONDecodeError as error:
            raise web.HTTPBadRequest(text="请求体必须是 JSON") from error
        except OperationInputError as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        except Exception:
            _log.exception("Admin operation failed: %s", operation.id)
            raise web.HTTPBadGateway(text="QQ API 调用失败，请查看机器人日志") from None
        return web.json_response({"operation": operation.id, "result": _json_safe(result)})
