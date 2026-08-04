import logging
import sqlite3

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)
DEFAULT_WIFE_REFRESH_TIME = "08:00"


class SettingsRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def get(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> bool:
        try:
            self.conn.execute(
                """INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at""",
                (key, value, beijing_now_str()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as error:
            logger.exception("设置配置失败, key: %s, error: %s", key, error)
            return False

    @property
    def wife_refresh_time(self) -> str:
        return self.get("wife_refresh_time", DEFAULT_WIFE_REFRESH_TIME)

    def set_wife_refresh_time(self, refresh_time: str) -> bool:
        return self.set("wife_refresh_time", refresh_time)
