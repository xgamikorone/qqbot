"""Group-scoped member observations and command usage, separate from guilds."""

import sqlite3


class GroupRepository:
    """Persists only observed members; it does not imply a full member list."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_command(
        self,
        *,
        group_openid: str,
        member_openid: str,
        display_name: str,
        message_id: str,
        command_name: str,
        command_index: int,
        succeeded: bool,
    ) -> None:
        """Records one chain segment without storing raw arguments/content.

        Group and member IDs form the identity boundary. Re-delivered events
        cannot duplicate usage rows, but this is not command-side-effect dedup.
        """
        with self._connection:
            self._connection.execute(
                """INSERT INTO group_members
                (group_openid, member_openid, display_name)
                VALUES (?, ?, ?) ON CONFLICT(group_openid, member_openid)
                DO UPDATE SET display_name = CASE
                    WHEN excluded.display_name <> '' THEN excluded.display_name
                    ELSE group_members.display_name END,
                    last_seen_at = CURRENT_TIMESTAMP""",
                (group_openid, member_openid, display_name),
            )
            self._connection.execute(
                """INSERT OR IGNORE INTO group_command_records
                (group_openid, member_openid, message_id, command_name,
                 command_index, succeeded) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    group_openid,
                    member_openid,
                    message_id,
                    command_name,
                    command_index,
                    int(succeeded),
                ),
            )
