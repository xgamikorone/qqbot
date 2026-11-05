"""Durable scheduled send attempts and idempotent QQ audit events."""

import sqlite3
import time
from collections.abc import Mapping


class MessageAuditRepository:
    """Keeps submissions separate from final events to tolerate event races."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def start(self, attempt_id: str, task_id: str, channel_id: str) -> None:
        """Records an attempt before any network side effect."""
        with self._connection:
            self._connection.execute(
                "INSERT INTO scheduled_message_sends "
                "(attempt_id, task_id, channel_id, status, created_at) "
                "VALUES (?, ?, ?, 'sending', ?)",
                (attempt_id, task_id, channel_id, time.time()))

    def finish(self,
               attempt_id: str,
               status: str,
               audit_id: str = "",
               message_id: str = "",
               code: int | None = None,
               error_type: str = "") -> None:
        """Records the HTTP outcome, never overwriting a final audit event."""
        with self._connection:
            self._connection.execute(
                "UPDATE scheduled_message_sends SET status=?, audit_id=?, "
                "message_id=?, code=?, error_type=?, updated_at=? "
                "WHERE attempt_id=?", (status, audit_id, message_id, code,
                                       error_type, time.time(), attempt_id))

    def record_event(self, status: str, fields: Mapping[str, str]) -> None:
        """Upserts metadata even if the event precedes the HTTP response.

        Duplicate events keep the first terminal outcome. Unmatched events are
        retained so that restarts and late HTTP responses do not lose results.
        """
        with self._connection:
            self._connection.execute(
                "INSERT INTO message_audit_events "
                "(audit_id, status, message_id, guild_id, channel_id, "
                "audit_time, create_time, seq_in_channel, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(audit_id) DO NOTHING",
                (fields['audit_id'], status, fields.get('message_id', ''),
                 fields.get('guild_id', ''), fields.get('channel_id', ''),
                 fields.get('audit_time', ''), fields.get('create_time', ''),
                 fields.get('seq_in_channel', ''), time.time()))
