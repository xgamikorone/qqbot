import logging
import os
import sqlite3
from typing import Any

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)


class OwnerRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    @staticmethod
    def _environment_owner_ids() -> set[str]:
        value = os.getenv("BOT_OWNER_IDS") or os.getenv("OWNER_IDS", "")
        return {owner_id.strip() for owner_id in value.split(",") if owner_id.strip()}

    def contains(self, user_id: str) -> bool:
        user_id = str(user_id)
        if user_id in self._environment_owner_ids():
            return True
        row = self.conn.execute(
            "SELECT 1 FROM bot_owners WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        return row is not None

    def add(self, user_id: str, note: str = "") -> bool:
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO bot_owners (user_id, note, created_at)
                VALUES (?, ?, ?)""",
                (str(user_id), note, beijing_now_str()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as error:
            logger.exception("add bot owner failed, user_id: %s, error: %s", user_id, error)
            return False

    def remove(self, user_id: str) -> bool:
        try:
            cursor = self.conn.execute(
                "DELETE FROM bot_owners WHERE user_id = ?", (str(user_id),)
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as error:
            logger.exception("remove bot owner failed, user_id: %s, error: %s", user_id, error)
            return False

    def get_all(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT user_id, note, created_at FROM bot_owners ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]
