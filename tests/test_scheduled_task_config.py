import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scheduled_task_config import (
    ScheduledTaskConfigError,
    load_scheduled_tasks_config,
)


class ScheduledTaskConfigTests(unittest.TestCase):
    def test_loads_repository_default_config(self):
        config = load_scheduled_tasks_config()

        self.assertEqual("Asia/Shanghai", str(config.timezone))
        self.assertEqual(
            {"daily_maintenance_report", "send_fans_and_guards_message"},
            set(config.tasks),
        )
        message_task = config.tasks["send_fans_and_guards_message"]
        self.assertEqual(23, message_task.schedule.hour)
        self.assertEqual("8338248", message_task.parameters["channel_id"])

    def test_environment_can_select_another_config_file(self):
        content = """\
timezone: UTC
tasks:
  daily_maintenance_report:
    enabled: false
    schedule:
      hour: 1
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "tasks.yaml"
            config_path.write_text(content, encoding="utf-8")
            with patch.dict(
                os.environ, {"SCHEDULED_TASKS_CONFIG": str(config_path)}
            ):
                config = load_scheduled_tasks_config()

        self.assertEqual("UTC", str(config.timezone))
        self.assertFalse(config.tasks["daily_maintenance_report"].enabled)
        self.assertEqual(0, config.tasks["daily_maintenance_report"].schedule.minute)

    def test_rejects_unknown_fields_and_invalid_values(self):
        invalid_configs = {
            "unknown root field": "timezone: UTC\nextra: true\ntasks: {}\n",
            "invalid timezone": "timezone: Mars/Olympus\ntasks: {}\n",
            "invalid enabled": (
                "tasks:\n"
                "  task:\n"
                "    enabled: yes-please\n"
                "    schedule: {hour: 1}\n"
            ),
            "invalid hour": (
                "tasks:\n"
                "  task:\n"
                "    schedule: {hour: 24}\n"
            ),
            "unknown schedule field": (
                "tasks:\n"
                "  task:\n"
                "    schedule: {hour: 1, timezone: UTC}\n"
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for name, content in invalid_configs.items():
                with self.subTest(name=name):
                    config_path = Path(temp_dir) / f"{name}.yaml"
                    config_path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ScheduledTaskConfigError):
                        load_scheduled_tasks_config(config_path)

    def test_rejects_invalid_yaml_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.yaml"
            invalid_path.write_text("tasks: [", encoding="utf-8")
            with self.assertRaisesRegex(ScheduledTaskConfigError, "invalid YAML"):
                load_scheduled_tasks_config(invalid_path)

            missing_path = Path(temp_dir) / "missing.yaml"
            with self.assertRaisesRegex(ScheduledTaskConfigError, "cannot read"):
                load_scheduled_tasks_config(missing_path)


if __name__ == "__main__":
    unittest.main()
