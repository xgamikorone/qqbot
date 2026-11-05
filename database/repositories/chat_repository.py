import datetime
import json
import sqlite3
import time
from typing import NotRequired, TypedDict

from chat import model_client


class DeliveryRecord(TypedDict):
    """Admin-only metadata, with final text included only for detail reads."""

    id: int
    session_key: str
    status: str
    error_type: str
    error_text: str
    created_at: float
    expires_at: float
    answer_chars: int
    model: str
    input_tokens: int
    output_tokens: int
    answer: NotRequired[str]


def session_key(guild: object, channel: object, user: object) -> str:
    """Builds an unambiguous guild/channel/user scope."""
    return json.dumps(
        [str(guild), str(channel), str(user)], separators=(",", ":"))


class ChatRepository:
    """Keeps normal context separate from short-lived sending diagnostics."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def version(self, key: str) -> int:
        """Returns the reset generation of one isolated conversation."""
        self.conn.execute("INSERT OR IGNORE INTO chat_sessions VALUES (?, 0)",
                          (key,))
        self.conn.commit()
        return int(
            self.conn.execute(
                "SELECT version FROM chat_sessions WHERE session_key=?",
                (key,)).fetchone()[0])

    def reset(self, key: str) -> None:
        """Clears this session's local context and diagnostics, not quota."""
        version = self.version(key) + 1
        with self.conn:
            self.conn.execute(
                "UPDATE chat_sessions SET version=? WHERE session_key=?",
                (version, key))
            self.conn.execute("DELETE FROM chat_turns WHERE session_key=?",
                              (key,))
            self.conn.execute("DELETE FROM chat_deliveries WHERE session_key=?",
                              (key,))

    def history(self, key: str, days: int) -> list[tuple[str, str]]:
        """Returns only confirmed sent turns for model context."""
        with self.conn:
            self.conn.execute("DELETE FROM chat_turns WHERE created_at < ?",
                              (time.time() - days * 86400,))
            self.conn.execute("DELETE FROM chat_requests WHERE created_at < ?",
                              (time.time() - max(days, 2) * 86400,))
        rows = self.conn.execute(
            "SELECT question,answer FROM chat_turns WHERE session_key=? "
            "AND status='sent' ORDER BY id DESC LIMIT 50",
            (key,)).fetchall()[::-1]
        return [(str(row[0]), str(row[1])) for row in rows]

    def reserve(self, user_id: str, limit: int) -> bool:
        """Consumes one admitted request in the user's China-calendar quota."""
        day = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
        with self.conn:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM chat_requests WHERE user_id=? AND day=?",
                (user_id, day)).fetchone()[0]
            if count >= limit:
                return False
            self.conn.execute(
                "INSERT INTO chat_requests(user_id,day,created_at) VALUES (?,?,?)",
                (user_id, day, time.time()))
        return True

    def append(self, key: str, question: str,
               result: model_client.GenerationResult, status: str) -> None:
        """Persists a turn after QQ acknowledgement, never from diagnostics."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO chat_turns(session_key,question,answer,model,"
                "input_tokens,output_tokens,status,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (key, question, result.text, result.model, result.input_tokens,
                 result.output_tokens, status, time.time()))

    def purge_deliveries(self) -> None:
        """Expires diagnostics after 24 hours and bounds storage to 1000 rows."""
        with self.conn:
            self.conn.execute("DELETE FROM chat_deliveries WHERE expires_at<=?",
                              (time.time(),))
            self.conn.execute(
                "DELETE FROM chat_deliveries WHERE id NOT IN "
                "(SELECT id FROM chat_deliveries ORDER BY id DESC LIMIT 1000)")

    def begin_delivery(self, key: str,
                       result: model_client.GenerationResult) -> int:
        """Persists exact outgoing text before sending; never stores prompts/tools."""
        self.purge_deliveries()
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO chat_deliveries(session_key,answer,answer_chars,model,"
                "input_tokens,output_tokens,status,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,'sending',?,?)",
                (key, result.text[:10000], len(result.text), result.model,
                 result.input_tokens, result.output_tokens, now, now + 86400),
            )
        assert cursor.lastrowid is not None
        self.purge_deliveries()
        return int(cursor.lastrowid)

    def finish_delivery(self,
                        record_id: int,
                        status: str,
                        error_type: str = "",
                        error_text: str = "") -> None:
        """Updates an existing attempt only, so resets cannot resurrect content."""
        with self.conn:
            self.conn.execute(
                "UPDATE chat_deliveries SET status=?,error_type=?,error_text=? "
                "WHERE id=?",
                (status, error_type[:100], error_text[:1000], record_id),
            )

    def forget_delivery(self, record_id: int) -> None:
        """Removes a successful attempt after its normal history is persisted."""
        with self.conn:
            self.conn.execute("DELETE FROM chat_deliveries WHERE id=?",
                              (record_id,))

    @staticmethod
    def _delivery_record(row: sqlite3.Row | tuple[object, ...],
                         include_answer: bool) -> DeliveryRecord:
        """Converts the explicit SQL projection at the untyped driver boundary."""
        result: DeliveryRecord = {
            "id": int(str(row[0])),
            "session_key": str(row[1]),
            "status": str(row[2]),
            "error_type": str(row[3]),
            "error_text": str(row[4]),
            "created_at": float(str(row[5])),
            "expires_at": float(str(row[6])),
            "answer_chars": int(str(row[7])),
            "model": str(row[8]),
            "input_tokens": int(str(row[9])),
            "output_tokens": int(str(row[10])),
        }
        if include_answer:
            result["answer"] = str(row[11])
        return result

    def list_deliveries(self, limit: int = 50) -> list[DeliveryRecord]:
        """Lists recent unexpired diagnostics without answer or error bodies."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("查询数量必须为 1–100")
        self.purge_deliveries()
        rows = self.conn.execute(
            "SELECT id,session_key,status,error_type,'',created_at,expires_at,"
            "answer_chars,model,input_tokens,output_tokens FROM chat_deliveries "
            "WHERE expires_at>? ORDER BY id DESC LIMIT ?",
            (time.time(), limit),
        ).fetchall()
        return [self._delivery_record(row, False) for row in rows]

    def delivery_detail(self, record_id: int) -> DeliveryRecord | None:
        """Returns final text for one unexpired record, only through admin access."""
        if type(record_id) is not int or record_id <= 0:
            raise ValueError("记录 ID 必须为正整数")
        self.purge_deliveries()
        row = self.conn.execute(
            "SELECT id,session_key,status,error_type,error_text,created_at,expires_at,"
            "answer_chars,model,input_tokens,output_tokens,answer "
            "FROM chat_deliveries WHERE id=? AND expires_at>?",
            (record_id, time.time()),
        ).fetchone()
        return self._delivery_record(row, True) if row is not None else None
