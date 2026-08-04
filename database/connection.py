import sqlite3


def create_connection(db_name: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_name, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection
