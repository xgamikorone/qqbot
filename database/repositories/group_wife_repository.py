"""Daily group wife assignments backed by the shared resource catalog."""

import dataclasses
import sqlite3


@dataclasses.dataclass(frozen=True)
class WifeAsset:
    """Shared catalog image referenced by an isolated group assignment."""

    id: int
    name: str
    url: str
    enabled: bool = True


class GroupWifeRepository:
    """Atomically draws once per group/member/date without channel writes."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_for_date(
        self, group_id: str, member_id: str, date: str
    ) -> WifeAsset | None:
        """Reads historical assignments even if their resource is disabled."""
        row = self._connection.execute(
            "SELECT w.id, w.name, w.url, w.enabled FROM group_wife_daily d "
            "JOIN wife_urls w ON w.id=d.wife_id "
            "WHERE d.group_openid=? AND d.member_openid=? AND d.date=?",
            (group_id, member_id, date),
        ).fetchone()
        return (
            WifeAsset(row[0], row[1] or "未命名", row[2], bool(row[3]))
            if row
            else None
        )

    def get_or_draw(
        self, group_id: str, member_id: str, date: str
    ) -> WifeAsset | None:
        """Serializes concurrent first draws, selecting only enabled assets."""
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self.get_for_date(group_id, member_id, date)
            if existing is not None:
                return existing
            row = self._connection.execute(
                "SELECT id FROM wife_urls WHERE enabled=1 ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._connection.execute(
                "INSERT INTO group_wife_daily (group_openid, member_openid, date, wife_id) "
                "VALUES (?, ?, ?, ?)",
                (group_id, member_id, date, row[0]),
            )
            return self.get_for_date(group_id, member_id, date)
