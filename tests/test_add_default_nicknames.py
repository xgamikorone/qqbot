import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from add_default_nicknames import add_default_nicknames


class AddDefaultNicknamesTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_number_of_added_nicknames(self):
        users = [
            {"uid": 1, "name": "Alice"},
            {"uid": 2, "name": "Bob"},
        ]
        nicknames = Mock()
        nicknames.add.side_effect = [True, False]
        dao = SimpleNamespace(nicknames=nicknames)

        with (
            patch(
                "add_default_nicknames.get_all_streamers",
                new=AsyncMock(return_value=users),
            ),
            patch("add_default_nicknames.get_dao", return_value=dao),
        ):
            added_count = await add_default_nicknames()

        self.assertEqual(1, added_count)
        self.assertEqual(
            [((1, "Alice"),), ((2, "Bob"),)],
            [call for call in nicknames.add.call_args_list],
        )

    async def test_api_failure_is_reported_to_scheduler(self):
        with patch(
            "add_default_nicknames.get_all_streamers",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "cannot fetch all streamers"):
                await add_default_nicknames()


if __name__ == "__main__":
    unittest.main()
