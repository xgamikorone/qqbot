import json
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List

DB_NAME = "user.db"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Dao:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def add_user(self, uid):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO users (uid) VALUES (?)", (uid,))
        self.conn.commit()

    def _init_db(self):
        sql = """
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            uid INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 子表：昵称表
        CREATE TABLE IF NOT EXISTS user_nicknames (
            id INTEGER PRIMARY KEY,       -- 自增ID
            uid INTEGER NOT NULL,         -- 外键指向 users.uid
            nickname TEXT NOT NULL UNIQUE, -- 昵称全局唯一，便于通过昵称查询uid
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
        );

        -- 为昵称建立索引，加快查询
        CREATE INDEX IF NOT EXISTS idx_nickname ON user_nicknames(nickname);

        -- 子表：调用记录
        CREATE TABLE IF NOT EXISTS command_records (
            id INTEGER PRIMARY KEY,
            message_id TEXT NOT NULL,  -- 调用消息的message_id
            channel_id TEXT NOT NULL,  -- 调用消息所在的channel_id
            guild_id TEXT NOT NULL,    -- 调用消息所在的guild_id
            content TEXT NOT NULL,     -- 调用消息的content
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT NOT NULL,  -- 调用者的uid
            user_name TEXT NOT NULL,  -- 调用者的昵称
            command_name TEXT NOT NULL,  -- 调用的命令名
            command_args TEXT NOT NULL  -- 调用的命令参数
        );

        -- 老婆池
        CREATE TABLE IF NOT EXISTS wife_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            name TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 用户每日老婆记录
        CREATE TABLE IF NOT EXISTS user_wife_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,      -- QQ 用户 ID
            wife_id INTEGER NOT NULL,      -- 对应 wife_urls.id

            channel_id TEXT NOT NULL,  -- 调用消息所在的channel_id
            guild_id TEXT NOT NULL,    -- 调用消息所在的guild_id
            
            date TEXT NOT NULL,            -- 'YYYY-MM-DD'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE (user_id, date),
            FOREIGN KEY (wife_id) REFERENCES wife_urls(id)
        );

        -- 每日被创记录
        CREATE TABLE IF NOT EXISTS user_chuang_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,      -- QQ 用户 ID
            distance INTEGER NOT NULL,   -- 创的距离，单位：米
            channel_id TEXT NOT NULL,  -- 调用消息所在的channel_id
            guild_id TEXT NOT NULL,    -- 调用消息所在的guild_id

            date TEXT NOT NULL,            -- 'YYYY-MM-DD'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE (user_id, date)
        )
        

        """
        self.conn.executescript(sql)

        # self._reset_wives()
        # self._add_wives()

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
                INSERT OR IGNORE INTO wife_urls (url, name, enabled)
                VALUES (?, ?, 1)
                """,
                (w["url"], w.get("name")),
            )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def add_nickname(self, uid: int, nickname: str) -> bool:
        """添加uid和对应的nickname，如果uid不存在则自动添加

        Args:
            uid (int): b站用户uid
            nickname (str): 要添加的昵称

        Returns:
            bool: 添加成功返回True，昵称已存在返回False
        """
        try:
            cursor = self.conn.cursor()
            # 先确保uid存在，不存在则自动插入
            cursor.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
            # 再添加昵称
            sql = "INSERT INTO user_nicknames (uid, nickname) VALUES (?,?)"
            cursor.execute(sql, (uid, nickname))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False

    def get_uid_by_nickname(self, nickname: str) -> int | None:
        """根据nickname查询uid

        Args:
            nickname (str): 昵称

        Returns:
            int | None: 对应的uid，如果没有找到则返回None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT uid FROM user_nicknames WHERE nickname = ?", (nickname,)
            )
            result = cursor.fetchone()
            return result["uid"] if result else None
        except sqlite3.Error as e:
            logger.exception(f"查询昵称对应的uid失败, error: {e}")
            return None

    def get_uids_by_nickname_like(self, nickname: str) -> list[int]:
        """根据nickname模糊查询uid列表

        Args:
            nickname (str): 昵称关键词

        Returns:
            list[int]: 对应的uid列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT DISTINCT uid FROM user_nicknames WHERE nickname LIKE ?",
                (f"%{nickname}%",),
            )
            result = cursor.fetchall()
            return [r["uid"] for r in result]
        except sqlite3.Error as e:
            logger.exception(f"模糊查询昵称对应的uid失败, error: {e}")
            return []

    def get_nicknames_by_uid(self, uid: int) -> list[str]:
        """根据uid查询昵称

        Args:
            uid (int): 用户uid

        Returns:
            list[str]: 对应的昵称
        """
        sql = "SELECT nickname FROM user_nicknames WHERE uid = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (uid,))
            result = cursor.fetchall()
            return [r["nickname"] for r in result]
        except sqlite3.Error as e:
            logger.exception(f"查询uid对应的昵称失败, error: {e}")
            return []

    def delete_nickname(self, nickname: str) -> bool:
        """删除nickname

        Args:
            nickname (str): 要删除的昵称

        Returns:
            bool: 是否删除成功
        """
        sql = "DELETE FROM user_nicknames WHERE nickname = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (nickname,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.exception(f"删除昵称失败, error: {e}")
            return False

    def delete_nickname_by_uid(self, uid: int) -> bool:
        """删除uid对应的所有昵称

        Args:
            uid (int): 用户uid


        Returns:
            bool: 是否删除成功
        """
        sql = "DELETE FROM user_nicknames WHERE uid = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (uid,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.exception(f"删除uid对应的所有昵称失败, error: {e}")
            return False

    def get_all_nicknames(self) -> list[dict]:
        """得到所有昵称和对应的uid

        Returns:
            list[dict]: 昵称和对应的uid列表
        """
        sql = "SELECT nickname, uid FROM user_nicknames"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            return [{"nickname": r["nickname"], "uid": r["uid"]} for r in result]
        except sqlite3.Error as e:
            logger.exception(f"查询所有昵称和uid失败, error: {e}")
            return []

    def add_command_record(
        self,
        message_id: str,
        channel_id: str,
        guild_id: str,
        content: str,
        user_id: str,
        user_name: str,
        command_name: str,
        command_args: str,
    ) -> bool:

        sql = """
        INSERT INTO command_records (message_id, channel_id, guild_id, content, user_id, user_name, command_name, command_args)
        VALUES (?,?,?,?,?,?,?,?)"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                sql,
                (
                    message_id,
                    channel_id,
                    guild_id,
                    content,
                    user_id,
                    user_name,
                    command_name,
                    command_args,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.exception(f"添加命令记录失败, error: {e}")
            return False

    def get_command_counts(self):
        """获取每种命令的调用次数"""
        sql = """
        SELECT command_name, COUNT(*) AS count FROM command_records
        GROUP BY command_name
        ORDER BY count DESC"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_command_counts_cur_guild(self, guild_id: str):
        """获取当前服务器每种命令的调用次数"""
        sql = """
        SELECT command_name, COUNT(*) AS count FROM command_records
        WHERE guild_id = ?
        GROUP BY command_name
        ORDER BY count DESC"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (guild_id,))
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_user_command_counts(self, user_id: str):
        sql = """
        SELECT command_name, COUNT(*) AS count FROM command_records
        WHERE user_id = ?
        GROUP BY command_name
        ORDER BY count DESC"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (user_id,))
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_user_command_counts_cur_guild(self, user_id: str, guild_id: str):
        sql = """
        SELECT command_name, COUNT(*) AS count FROM command_records
        WHERE user_id = ?
        AND guild_id = ?
        GROUP BY command_name
        ORDER BY count DESC"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (user_id, guild_id))
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_command_counts_per_user(self, command_name: str, limit: int = 10):
        """获取某个命令被那些用户使用最多"""
        sql = """
        SELECT user_id, COUNT(*) AS count FROM command_records
        WHERE command_name = ?
        GROUP BY user_id
        ORDER BY count DESC
        LIMIT ?"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (command_name, limit))
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_command_counts_per_user_cur_guild(
        self, command_name: str, guild_id: str, limit: int = 10
    ):
        """获取某个命令被那些用户使用最多"""
        sql = """
        SELECT user_id, COUNT(*) AS count FROM command_records
        WHERE command_name = ?
        AND guild_id = ?
        GROUP BY user_id
        ORDER BY count DESC
        LIMIT ?"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (command_name, guild_id, limit))
            result = cursor.fetchall()
            return [dict(r) for r in result]
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return []

    def get_command_counts_by_user_cur_guild(
        self,
        command_name: str,
        user_id: str,
        guild_id: str,
    ):
        sql = """
        SELECT COUNT(*)
        FROM command_records
        WHERE guild_id = ?
        AND command_name = ?
        AND user_id = ?"""

        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (guild_id, command_name, user_id))
            result = cursor.fetchone()
            return dict(result) if result else {}
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return {}

    def get_command_counts_rank_by_user_cur_guild(
        self,
        command_name: str,
        guild_id: str,
        count: int,
    ):
        sql = """
        SELECT COUNT(*) AS greater_count
        FROM (
            SELECT user_id, COUNT(*) AS cnt
            FROM command_records
            WHERE guild_id = ?
            AND command_name = ?
            GROUP BY user_id
        ) t
        WHERE cnt > ?"""

        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (guild_id, command_name, count))
            result = cursor.fetchone()
            return dict(result) if result else {}
        except sqlite3.Error as e:
            logger.exception(f"获取命令调用次数失败, error: {e}")
            return {}

    def _get_today_str(self):
        return datetime.now().strftime("%Y-%m-%d")

    def get_wife(self, user_id: str, channel_id: str, guild_id: str):
        today = self._get_today_str()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT w.id, w.url, w.name
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            WHERE uw.user_id = ? AND uw.date = ?
            """,
            (user_id, today),
        )

        row = cursor.fetchone()
        if row:
            return dict(row)

        # 如果今天没有记录，则随机选一个老婆
        cursor.execute(
            """
            SELECT id, url, name
            FROM wife_urls
            WHERE enabled = 1
            ORDER BY RANDOM()
            LIMIT 1
            """
        )

        row = cursor.fetchone()
        print(dict(row))
        if not row:
            return {}

        print(1)
        wife_id = row["id"]
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_wife_daily (user_id, wife_id, channel_id, guild_id, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, wife_id, channel_id, guild_id, today),
        )

        self.conn.commit()

        # 再查一次，确保拿到“最终绑定的”
        cursor.execute(
            """
            SELECT w.id, w.url, w.name
            FROM user_wife_daily uw
            JOIN wife_urls w ON uw.wife_id = w.id
            WHERE uw.user_id = ? AND uw.date = ?
            """,
            (user_id, today),
        )

        result = cursor.fetchone()
        return dict(result) if result else {}

    def get_num_wives(self):
        """获取老婆池中老婆的数量"""
        sql = "SELECT COUNT(*) AS count FROM wife_urls WHERE enabled = 1"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchone()
            return result["count"] if result else 0
        except sqlite3.Error as e:
            logger.exception(f"获取老婆数量失败, error: {e}")
            return 0

    def get_today_chuang_distance(
        self, user_id: str, guild_id: str, date: str
    ) -> int | None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT distance
            FROM user_chuang_daily
            WHERE user_id = ?
            AND guild_id = ?
            AND date = ?
            """,
            (user_id, guild_id, date),
        )
        row = cursor.fetchone()
        return row["distance"] if row else None

    def insert_chuang(
        self,
        user_id: str,
        distance: int,
        channel_id: str,
        guild_id: str,
        date: str,
    ):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_chuang_daily
            (user_id, distance, channel_id, guild_id, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, distance, channel_id, guild_id, date),
        )
        self.conn.commit()

    def get_today_chuang_rank_cur_guild(
        self,
        distance: int,
        guild_id: str,
        date: str,
    ) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE date = ?
            AND guild_id = ?
            AND distance > ?
            """,
            (date, guild_id, distance),
        )
        return cursor.fetchone()["rank"]

    def get_today_chuang_rank_all_guild(
        self,
        distance: int,
        date: str,
    ) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE date = ?
            AND distance > ?
            """,
            (date, distance),
        )
        return cursor.fetchone()["rank"]

    def get_chuang_history_rank_cur_guild(self, distance: int, guild_id: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE guild_id = ?
            AND distance > ?
            """,
            (guild_id, distance),
        )
        return cursor.fetchone()["rank"]

    def get_chuang_history_rank_all_guild(self, distance: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM user_chuang_daily
            WHERE distance > ?
            """,
            (distance,),
        )
        return cursor.fetchone()["rank"]

    def get_chuang_history_max(self, user_id: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT MAX(distance) AS max_distance
            FROM user_chuang_daily
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return row["max_distance"] or 0

    def add_qq_user_nickname(self, user_id: str, nickname: str):
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO user_nickname_ids
                (user_id, nickname)
                VALUES (?, ?)
                """,
                (user_id, nickname),
            )
            return cursor.rowcount == 1

    def get_chuang_top_k_cur_guild(
        self, k: int, date: str, guild_id: str
    ) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM user_chuang_daily
            WHERE date = ?
            AND guild_id = ?
            ORDER BY distance DESC
            LIMIT ?
            """,
            (date, guild_id, k),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_chuang_top_k_cur_guild_history(
        self, k: int, guild_id: str
    ) -> list[dict[str, Any]]:
        """返回历史记录中被创距离最远的k条, 每个user_id仅限一条"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT * FROM (
                SELECT *, 
                       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY distance DESC) as rn
                FROM user_chuang_daily
                WHERE guild_id = ?
            ) t
            WHERE t.rn = 1
            ORDER BY t.distance DESC
            LIMIT ?
            """
            cursor.execute(sql, (guild_id, k))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.exception(f"获取被创记录失败, error: {e}")
            return []

    def get_user_chuang_history_best(
        self, user_id: str, guild_id: str
    ) -> dict[str, Any]:
        """获取指定用户在指定公会中的历史最远被创记录和历史排名，返回全部字段"""
        try:
            cursor = self.conn.cursor()
            # 获取用户在指定公会中的历史最远被创记录
            sql = """
            SELECT *
            FROM user_chuang_daily
            WHERE user_id = ?
            AND guild_id = ?
            ORDER BY distance DESC
            LIMIT 1
            """
            cursor.execute(sql, (user_id, guild_id))
            row = cursor.fetchone()
            if not row:
                return {}

            # 转换为字典
            result = dict(row)

            # 计算在指定公会中的历史排名
            distance = result["distance"]
            rank = self.get_chuang_history_rank_cur_guild(distance, guild_id)
            result["history_rank"] = rank

            return result
        except sqlite3.Error as e:
            logger.exception(f"获取用户历史最远被创记录失败, error: {e}")
            return {}

    def get_chuang_total_top_k_cur_guild(
        self, k: int, guild_id: str
    ) -> list[dict[str, Any]]:
        """获取指定公会中累计被创距离排名前k的用户"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT user_id, SUM(distance) AS total_distance
            FROM user_chuang_daily
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY total_distance DESC
            LIMIT ?
            """
            cursor.execute(sql, (guild_id, k))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.exception(f"获取累计被创排名失败, error: {e}")
            return []

    def get_user_chuang_total(self, user_id: str, guild_id: str) -> dict[str, Any]:
        """获取指定用户在指定公会中的累计被创距离和排名"""
        try:
            cursor = self.conn.cursor()
            # 计算指定用户在指定公会中的累计被创距离
            sql = """
            SELECT SUM(distance) AS total_distance
            FROM user_chuang_daily
            WHERE user_id = ?
            AND guild_id = ?
            """
            cursor.execute(sql, (user_id, guild_id))
            row = cursor.fetchone()
            if not row or not row["total_distance"]:
                return {"total_distance": 0, "rank": 0}

            total_distance = row["total_distance"]

            # 计算该用户在指定公会中的累计被创距离排名
            rank_sql = """
            SELECT COUNT(*) + 1 AS rank
            FROM (
                SELECT SUM(distance) AS total_distance
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
                HAVING SUM(distance) > ?
            ) t
            """
            cursor.execute(rank_sql, (guild_id, total_distance))
            rank_row = cursor.fetchone()
            rank = rank_row["rank"] if rank_row else 0

            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "total_distance": total_distance,
                "rank": rank,
            }
        except sqlite3.Error as e:
            logger.exception(f"获取用户累计被创距离失败, error: {e}")
            return {"total_distance": 0, "rank": 0}

    def get_chuang_average_top_k_cur_guild(
        self,
        k: int,
        guild_id: str,
        min_limit: int = 5,
    ):
        """获取指定公会中平均被创距离排名前k的用户"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT user_id, AVG(distance) AS average_distance
            FROM user_chuang_daily
            WHERE guild_id = ?
            GROUP BY user_id
            HAVING COUNT(*) >= ?
            ORDER BY average_distance DESC
            LIMIT ?
            """
            cursor.execute(sql, (guild_id, min_limit, k))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.exception(f"获取平均被创排名失败, error: {e}")
            return []

    def get_user_chuang_time(self, user_id: str, guild_id: str) -> int:
        """获取指定用户在指定公会中的被创次数"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT COUNT(*) AS chuang_time
            FROM user_chuang_daily
            WHERE user_id = ?
            AND guild_id = ?
            """
            cursor.execute(sql, (user_id, guild_id))
            row = cursor.fetchone()
            if not row or not row["chuang_time"]:
                return 0
            return row["chuang_time"]
        except sqlite3.Error as e:
            logger.exception(f"获取用户被创次数失败, error: {e}")
            return 0

    def get_user_chuang_average(self, user_id: str, guild_id: str) -> float:
        """获取指定用户在指定公会中的平均被创距离"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT AVG(distance) AS average_distance
            FROM user_chuang_daily
            WHERE user_id = ?
            AND guild_id = ?
            """
            cursor.execute(sql, (user_id, guild_id))
            row = cursor.fetchone()
            if not row or not row["average_distance"]:
                return 0.0
            return row["average_distance"]
        except sqlite3.Error as e:
            logger.exception(f"获取用户平均被创距离失败, error: {e}")
            return 0.0

    def get_avg_distance_rank_cur_guild(
        self, distance: float, guild_id: str, min_limit: int
    ) -> int:
        """获取指定公会中平均被创距离大于指定值的用户的排名"""
        try:
            sql = """
            SELECT COUNT(*) + 1 AS rank
            FROM (
                SELECT AVG(distance) AS average_distance
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
                HAVING COUNT(*) >= ?
            ) t
            WHERE average_distance > ?
            """
            cursor = self.conn.cursor()
            cursor.execute(sql, (guild_id, min_limit, distance))
            row = cursor.fetchone()
            if not row or not row["rank"]:
                return 0
            return row["rank"]
        except sqlite3.Error as e:
            logger.exception(f"获取平均被创排名失败, error: {e}")
            return 0

    def get_chuang_times_rank_cur_guild(self, guild_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取指定公会中被创次数排名前k的用户"""
        try:
            cursor = self.conn.cursor()
            sql = """
            SELECT user_id, COUNT(*) AS chuang_time
            FROM user_chuang_daily
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY chuang_time DESC
            LIMIT ?
            """
            cursor.execute(sql, (guild_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.exception(f"获取被创次数排名失败, error: {e}")
            return []

    def get_user_chuang_times_rank_cur_guild(self, times: int, guild_id: str) -> int:
        """获取指定公会中被创次数大于等于指定值的用户的排名"""
        try:
            sql = """
            SELECT COUNT(*) + 1 AS rank
            FROM (
                SELECT COUNT(*) AS chuang_time
                FROM user_chuang_daily
                WHERE guild_id = ?
                GROUP BY user_id
            ) t
            WHERE chuang_time > ?
            """
            cursor = self.conn.cursor()
            cursor.execute(sql, (guild_id, times))
            row = cursor.fetchone()
            return row["rank"] if row else 0
        except sqlite3.Error as e:
            logger.exception(f"获取被创次数排名失败, error: {e}")
            return 0


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
    print(dao.get_num_wives())
