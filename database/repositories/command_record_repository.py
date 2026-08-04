import logging
import sqlite3
from typing import Any

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)


class CommandRecordRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def record(self, message_id, channel_id, guild_id, content, user_id,
               user_name, command_name, command_args) -> bool:
        try:
            self.conn.execute(
                """INSERT INTO command_records
                (message_id, channel_id, guild_id, content, created_at, user_id,
                 user_name, command_name, command_args)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (message_id, channel_id, guild_id, content, beijing_now_str(),
                 user_id, user_name, command_name, command_args),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as error:
            logger.exception("添加命令记录失败, error: %s", error)
            return False

    def get_command_counts(self, guild_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT command_name, COUNT(*) AS count FROM command_records
            WHERE guild_id = ? GROUP BY command_name ORDER BY count DESC""",
            (guild_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_counts(self, user_id: str, guild_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT command_name, COUNT(*) AS count FROM command_records
            WHERE user_id = ? AND guild_id = ?
            GROUP BY command_name ORDER BY count DESC""",
            (user_id, guild_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_command_users(self, command_name: str, guild_id: str,
                          limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT user_id, COUNT(*) AS count FROM command_records
            WHERE command_name = ? AND guild_id = ?
            GROUP BY user_id ORDER BY count DESC LIMIT ?""",
            (command_name, guild_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_command_count(self, command_name: str, user_id: str,
                               guild_id: str) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) AS count FROM command_records
            WHERE guild_id = ? AND command_name = ? AND user_id = ?""",
            (guild_id, command_name, user_id),
        ).fetchone()
        return row["count"] if row else 0

    def get_command_user_rank(self, command_name: str, guild_id: str,
                              count: int) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) + 1 AS rank FROM (
                SELECT user_id, COUNT(*) AS count FROM command_records
                WHERE guild_id = ? AND command_name = ? GROUP BY user_id
            ) WHERE count > ?""",
            (guild_id, command_name, count),
        ).fetchone()
        return row["rank"] if row else 0

    def find_users_by_nickname(self, nickname: str,
                               guild_id: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            """SELECT user_id, user_name FROM command_records
            WHERE guild_id = ? AND user_name LIKE ?
            GROUP BY user_id, user_name ORDER BY MAX(created_at) DESC""",
            (guild_id, f"%{nickname}%"),
        ).fetchall()
        return [{"user_id": row["user_id"], "user_name": row["user_name"]}
                for row in rows]

    def get_user_history(self, user_id: str, guild_id: str) -> list[str]:
        rows = self.conn.execute(
            """SELECT user_name FROM command_records
            WHERE user_id = ? AND guild_id = ? GROUP BY user_name
            ORDER BY MAX(created_at) DESC""",
            (user_id, guild_id),
        ).fetchall()
        return [row["user_name"] for row in rows if row["user_name"]]
