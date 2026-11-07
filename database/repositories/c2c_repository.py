"""C2C command metadata, independent of guild and group identities."""

import sqlite3


class C2CRepository:
    """Stores usage metadata without private message text or arguments."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_command(
        self,
        *,
        user_openid: str,
        message_id: str,
        command_name: str,
        command_index: int,
        succeeded: bool,
    ) -> None:
        """Deduplicates usage rows, not command execution side effects."""
        with self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO c2c_command_records
                (user_openid, message_id, command_name, command_index, succeeded)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    user_openid,
                    message_id,
                    command_name,
                    command_index,
                    int(succeeded),
                ),
            )
