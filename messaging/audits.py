"""Tracks scheduled submissions and asynchronous QQ audit outcomes."""

import asyncio
import logging
import uuid
from typing import Protocol

from database.repositories import message_audit_repository

_LOG = logging.getLogger("botpy.message_audit")


class MessageSender(Protocol):
    """Minimal interface at the untyped botpy response boundary."""

    async def post_message(self, channel_id: str, content: str) -> object:
        """Submits a channel message."""
        ...


def audit_id_from_response(response: object) -> str:
    """Extracts the audit ID without trusting SDK response annotations."""
    if not isinstance(response, dict):
        return ""
    data = response.get("data")
    audit = data.get("message_audit") if isinstance(data, dict) else None
    value = audit.get("audit_id") if isinstance(audit, dict) else None
    return value if isinstance(value, str) else ""


class MessageAuditTracker:
    """Tracks metadata only; pending or unknown outcomes are never resent."""

    def __init__(
            self, repository: message_audit_repository.MessageAuditRepository
    ) -> None:
        self._repository = repository

    async def send(self, sender: MessageSender, task_id: str, channel_id: str,
                   content: str) -> None:
        """Records one submission, raising for failed or unknown outcomes.

        A pending audit is an accepted submission, not proof of delivery.
        Database errors propagate and never trigger another network send.
        """
        attempt_id = uuid.uuid4().hex
        self._repository.start(attempt_id, task_id, channel_id)
        _LOG.info("Scheduled send start: attempt=%s task=%r channel_id=%r",
                  attempt_id, task_id, channel_id)
        try:
            response = await sender.post_message(channel_id=channel_id,
                                                 content=content)
        except (Exception, asyncio.CancelledError) as error:
            _LOG.warning("Scheduled send unknown: attempt=%s error_type=%s",
                         attempt_id,
                         type(error).__name__)
            self._repository.finish(attempt_id,
                                    "unknown",
                                    error_type=type(error).__name__)
            raise
        body = response if isinstance(response, dict) else {}
        message_id = body.get("id")
        message_id = message_id if isinstance(message_id, str) else ""
        code = body.get("code")
        code = code if type(code) is int else None
        audit_id = audit_id_from_response(response)
        if message_id:
            status = "sent"
        elif code in (304023, 304024) or audit_id:
            status = "pending_audit"
        elif code is not None and code != 0:
            status = "rejected"
        else:
            status = "unknown"
        _LOG.info(
            "Scheduled send result: attempt=%s task=%r channel_id=%r "
            "status=%s audit_id=%r message_id=%r code=%s", attempt_id, task_id,
            channel_id, status, audit_id, message_id, code)
        self._repository.finish(attempt_id, status, audit_id, message_id, code)
        if status in ("unknown", "rejected"):
            raise RuntimeError("Scheduled message delivery: " + status)

    def record_event(self, event: object, *, passed: bool) -> None:
        """Records SDK audit callbacks without logging their arbitrary body."""
        fields: dict[str, str] = {}
        for name in ("audit_id", "message_id", "guild_id", "channel_id",
                     "audit_time", "create_time", "seq_in_channel"):
            value = getattr(event, name, None)
            fields[name] = value if isinstance(value, str) else ""
        if not fields["audit_id"]:
            _LOG.warning("QQ audit event missing audit_id; ignored")
            return
        status = "audit_passed" if passed else "audit_rejected"
        _LOG.info(
            "QQ audit result: status=%s audit_id=%r channel_id=%r "
            "guild_id=%r message_id=%r", status, fields["audit_id"],
            fields["channel_id"], fields["guild_id"], fields["message_id"])
        self._repository.record_event(status, fields)
