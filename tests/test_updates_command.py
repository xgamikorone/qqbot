import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from commands.base import _command_registry
from commands.help_catalog import HelpCatalog
from commands.updates import RecentUpdatesCommand
from user_updates import UserUpdate, UserUpdatesConfigError


class RecentUpdatesCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = SimpleNamespace(post_message=AsyncMock())
        self.command = RecentUpdatesCommand(SimpleNamespace(api=self.api))
        self.message = SimpleNamespace(channel_id="channel", id="message")

    async def test_replies_with_latest_user_update(self):
        update = UserUpdate(
            published_at=date(2026, 8, 6),
            title="New feature",
            audience="user",
            changes=("Added /recent",),
        )

        with patch("commands.updates.load_latest_user_update", return_value=update):
            await self.command.execute(self.message, [])

        self.api.post_message.assert_awaited_once_with(
            channel_id="channel",
            content=update.render(),
            msg_id="message",
        )

    async def test_reports_missing_or_invalid_update_feed(self):
        with patch("commands.updates.load_latest_user_update", return_value=None):
            await self.command.execute(self.message, [])
        self.assertIn(
            "暂无面向用户",
            self.api.post_message.await_args.kwargs["content"],
        )

        self.api.post_message.reset_mock()
        with patch(
            "commands.updates.load_latest_user_update",
            side_effect=UserUpdatesConfigError("broken"),
        ):
            await self.command.execute(self.message, [])
        self.assertIn(
            "暂时无法获取",
            self.api.post_message.await_args.kwargs["content"],
        )

    def test_command_is_registered_and_visible_in_help(self):
        self.assertIs(RecentUpdatesCommand, _command_registry["最近更新"])
        self.assertIn("/最近更新", HelpCatalog(_command_registry).render())


if __name__ == "__main__":
    unittest.main()
