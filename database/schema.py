import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scheduled_message_sends (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL,
    audit_id TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '',
    code INTEGER,
    error_type TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_scheduled_message_audit
ON scheduled_message_sends(audit_id);
CREATE TABLE IF NOT EXISTS message_audit_events (
    audit_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    message_id TEXT NOT NULL DEFAULT '',
    guild_id TEXT NOT NULL DEFAULT '',
    channel_id TEXT NOT NULL DEFAULT '',
    audit_time TEXT NOT NULL DEFAULT '',
    create_time TEXT NOT NULL DEFAULT '',
    seq_in_channel TEXT NOT NULL DEFAULT '',
    received_at REAL NOT NULL
);
CREATE VIEW IF NOT EXISTS scheduled_message_delivery AS
SELECT s.attempt_id, s.task_id, s.channel_id,
       COALESCE(e.status, s.status) AS status, s.audit_id,
       COALESCE(NULLIF(e.message_id, ''), s.message_id) AS message_id,
       s.code, s.error_type, s.created_at, s.updated_at,
       e.guild_id, e.audit_time, e.create_time, e.seq_in_channel,
       e.received_at
FROM scheduled_message_sends s LEFT JOIN message_audit_events e
ON s.audit_id = e.audit_id
AND (e.channel_id = '' OR s.channel_id = e.channel_id);
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 30000;
CREATE TABLE IF NOT EXISTS chat_sessions (session_key TEXT PRIMARY KEY, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS chat_turns (
    id INTEGER PRIMARY KEY, session_key TEXT NOT NULL, question TEXT NOT NULL,
    answer TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_turns_session ON chat_turns(session_key,id);
CREATE TABLE IF NOT EXISTS chat_requests (
    id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, day TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_requests_day ON chat_requests(user_id,day);
CREATE TABLE IF NOT EXISTS chat_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_key TEXT NOT NULL,
    answer TEXT NOT NULL, answer_chars INTEGER NOT NULL,
    model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL, status TEXT NOT NULL,
    error_type TEXT NOT NULL DEFAULT '', error_text TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_deliveries_expiry
ON chat_deliveries(expires_at);
CREATE INDEX IF NOT EXISTS idx_chat_deliveries_session
ON chat_deliveries(session_key);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    uid INTEGER NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS user_nicknames (
    id INTEGER PRIMARY KEY,
    uid INTEGER NOT NULL,
    nickname TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_nickname ON user_nicknames(nickname);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS bot_owners (
    user_id TEXT PRIMARY KEY,
    note TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS command_records (
    id INTEGER PRIMARY KEY,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    command_name TEXT NOT NULL,
    command_args TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_command_records_created_at
ON command_records(created_at);

CREATE TABLE IF NOT EXISTS wife_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
);

CREATE TABLE IF NOT EXISTS user_wife_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    wife_id INTEGER NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
    UNIQUE (user_id, date),
    FOREIGN KEY (wife_id) REFERENCES wife_urls(id)
);

CREATE TABLE IF NOT EXISTS user_chuang_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    distance INTEGER NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
    UNIQUE (user_id, date)
);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
