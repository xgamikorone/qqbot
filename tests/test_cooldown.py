import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from commands.base import cooldown, last_used, _running_commands
from commands.revenue import UserSuperChatCommand


class CooldownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        last_used.clear()
        _running_commands.clear()
        self.command = SimpleNamespace(name="cooldown-test", send_reply=AsyncMock())

    def tearDown(self):
        last_used.clear()
        _running_commands.clear()

    async def test_failure_can_be_immediately_corrected_then_success_is_cooled(self):
        calls = []

        @cooldown(10)
        async def execute(command, message, args):
            calls.append(args)
            return True if args else None

        self.assertIsNone(await execute(self.command, None, []))
        self.assertNotIn(self.command.name, last_used)
        self.assertTrue(await execute(self.command, None, ["valid"]))
        self.assertFalse(await execute(self.command, None, ["valid"]))
        self.assertEqual([[], ["valid"]], calls)

    async def test_exception_does_not_leave_cooldown_or_execution_guard(self):
        @cooldown(10)
        async def execute(command, message, args):
            raise ValueError("invalid argument")

        with self.assertRaises(ValueError):
            await execute(self.command, None, [])
        self.assertNotIn(self.command.name, last_used)
        self.assertNotIn(self.command.name, _running_commands)

    async def test_running_command_is_blocked_and_cooldown_starts_at_completion(self):
        entered = asyncio.Event()
        finish = asyncio.Event()

        @cooldown(10)
        async def execute(command, message, args):
            entered.set()
            await finish.wait()
            return True

        with patch("commands.base.monotonic", return_value=100) as clock:
            task = asyncio.create_task(execute(self.command, None, []))
            await entered.wait()
            try:
                self.assertFalse(await execute(self.command, None, []))
            finally:
                clock.return_value = 150
                finish.set()
                await task
            self.assertEqual(150, last_used[self.command.name])
            self.assertFalse(await execute(self.command, None, []))
            self.assertNotIn(self.command.name, _running_commands)

    async def test_real_command_missing_arguments_does_not_consume_cooldown(self):
        command = UserSuperChatCommand(SimpleNamespace())
        command.send_reply = AsyncMock()
        message = SimpleNamespace(member=SimpleNamespace(roles=[]))
        with patch("commands.revenue.is_admin_or_owner", return_value=True):
            await command.execute(message, [])
            await command.execute(message, [])
        self.assertNotIn(command.name, last_used)
        self.assertEqual(2, command.send_reply.await_count)
        self.assertTrue(all(
            call.args[1] == "请输入要查询的用户uid或昵称"
            for call in command.send_reply.await_args_list
        ))


if __name__ == "__main__":
    unittest.main()
