import unittest

from admin_operations import get_operation, list_operations


class AdminOperationTests(unittest.TestCase):
    def test_catalog_includes_common_read_and_write_operations(self):
        operations = {operation.id for operation in list_operations()}

        self.assertIn("get_channels", operations)
        self.assertIn("post_message", operations)
        self.assertIn("create_schedule", operations)
        self.assertIn("post_group_message", operations)

    def test_catalog_only_allows_panel_deletion_and_excludes_recall(self):
        operations = {operation.id for operation in list_operations()}

        self.assertEqual({"delete_panel"}, {operation for operation in operations if "delete" in operation})
        self.assertNotIn("recall_message", operations)

    def test_menu_panel_operations_and_write_confirmations(self):
        reads = {"get_global_menu", "get_panels", "get_panel"}
        writes = {"update_global_menu", "create_panel", "update_panel", "delete_panel", "update_panel_targets"}
        for name in reads | writes:
            operation = get_operation(name)
            self.assertIsNotNone(operation)
            self.assertEqual(name, operation.api_method)
            self.assertEqual(name in writes, bool(operation.as_dict()["confirmation"]))

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
