import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from commands.guards import GuardsCommand, FollowersCommand
from scheduled_jobs import generate_fans_and_guards_message


USERS = {
    "1": {"uid": 1, "name": "NoRoom", "room_id": None},
    "2": {"uid": 2, "name": "Streamer", "room_id": 102},
}
COUNTS = {"2": {"num_guards": 3, "guard_num_1": 0, "guard_num_2": 0, "guard_num_3": 3}}
FANS = {"1": {"num_followers": 10}, "2": {"num_followers": 20}}


class StreamersWithoutRoomsTests(unittest.IsolatedAsyncioTestCase):
    async def test_guards_filters_pairs_and_explains_missing_room(self):
        command = GuardsCommand(SimpleNamespace())
        command.send_reply = AsyncMock()
        with (
            patch("commands.guards.get_tagged_streamers", new=AsyncMock(return_value=[{"uid": 1}, {"uid": 2}])),
            patch("commands.guards.get_user_info_by_uids", new=AsyncMock(return_value=USERS)),
            patch("commands.guards.get_num_guards", new=AsyncMock(return_value=COUNTS)) as get_guards,
        ):
            await command.execute(SimpleNamespace(), [])
        get_guards.assert_awaited_once_with([2], [102])
        content = command.send_reply.await_args.args[1]
        self.assertIn("NoRoom：暂无直播间", content)
        self.assertIn("Streamer: 3", content)

    async def test_all_users_without_rooms_skips_network_lookup(self):
        command = GuardsCommand(SimpleNamespace())
        command.send_reply = AsyncMock()
        with (
            patch("commands.guards.get_tagged_streamers", new=AsyncMock(return_value=[{"uid": 1}])),
            patch("commands.guards.get_user_info_by_uids", new=AsyncMock(return_value=USERS)),
            patch("commands.guards.get_num_guards", new=AsyncMock()) as get_guards,
        ):
            await command.execute(SimpleNamespace(), [])
        get_guards.assert_not_awaited()
        self.assertIn("NoRoom：暂无直播间", command.send_reply.await_args.args[1])

    async def test_followers_keeps_roomless_users(self):
        command = FollowersCommand(SimpleNamespace())
        command.send_reply = AsyncMock()
        with (
            patch("commands.guards.get_tagged_streamers", new=AsyncMock(return_value=[{"uid": 1}, {"uid": 2}])),
            patch("commands.guards.get_user_info_by_uids", new=AsyncMock(return_value=USERS)),
            patch("commands.guards.get_num_followers", new=AsyncMock(return_value=FANS)) as get_followers,
        ):
            await command.execute(SimpleNamespace(), [])
        get_followers.assert_awaited_once_with([1, 2])
        self.assertIn("NoRoom: 10", command.send_reply.await_args.args[1])

    async def test_scheduled_report_preserves_followers_but_filters_guard_rooms(self):
        with (
            patch.dict("scheduled_jobs.categories", {"test": [1, 2]}),
            patch("scheduled_jobs.get_user_info_by_uids", new=AsyncMock(return_value=USERS)),
            patch("scheduled_jobs.get_num_followers", new=AsyncMock(return_value=FANS)),
            patch("scheduled_jobs.get_num_guards", new=AsyncMock(return_value=COUNTS)) as get_guards,
        ):
            content = await generate_fans_and_guards_message("test")
        get_guards.assert_awaited_once_with([2], [102])
        self.assertIn("NoRoom: 10", content)
        self.assertIn("NoRoom：暂无直播间", content)


if __name__ == "__main__":
    unittest.main()
