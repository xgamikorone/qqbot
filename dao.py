import json
import os
import sqlite3
import logging
from typing import Any, Dict, List
from database.connection import create_connection
from database.repositories.chuang_repository import ChuangRepository
from database.repositories.command_record_repository import CommandRecordRepository
from database.repositories.nickname_repository import NicknameRepository
from database.repositories.wife_repository import WifeRepository
from database.schema import initialize_schema
from utils.time_utils import beijing_now_str

DB_NAME = "user.db"
DEFAULT_WIFE_REFRESH_TIME = "08:00"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Dao:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.conn = create_connection(db_name)
        self._init_db()
        self.wives = WifeRepository(self.conn)
        self.chuang = ChuangRepository(self.conn)
        self.command_records = CommandRecordRepository(self.conn)
        self.nicknames = NicknameRepository(self.conn)

    def add_user(self, uid):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO users (uid, created_at) VALUES (?, ?)",
            (uid, beijing_now_str()),
        )
        self.conn.commit()

    def _get_env_owner_ids(self) -> set[str]:
        owner_ids = os.getenv("BOT_OWNER_IDS") or os.getenv("OWNER_IDS", "")
        return {owner_id.strip() for owner_id in owner_ids.split(",") if owner_id.strip()}

    def _init_db(self):
        initialize_schema(self.conn)

        # self._reset_wives()
        # self._add_wives()

    def is_bot_owner(self, user_id: str) -> bool:
        user_id = str(user_id)
        if user_id in self._get_env_owner_ids():
            return True

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM bot_owners WHERE user_id = ? LIMIT 1",
                (user_id,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.exception(f"check bot owner failed, user_id: {user_id}, error: {e}")
            return False

    def add_bot_owner(self, user_id: str, note: str = "") -> bool:
        try:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO bot_owners (user_id, note, created_at)
                VALUES (?, ?, ?)
                """,
                (str(user_id), note, beijing_now_str()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.exception(f"add bot owner failed, user_id: {user_id}, error: {e}")
            return False

    def remove_bot_owner(self, user_id: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM bot_owners WHERE user_id = ?", (str(user_id),))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.exception(f"remove bot owner failed, user_id: {user_id}, error: {e}")
            return False

    def get_bot_owners(self) -> list[dict[str, Any]]:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT user_id, note, created_at
                FROM bot_owners
                ORDER BY created_at ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.exception(f"get bot owners failed, error: {e}")
            return []

    def _reset_wives(self):
        sql = """
        DELETE FROM wife_urls;
        DELETE FROM sqlite_sequence WHERE name='wife_urls';
        """
        self.conn.executescript(sql)

    def _add_wives(self):
        with open("wives2.json", encoding="utf-8") as f:
            data = json.load(f)

        for w in data:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO wife_urls (url, name, enabled, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (w["url"], w.get("name"), beijing_now_str()),
            )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def get_setting(self, key: str, default: str = "") -> str:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
        except sqlite3.Error as e:
            logger.exception(f"获取配置失败, key: {key}, error: {e}")
            return default

    def set_setting(self, key: str, value: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, beijing_now_str()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.exception(f"设置配置失败, key: {key}, value: {value}, error: {e}")
            return False

    def get_wife_refresh_time(self) -> str:
        return self.get_setting("wife_refresh_time", DEFAULT_WIFE_REFRESH_TIME)

    def set_wife_refresh_time(self, refresh_time: str) -> bool:
        return self.set_setting("wife_refresh_time", refresh_time)
    
# 单例实例
_dao_instance = None


def get_dao(db_name=DB_NAME):
    """获取 Dao 单例实例

    Args:
        db_name (str): 数据库文件名，默认为 'user.db'

    Returns:
        Dao: Dao 单例实例
    """
    global _dao_instance
    if _dao_instance is None:
        _dao_instance = Dao(db_name)
    return _dao_instance


if __name__ == "__main__":
    dao = get_dao()
    print(dao.wives.count_enabled())
