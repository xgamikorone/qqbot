"""Atomic daily game results, isolated from channels and other groups."""

import collections.abc
import dataclasses
import sqlite3


@dataclasses.dataclass(frozen=True)
class DailyResult:
    """Stable daily distance and record flag, with current group rankings."""

    distance: int
    personal_record: bool
    daily_rank: int
    history_rank: int


class GroupChuangRepository:
    """Stores one result per group/member/Beijing date."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_or_create(
        self,
        group_id: str,
        member_id: str,
        date: str,
        draw: collections.abc.Callable[[], int],
    ) -> DailyResult:
        """Serializes first draws across connections; repeats never draw again.

        Equal distances share a rank. Historical rank compares each member's
        personal best within the same group.
        """
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT distance, personal_record FROM group_chuang_daily "
                "WHERE group_openid=? AND member_openid=? AND date=?",
                (group_id, member_id, date),
            ).fetchone()
            if row is None:
                previous = (
                    self._connection.execute(
                        "SELECT MAX(distance) FROM group_chuang_daily "
                        "WHERE group_openid=? AND member_openid=?",
                        (group_id, member_id),
                    ).fetchone()[0]
                    or 0
                )
                distance = draw()
                personal_record = distance > previous
                self._connection.execute(
                    "INSERT INTO group_chuang_daily "
                    "(group_openid, member_openid, date, distance, personal_record) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (group_id, member_id, date, distance, int(personal_record)),
                )
            else:
                distance, personal_record = row[0], bool(row[1])
            daily_rank = self._connection.execute(
                "SELECT COUNT(*)+1 FROM group_chuang_daily "
                "WHERE group_openid=? AND date=? AND distance>?",
                (group_id, date, distance),
            ).fetchone()[0]
            history_rank = self._connection.execute(
                "SELECT COUNT(*)+1 FROM (SELECT MAX(distance) AS best "
                "FROM group_chuang_daily WHERE group_openid=? "
                "GROUP BY member_openid) WHERE best>?",
                (group_id, distance),
            ).fetchone()[0]
        return DailyResult(distance, personal_record, daily_rank, history_rank)
