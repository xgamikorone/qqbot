import unittest

from admin_operations import get_operation
from admin_server import OperationInputError, invoke_operation


class FakeAPI:
    async def post_message(self, **kwargs):
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


if __name__ == "__main__":
    unittest.main()
