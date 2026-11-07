"""Checks resource discovery after moving administration and scheduling."""

import contextlib
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from aiohttp import web
from aiohttp import test_utils

from admin import server
from live_forwarding import server as forwarding
from messaging import reply_sources
from scheduling import config


class PackageLayoutTests(unittest.IsolatedAsyncioTestCase):
    """Protects paths which must not depend on the shell working directory."""

    def test_forwarding_and_reply_config_paths_stay_at_repository(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.chdir(directory):
                forwarding.load_config()
                reply_sources.load_config()
        self.assertEqual(root, forwarding.ROOT)
        self.assertEqual(root, reply_sources._ROOT)

    async def test_default_database_paths_do_not_move_with_modules(
            self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        api = mock.Mock()
        with mock.patch.object(reply_sources,
                               "load_config",
                               return_value=reply_sources.Settings()):
            receiver = forwarding.LiveForwardingServer(api,
                                                       forwarding.load_config())
        self.assertEqual(root / "live_forwarding.db",
                         pathlib.Path(receiver.db_path))
        await receiver.close()
        with mock.patch("messaging.reply_sources.sqlite3.connect") as connect:
            pool = reply_sources.ReplySources(
                api, reply_sources.Settings(enabled=True))
            connect.assert_called_once_with(root / "reply_sources.db")
            await pool.close()

    def test_default_schedule_path_is_repository_relative(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.chdir(directory):
                with mock.patch.dict(os.environ, {}, clear=True):
                    loaded = config.load_scheduled_tasks_config()
        self.assertEqual(root / "config" / "scheduled_tasks.yaml",
                         config.DEFAULT_CONFIG_PATH)
        self.assertIn("daily_maintenance_report", loaded.tasks)

    async def test_admin_index_and_assets_survive_directory_change(
            self) -> None:
        panel = server.BotAdminServer(object())
        application = web.Application()
        application.router.add_get("/", panel._index)
        application.router.add_static("/assets", server._STATIC_DIR)
        async with test_utils.TestClient(
                test_utils.TestServer(application)) as browser:
            with tempfile.TemporaryDirectory() as directory:
                with contextlib.chdir(directory):
                    for path, expected in (
                        ("/", "<!doctype html>"),
                        ("/assets/app.js", "const state"),
                        ("/assets/styles.css", ":root"),
                        ("/assets/favicon.svg", "<svg"),
                    ):
                        response = await browser.get(path)
                        self.assertEqual(200, response.status, path)
                        self.assertIn(expected, await response.text())
