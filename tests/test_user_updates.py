import tempfile
import unittest
from datetime import date
from pathlib import Path

from user_updates import (
    UserUpdatesConfigError,
    load_latest_user_update,
    load_updates,
)


class UserUpdatesTests(unittest.TestCase):
    def test_latest_update_ignores_newer_internal_entries(self):
        content = """\
updates:
  - published_at: "2026-08-05"
    title: User feature
    audience: user
    changes:
      - Added a command
  - published_at: "2026-08-06"
    title: Internal refactor
    audience: internal
    changes:
      - Reorganized modules
  - published_at: "2026-08-04"
    title: Older user feature
    audience: user
    changes:
      - Improved output
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "updates.yaml"
            path.write_text(content, encoding="utf-8")
            latest = load_latest_user_update(path)

        self.assertIsNotNone(latest)
        self.assertEqual("User feature", latest.title)
        self.assertEqual(date(2026, 8, 5), latest.published_at)
        self.assertNotIn("Internal refactor", latest.render())

    def test_returns_none_when_there_are_no_user_updates(self):
        content = """\
updates:
  - published_at: "2026-08-06"
    title: Internal only
    audience: internal
    changes:
      - Refactored storage
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "updates.yaml"
            path.write_text(content, encoding="utf-8")
            self.assertIsNone(load_latest_user_update(path))

    def test_render_uses_consistent_user_facing_format(self):
        update = load_latest_user_update()

        self.assertIsNotNone(update)
        rendered = update.render()
        self.assertTrue(rendered.startswith("最近更新 · 2026-08-06"))
        self.assertIn("\n- 新增 /最近更新", rendered)

    def test_rejects_invalid_update_entries(self):
        invalid_configs = {
            "invalid date": """\
updates:
  - published_at: 2026/08/06
    title: Update
    audience: user
    changes: [Changed]
""",
            "invalid audience": """\
updates:
  - published_at: "2026-08-06"
    title: Update
    audience: everyone
    changes: [Changed]
""",
            "empty changes": """\
updates:
  - published_at: "2026-08-06"
    title: Update
    audience: user
    changes: []
""",
            "unknown field": """\
updates:
  - published_at: "2026-08-06"
    title: Update
    audience: user
    changes: [Changed]
    commit: abc123
""",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for name, content in invalid_configs.items():
                with self.subTest(name=name):
                    path = Path(temp_dir) / f"{name}.yaml"
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(UserUpdatesConfigError):
                        load_updates(path)


if __name__ == "__main__":
    unittest.main()
