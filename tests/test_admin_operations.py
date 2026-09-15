import unittest

from admin_operations import get_operation, list_operations


class AdminOperationTests(unittest.TestCase):
    def test_catalog_includes_common_read_and_write_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertIn("get_channels", operations)
        self.assertIn("post_message", operations)
        self.assertIn("create_schedule", operations)
        self.assertIn("post_group_message", operations)

    def test_catalog_excludes_delete_and_recall_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertFalse(any("delete" in operation for operation in operations))
        self.assertNotIn("recall_message", operations)

    def test_catalog_includes_mute_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertTrue(
            {"mute_member", "mute_multi_member", "mute_all"} <= operations
        )
        self.assertEqual(
            {"guild_id", "user_id", "mute_seconds"},
            {field.name for field in get_operation("mute_member").fields},
        )
        self.assertEqual(
            "json",
            next(
                field.kind
                for field in get_operation("mute_multi_member").fields
                if field.name == "user_ids"
            ),
        )

    def test_operation_exposes_only_declared_fields(self):
        operation = get_operation("post_message")

        self.assertIsNotNone(operation)
        self.assertEqual("post_message", operation.api_method)
        self.assertIn("channel_id", {field.name for field in operation.fields})
        self.assertIn("content", {field.name for field in operation.fields})


if __name__ == "__main__":
    unittest.main()
