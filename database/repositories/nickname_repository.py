import logging
import sqlite3

from utils.time_utils import beijing_now_str


logger = logging.getLogger(__name__)


class NicknameRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def add(self, uid: int, nickname: str) -> bool:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO users (uid, created_at) VALUES (?, ?)",
                (uid, beijing_now_str()),
            )
            self.conn.execute(
                "INSERT INTO user_nicknames (uid, nickname, created_at) VALUES (?, ?, ?)",
                (uid, nickname, beijing_now_str()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False

    def get_uid(self, nickname: str) -> int | None:
        row = self.conn.execute(
            "SELECT uid FROM user_nicknames WHERE nickname = ?", (nickname,)
        ).fetchone()
        return row["uid"] if row else None

    def find_uids(self, nickname: str) -> list[int]:
        rows = self.conn.execute(
            "SELECT DISTINCT uid FROM user_nicknames WHERE nickname LIKE ?",
            (f"%{nickname}%",),
        ).fetchall()
        return [row["uid"] for row in rows]

    def get_for_uid(self, uid: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT nickname FROM user_nicknames WHERE uid = ?", (uid,)
        ).fetchall()
        return [row["nickname"] for row in rows]

    def delete(self, nickname: str) -> bool:
        try:
            self.conn.execute("DELETE FROM user_nicknames WHERE nickname = ?", (nickname,))
            self.conn.commit()
            return True
        except sqlite3.Error as error:
            logger.exception("删除昵称失败, error: %s", error)
            return False

    def delete_for_uid(self, uid: int) -> bool:
        try:
            self.conn.execute("DELETE FROM user_nicknames WHERE uid = ?", (uid,))
            self.conn.commit()
            return True
        except sqlite3.Error as error:
            logger.exception("删除uid对应的所有昵称失败, error: %s", error)
            return False

    def get_all(self) -> list[dict]:
        rows = self.conn.execute("SELECT nickname, uid FROM user_nicknames").fetchall()
        return [{"nickname": row["nickname"], "uid": row["uid"]} for row in rows]
