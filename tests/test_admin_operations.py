import unittest

from admin_operations import get_operation, list_operations


class AdminOperationTests(unittest.TestCase):
    def test_catalog_includes_common_read_and_write_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertIn("get_channels", operations)
        self.assertIn("post_message", operations)
        self.assertIn("create_schedule", operations)
        self.assertIn("post_group_message", operations)

    def test_catalog_excludes_delete_recall_and_mute_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertFalse(any("delete" in operation for operation in operations))
        self.assertNotIn("recall_message", operations)
        self.assertFalse(any("mute" in operation for operation in operations))

    def test_operation_exposes_only_declared_fields(self):
        operation = get_operation("post_message")

        self.assertIsNotNone(operation)
        self.assertEqual("post_message", operation.api_method)
        self.assertIn("channel_id", {field.name for field in operation.fields})
        self.assertIn("content", {field.name for field in operation.fields})


if __name__ == "__main__":
    unittest.main()
