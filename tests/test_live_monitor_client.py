import os
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from live_monitor_client import (
    LiveMonitorError,
    check_live_monitor_health,
)


def health_payload(*, healthy: bool = True) -> dict:
    return {
        "status": "healthy" if healthy else "unhealthy",
        "components": {
            "LiveMonitor": {
                "healthy": healthy,
                "status": "running" if healthy else "stale",
                "age_seconds": 2.5 if healthy else 45.0,
            },
            "RevenueMonitor": {
                "healthy": healthy,
                "status": "running" if healthy else "stale",
                "age_seconds": 3,
            },
        },
    }


class LiveMonitorClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_health_endpoint_with_bearer_authentication(self):
        received: dict[str, str] = {}

        async def handle_health(request: web.Request) -> web.Response:
            received["authorization"] = request.headers.get("Authorization", "")
            received["max_age_seconds"] = request.query.get("max_age_seconds", "")
            return web.json_response(health_payload())

        app = web.Application()
        app.router.add_get("/monitor/health", handle_health)
        server = TestServer(app)
        await server.start_server()
        try:
            with patch.dict(
                os.environ,
                {
                    "LIVE_MONITOR_BASE_URL": str(server.make_url("/")).rstrip("/"),
                    "LIVE_MONITOR_API_TOKEN": "test-token",
                },
                clear=True,
            ):
                health = await check_live_monitor_health(45)
        finally:
            await server.close()

        self.assertTrue(health.healthy)
        self.assertEqual("healthy", health.status)
        self.assertEqual("Bearer test-token", received["authorization"])
        self.assertEqual("45", received["max_age_seconds"])
        self.assertIn("LiveMonitor：正常", health.render())

    async def test_preserves_unhealthy_503_as_a_health_result(self):
        async def handle_health(request: web.Request) -> web.Response:
            return web.json_response(health_payload(healthy=False), status=503)

        app = web.Application()
        app.router.add_get("/monitor/health", handle_health)
        server = TestServer(app)
        await server.start_server()
        try:
            with patch.dict(
                os.environ,
                {
                    "LIVE_MONITOR_BASE_URL": str(server.make_url("/")).rstrip("/"),
                    "LIVE_MONITOR_API_TOKEN": "test-token",
                },
                clear=True,
            ):
                health = await check_live_monitor_health()
        finally:
            await server.close()

        self.assertFalse(health.healthy)
        self.assertIn("Live Monitor：异常", health.render())
        self.assertIn("LiveMonitor：异常（stale，心跳 45.0 秒前）", health.render())

    async def test_rejects_missing_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(LiveMonitorError, "BASE_URL"):
                await check_live_monitor_health()

    async def test_validates_maximum_heartbeat_age(self):
        for value in (4, 301, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    await check_live_monitor_health(value)


if __name__ == "__main__":
    unittest.main()
