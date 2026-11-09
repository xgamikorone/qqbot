import logging
import sqlite3
import re
import typing

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)
DEFAULT_WIFE_REFRESH_TIME = "00:00"


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

    def get_wife_refresh_time(
        self, scene: typing.Literal["guild", "group"], scope_id: str
    ) -> str:
        """Reads a scoped override, falling back to the original global value."""
        if scene not in {"guild", "group"} or not scope_id:
            raise ValueError("无效的作用域")
        row = self.conn.execute(
            "SELECT refresh_time FROM wife_refresh_settings WHERE scene=? AND scope_id=?",
            (scene, scope_id),
        ).fetchone()
        return row[0] if row else self.wife_refresh_time

    def set_scoped_wife_refresh_time(
        self, scene: typing.Literal["guild", "group"], scope_id: str, value: str
    ) -> bool:
        """Changes only the current scope, preserving the global default."""
        if (
            scene not in {"guild", "group"}
            or not scope_id
            or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)
        ):
            raise ValueError("无效的刷新时间或作用域")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO wife_refresh_settings VALUES (?, ?, ?) ON CONFLICT(scene, scope_id) DO UPDATE SET refresh_time=excluded.refresh_time",
                    (scene, scope_id, value),
                )
            return True
        except sqlite3.Error:
            logger.warning("设置当前作用域刷新时间失败")
            return False
