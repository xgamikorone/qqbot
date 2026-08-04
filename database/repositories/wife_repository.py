import logging
import sqlite3
from typing import Any

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)


class WifeRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def get_by_id(self, wife_id: int) -> dict[str, Any]:
        cursor = self.conn.execute(
            "SELECT id, url, name, enabled, created_at FROM wife_urls WHERE id = ?",
            (wife_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    def search_by_name(self, name: str, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT id, url, name, enabled
            FROM wife_urls
            WHERE name LIKE ?
            ORDER BY id
            LIMIT ?
            """,
            (f"%{name}%", limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_page(
        self, page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * page_size
        count_row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM wife_urls"
        ).fetchone()
        total = count_row["count"] if count_row else 0
        rows = self.conn.execute(
            "SELECT id, name, enabled, url FROM wife_urls ORDER BY id LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        return [dict(row) for row in rows], total

    def set_enabled(self, wife_id: int, enabled: bool) -> bool:
        try:
            cursor = self.conn.execute(
                "UPDATE wife_urls SET enabled = ? WHERE id = ?",
                (int(enabled), wife_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as error:
            logger.exception(
                "设置老婆启用状态失败, wife_id: %s, error: %s", wife_id, error
            )
            return False

    def add(self, name: str, url: str) -> int | None:
        try:
            cursor = self.conn.execute(
                "INSERT INTO wife_urls (url, name, enabled, created_at) VALUES (?, ?, 1, ?)",
                (url, name, beijing_now_str()),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as error:
            logger.exception(
                "增加老婆失败, name: %s, url: %s, error: %s", name, url, error
            )
            return None

    def update(
        self, wife_id: int, name: str | None = None, url: str | None = None
    ) -> bool:
        if name is None and url is None:
            return False

        fields = []
        values: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if url is not None:
            fields.append("url = ?")
            values.append(url)
        values.append(wife_id)

        try:
            cursor = self.conn.execute(
                f"UPDATE wife_urls SET {', '.join(fields)} WHERE id = ?", values
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as error:
            logger.exception(
                "更新老婆失败, wife_id: %s, error: %s", wife_id, error
            )
            return False

    def get_or_draw(self, user_id: str, channel_id: str, guild_id: str):
        today = beijing_now_str("%Y-%m-%d")
        existing = self.get_for_date(user_id, today)
        if existing:
            return existing

        row = self.conn.execute(
            """
            SELECT id, url, name
            FROM wife_urls
            WHERE enabled = 1
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {}

        self.conn.execute(
            """
            INSERT OR IGNORE INTO user_wife_daily
                (user_id, wife_id, channel_id, guild_id, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, row["id"], channel_id, guild_id, today, beijing_now_str()),
        )
        self.conn.commit()
        return self.get_for_date(user_id, today)

    def count_enabled(self) -> int:
        try:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM wife_urls WHERE enabled = 1"
            ).fetchone()
            return row["count"] if row else 0
        except sqlite3.Error as error:
            logger.exception("获取老婆数量失败, error: %s", error)
            return 0

    def get_for_date(self, user_id: str, date: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT w.id, w.url, w.name
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            WHERE uw.user_id = ? AND uw.date = ?
            """,
            (user_id, date),
        ).fetchone()
        return dict(row) if row else {}

    def get_user_counts(
        self, user_id: str, page: int = 1, page_size: int = 10
    ) -> list[dict[str, Any]]:
        offset = (page - 1) * page_size
        rows = self.conn.execute(
            """
            SELECT MIN(w.id) AS id, MIN(w.url) AS url, w.name, COUNT(*) AS count
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            WHERE uw.user_id = ?
            GROUP BY w.name
            ORDER BY count DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, page_size, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_counts(
        self, page: int = 1, page_size: int = 10
    ) -> list[dict[str, Any]]:
        offset = (page - 1) * page_size
        rows = self.conn.execute(
            """
            SELECT MIN(w.id) AS id, MIN(w.url) AS url, w.name, COUNT(*) AS count
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            GROUP BY w.name
            ORDER BY count DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_counts_by_name(
        self, wife_name: str, page: int = 1, page_size: int = 10
    ) -> list[dict[str, Any]]:
        offset = (page - 1) * page_size
        rows = self.conn.execute(
            """
            SELECT uw.user_id, COUNT(*) AS count
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            WHERE w.name = ?
            GROUP BY uw.user_id
            ORDER BY count DESC, uw.user_id
            LIMIT ? OFFSET ?
            """,
            (wife_name, page_size, offset),
        ).fetchall()
        return [dict(row) for row in rows]
