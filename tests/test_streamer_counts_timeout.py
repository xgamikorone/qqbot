import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from commands import api
from commands.guards import FollowersCommand, GuardsCommand


class StreamerCountsTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_count_requests_override_timeout_and_preserve_response(self):
        expected = {"1": {"num_guards": 2, "num_followers": 10}}
        response = SimpleNamespace(json=AsyncMock(return_value={"data": expected}))
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = Mock()
        session.get.return_value = context

        with patch.object(api, "get_session", new=AsyncMock(return_value=session)):
            for function, args in (
                (api.get_num_guards, ([1], [101])),
                (api.get_num_followers, ([1],)),
            ):
                with self.subTest(function=function.__name__):
                    self.assertEqual(expected, await function(*args))
                    timeout = session.get.call_args.kwargs["timeout"]
                    self.assertEqual(180, timeout.total)
                    self.assertEqual(150, timeout.sock_read)
                    self.assertEqual(20, timeout.connect)
                    self.assertEqual(20, timeout.sock_connect)

            await api.get_user_info_by_uids([1])
            self.assertNotIn("timeout", session.get.call_args.kwargs)

    async def test_commands_send_waiting_message_before_querying_counts(self):
        for command_class, function_name, args in (
            (GuardsCommand, "get_num_guards", ([1], [101])),
            (FollowersCommand, "get_num_followers", ([1],)),
        ):
            with self.subTest(command=command_class.__name__):
                command = command_class(SimpleNamespace())
                command.send_reply = AsyncMock()
                message = SimpleNamespace()

                async def query(*actual_args):
                    self.assertEqual(args, actual_args)
                    self.assertEqual(1, command.send_reply.await_count)
                    self.assertIn("正在查询 1 位主播", command.send_reply.await_args.args[1])
                    return None

                with (
                    patch("commands.guards.get_tagged_streamers", new=AsyncMock(
                        return_value=[{"uid": 1}],
                    )),
                    patch("commands.guards.get_user_info_by_uids", new=AsyncMock(
                        return_value={"1": {"name": "Alice", "room_id": 101}},
                    )),
                    patch(f"commands.guards.{function_name}", new=AsyncMock(side_effect=query)),
                ):
                    await command.execute(message, [])
                self.assertIn("失败", command.send_reply.await_args.args[1])


if __name__ == "__main__":
    unittest.main()
