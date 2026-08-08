import sqlite3


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 30000;
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
