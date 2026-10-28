import json
import time
from datetime import datetime, timedelta, timezone

def session_key(guild, channel, user):
    return json.dumps([str(guild), str(channel), str(user)], separators=(",", ":"))

class ChatRepository:
    def __init__(self, conn):
        self.conn = conn

    def version(self, key):
        self.conn.execute("INSERT OR IGNORE INTO chat_sessions VALUES (?, 0)", (key,))
        self.conn.commit()
        return self.conn.execute("SELECT version FROM chat_sessions WHERE session_key=?", (key,)).fetchone()[0]

    def reset(self, key):
        version = self.version(key) + 1
        with self.conn:
            self.conn.execute("UPDATE chat_sessions SET version=? WHERE session_key=?", (version, key))
            self.conn.execute("DELETE FROM chat_turns WHERE session_key=?", (key,))

    def history(self, key, days):
        with self.conn:
            self.conn.execute("DELETE FROM chat_turns WHERE created_at < ?", (time.time() - days * 86400,))
            self.conn.execute("DELETE FROM chat_requests WHERE created_at < ?", (time.time() - max(days, 2) * 86400,))
        return self.conn.execute("SELECT question,answer FROM chat_turns WHERE session_key=? AND status='sent' ORDER BY id DESC LIMIT 50", (key,)).fetchall()[::-1]

    def reserve(self, user_id, limit):
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        with self.conn:
            count = self.conn.execute("SELECT COUNT(*) FROM chat_requests WHERE user_id=? AND day=?", (user_id, day)).fetchone()[0]
            if count >= limit:
                return False
            self.conn.execute("INSERT INTO chat_requests(user_id,day,created_at) VALUES (?,?,?)", (user_id, day, time.time()))
        return True

    def append(self, key, question, result, status):
        with self.conn:
            self.conn.execute("INSERT INTO chat_turns(session_key,question,answer,model,input_tokens,output_tokens,status,created_at) VALUES (?,?,?,?,?,?,?,?)", (key, question, result.text, result.model, result.input_tokens, result.output_tokens, status, time.time()))
