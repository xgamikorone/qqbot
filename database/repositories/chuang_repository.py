import logging
import sqlite3
from typing import Any

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)


class ChuangRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def get_distance(self, user_id: str, guild_id: str, date: str) -> int | None:
        row = self.conn.execute(
            """
            SELECT distance
            FROM user_chuang_daily
            WHERE user_id = ? AND guild_id = ? AND date = ?
            """,
            (user_id, guild_id, date),
        ).fetchone()
        return row["distance"] if row else None

    def record(
        self,
        user_id: str,
        distance: int,
        channel_id: str,
        guild_id: str,
        date: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO user_chuang_daily
                (user_id, distance, channel_id, guild_id, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, distance, channel_id, guild_id, date, beijing_now_str()),
        )
        self.conn.commit()

    def get_daily_rank(self, distance: int, guild_id: str, date: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE date = ? AND guild_id = ? AND distance > ?
            """,
            (date, guild_id, distance),
        ).fetchone()
        return row["rank"]

    def get_global_daily_rank(self, distance: int, date: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE date = ? AND distance > ?
            """,
            (date, distance),
        ).fetchone()
        return row["rank"]

    def get_history_rank(self, distance: int, guild_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE guild_id = ? AND distance > ?
            """,
            (guild_id, distance),
        ).fetchone()
        return row["rank"]

    def get_global_history_rank(self, distance: int) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE distance > ?
            """,
            (distance,),
        ).fetchone()
        return row["rank"]

    def get_history_max(self, user_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT MAX(distance) AS max_distance
            FROM user_chuang_daily
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return row["max_distance"] or 0

    def get_daily_top(
        self, limit: int, date: str, guild_id: str
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM user_chuang_daily
            WHERE date = ? AND guild_id = ?
            ORDER BY distance DESC
            LIMIT ?
            """,
            (date, guild_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_history_top(
        self, limit: int, guild_id: str
    ) -> list[dict[str, Any]]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY user_id ORDER BY distance DESC
                           ) AS rn
                    FROM user_chuang_daily
                    WHERE guild_id = ?
                ) t
                WHERE t.rn = 1
                ORDER BY t.distance DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            logger.exception("获取被创记录失败, error: %s", error)
            return []

    def get_user_history_best(
        self, user_id: str, guild_id: str
    ) -> dict[str, Any]:
        try:
            row = self.conn.execute(
                """
                SELECT *
                FROM user_chuang_daily
                WHERE user_id = ? AND guild_id = ?
                ORDER BY distance DESC
                LIMIT 1
                """,
                (user_id, guild_id),
            ).fetchone()
            if not row:
                return {}

            result = dict(row)
            result["history_rank"] = self.get_history_rank(
                result["distance"], guild_id
            )
            return result
        except sqlite3.Error as error:
            logger.exception("获取用户历史最远被创记录失败, error: %s", error)
            return {}

    def get_total_top(
        self, limit: int, guild_id: str
    ) -> list[dict[str, Any]]:
        try:
            rows = self.conn.execute(
                """
                SELECT user_id, SUM(distance) AS total_distance
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
                ORDER BY total_distance DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            logger.exception("获取累计被创排名失败, error: %s", error)
            return []

    def get_user_total(self, user_id: str, guild_id: str) -> dict[str, Any]:
        try:
            row = self.conn.execute(
                """
                SELECT SUM(distance) AS total_distance
                FROM user_chuang_daily
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id),
            ).fetchone()
            if not row or not row["total_distance"]:
                return {"total_distance": 0, "rank": 0}

            total_distance = row["total_distance"]
            rank_row = self.conn.execute(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM (
                    SELECT SUM(distance) AS total_distance
                    FROM user_chuang_daily
                    WHERE guild_id = ?
                    GROUP BY user_id
                    HAVING SUM(distance) > ?
                ) t
                """,
                (guild_id, total_distance),
            ).fetchone()
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "total_distance": total_distance,
                "rank": rank_row["rank"] if rank_row else 0,
            }
        except sqlite3.Error as error:
            logger.exception("获取用户累计被创距离失败, error: %s", error)
            return {"total_distance": 0, "rank": 0}

    def get_average_top(
        self, limit: int, guild_id: str, min_count: int = 5
    ) -> list[dict[str, Any]]:
        try:
            rows = self.conn.execute(
                """
                SELECT user_id, AVG(distance) AS average_distance
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
                HAVING COUNT(*) >= ?
                ORDER BY average_distance DESC
                LIMIT ?
                """,
                (guild_id, min_count, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            logger.exception("获取平均被创排名失败, error: %s", error)
            return []

    def get_user_count(self, user_id: str, guild_id: str) -> int:
        try:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS chuang_time
                FROM user_chuang_daily
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id),
            ).fetchone()
            return row["chuang_time"] if row and row["chuang_time"] else 0
        except sqlite3.Error as error:
            logger.exception("获取用户被创次数失败, error: %s", error)
            return 0

    def get_user_average(self, user_id: str, guild_id: str) -> float:
        try:
            row = self.conn.execute(
                """
                SELECT AVG(distance) AS average_distance
                FROM user_chuang_daily
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id),
            ).fetchone()
            return (
                row["average_distance"]
                if row and row["average_distance"]
                else 0.0
            )
        except sqlite3.Error as error:
            logger.exception("获取用户平均被创距离失败, error: %s", error)
            return 0.0

    def get_average_rank(
        self, average: float, guild_id: str, min_count: int
    ) -> int:
        try:
            row = self.conn.execute(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM (
                    SELECT AVG(distance) AS average_distance
                    FROM user_chuang_daily
                    WHERE guild_id = ?
                    GROUP BY user_id
                    HAVING COUNT(*) >= ?
                ) t
                WHERE average_distance > ?
                """,
                (guild_id, min_count, average),
            ).fetchone()
            return row["rank"] if row and row["rank"] else 0
        except sqlite3.Error as error:
            logger.exception("获取平均被创排名失败, error: %s", error)
            return 0

    def get_count_top(
        self, guild_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        try:
            rows = self.conn.execute(
                """
                SELECT user_id, COUNT(*) AS chuang_time
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
                ORDER BY chuang_time DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            logger.exception("获取被创次数排名失败, error: %s", error)
            return []

    def get_count_rank(self, count: int, guild_id: str) -> int:
        try:
            row = self.conn.execute(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM (
                    SELECT COUNT(*) AS chuang_time
                    FROM user_chuang_daily
                    WHERE guild_id = ?
                    GROUP BY user_id
                ) t
                WHERE chuang_time > ?
                """,
                (guild_id, count),
            ).fetchone()
            return row["rank"] if row else 0
        except sqlite3.Error as error:
            logger.exception("获取被创次数排名失败, error: %s", error)
            return 0
