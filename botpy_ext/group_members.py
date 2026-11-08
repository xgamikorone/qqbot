"""Optional group member lookup through the SDK's authenticated transport."""

import asyncio
import dataclasses
import json

from botpy import api as botpy_api
from botpy import errors as botpy_errors
from botpy import http as botpy_http


@dataclasses.dataclass(frozen=True)
class MemberName:
    """A display name result, without granting any group permissions."""

    name: str = ""
    permission_denied: bool = False


async def fetch_member_name(
    api: botpy_api.BotAPI, group_id: str, member_id: str
) -> MemberName:
    """Best-effort member lookup; never logs raw responses or exceptions."""
    try:
        async with asyncio.timeout(2):
            result = await api._http.request(
                botpy_http.Route(
                    "GET",
                    "/v2/groups/{group_openid}/members/{member_openid}",
                    group_openid=group_id,
                    member_openid=member_id,
                )
            )
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict):
            return MemberName()
        if result.get("code") in {11253, "11253"}:
            return MemberName(permission_denied=True)
        if result.get("code", 0) not in {0, "0"}:
            return MemberName()
        name = result.get("username")
        return MemberName(name.strip() if isinstance(name, str) else "")
    except Exception as error:
        # SDK exceptions may discard the numeric API code; recognize its
        # permission exception or known permission message without logging it.
        denied = (
            isinstance(error, botpy_errors.ForbiddenError)
            or "11253" in str(error)
            or "应用无接口访问权限" in str(error)
        )
        return MemberName(permission_denied=denied)
