import unittest

from apscheduler.triggers.cron import CronTrigger

from task_scheduler import CronSchedule, ScheduledTask, TaskScheduler


class FakeScheduler:
    def __init__(self):
        self.running = False
        self.jobs = {}
        self.start_count = 0
        self.shutdown_calls = []

    def add_job(self, callback, **options):
        task_id = options["id"]
        if task_id in self.jobs and not options["replace_existing"]:
            raise AssertionError(f"duplicate fake job: {task_id}")
        self.jobs[task_id] = (callback, options)

    def start(self):
        self.running = True
        self.start_count += 1

    def remove_job(self, task_id):
        del self.jobs[task_id]

    def shutdown(self, wait=True):
        self.running = False
        self.shutdown_calls.append(wait)


def make_task(task_id="demo", callback=lambda: None):
    return ScheduledTask(
        id=task_id,
        description="demo task",
        callback=callback,
        schedule=CronSchedule(hour=4, minute=30),
    )


class CronScheduleTests(unittest.TestCase):
    def test_rejects_invalid_time(self):
        with self.assertRaises(ValueError):
            CronSchedule(hour=24)
        with self.assertRaises(ValueError):
            CronSchedule(hour=0, minute=60)


class TaskSchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = FakeScheduler()
        self.scheduler = TaskScheduler(self.backend)

    def test_register_configures_safe_job_defaults(self):
        task = make_task()

        self.scheduler.register(task)

        self.assertEqual((task,), self.scheduler.list_tasks())
        _, options = self.backend.jobs[task.id]
        self.assertIsInstance(options["trigger"], CronTrigger)
        self.assertEqual((task,), options["args"])
        self.assertTrue(options["coalesce"])
        self.assertEqual(1, options["max_instances"])
        self.assertEqual(300, options["misfire_grace_time"])

    def test_duplicate_registration_requires_replace(self):
        self.scheduler.register(make_task())

        with self.assertRaises(ValueError):
            self.scheduler.register(make_task())

        replacement = make_task(callback=lambda: "replacement")
        self.scheduler.register(replacement, replace=True)
        self.assertEqual((replacement,), self.scheduler.list_tasks())

    def test_start_and_shutdown_are_idempotent(self):
        self.assertTrue(self.scheduler.start())
        self.assertFalse(self.scheduler.start())
        self.assertEqual(1, self.backend.start_count)

        self.assertTrue(self.scheduler.shutdown(wait=False))
        self.assertFalse(self.scheduler.shutdown())
        self.assertEqual([False], self.backend.shutdown_calls)

    async def test_run_now_supports_sync_and_async_callbacks(self):
        calls = []

        async def async_callback():
            calls.append("async")

        self.scheduler.register(make_task("sync", lambda: calls.append("sync")))
        self.scheduler.register(make_task("async", async_callback))

        await self.scheduler.run_now("sync")
        await self.scheduler.run_now("async")

        self.assertEqual(["sync", "async"], calls)

    async def test_run_now_propagates_failure_and_unknown_task(self):
        def fail():
            raise RuntimeError("boom")

        self.scheduler.register(make_task(callback=fail))

        with self.assertRaisesRegex(RuntimeError, "boom"):
            await self.scheduler.run_now("demo")
        with self.assertRaisesRegex(KeyError, "unknown scheduled task"):
            await self.scheduler.run_now("missing")

    def test_remove_updates_backend_and_registry(self):
        self.scheduler.register(make_task())

        self.assertTrue(self.scheduler.remove("demo"))
        self.assertFalse(self.scheduler.remove("demo"))
        self.assertEqual((), self.scheduler.list_tasks())
        self.assertEqual({}, self.backend.jobs)


if __name__ == "__main__":
    unittest.main()
