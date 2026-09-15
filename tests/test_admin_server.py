import unittest

from admin_operations import get_operation
from admin_server import OperationInputError, invoke_operation


class FakeAPI:
    async def post_message(self, **kwargs):
        return kwargs

    async def mute_member(self, **kwargs):
        return kwargs


class FakeClient:
    api = FakeAPI()


class AdminServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_invokes_only_declared_operation_fields(self):
        result = await invoke_operation(
            FakeClient(),
            get_operation("post_message"),
            {"channel_id": "123", "content": "hello"},
        )

        self.assertEqual({"channel_id": "123", "content": "hello"}, result)

    async def test_rejects_unknown_operation_field(self):
        with self.assertRaisesRegex(OperationInputError, "未知参数"):
            await invoke_operation(
                FakeClient(),
                get_operation("post_message"),
                {"channel_id": "123", "content": "hello", "unexpected": True},
            )

    async def test_invokes_member_mute_with_declared_fields(self):
        result = await invoke_operation(
            FakeClient(),
            get_operation("mute_member"),
            {"guild_id": "guild-1", "user_id": "user-1", "mute_seconds": "3600"},
        )

        self.assertEqual(
            {"guild_id": "guild-1", "user_id": "user-1", "mute_seconds": "3600"},
            result,
        )


if __name__ == "__main__":
    unittest.main()
