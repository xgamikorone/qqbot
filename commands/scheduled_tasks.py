from typing import List

from botpy import logging
from botpy.message import Message

from .base import Command, command
from .help_catalog import CommandHelp


_log = logging.get_logger(__name__)


@command("测试定时任务", "run_scheduled_task")
class RunScheduledTaskCommand(Command):
    name = "run_scheduled_task"
    cn_name = "测试定时任务"
    owner_only = True
    help = CommandHelp(
        title="测试定时任务",
        category="管理",
        summary="立即执行一个已注册的定时任务",
        usage="/测试定时任务 [任务 ID]",
        examples=(
            "/测试定时任务",
            "/测试定时任务 daily_maintenance_report",
        ),
        details=(
            "测试定时任务\n"
            "立即执行一个已注册的定时任务，执行逻辑与定时触发完全相同。\n\n"
            "不带任务 ID 时列出当前可测试的任务。\n\n"
            "用法：\n"
            "/测试定时任务 [任务 ID]"
        ),
    )

    async def execute(self, message: Message, args: List[str]):
        scheduler = getattr(self.client, "task_scheduler", None)
        if scheduler is None:
            await self.send_reply(message, "定时任务调度器尚未初始化。")
            return

        tasks = scheduler.list_tasks()
        if not args:
            if not tasks:
                await self.send_reply(message, "当前没有已注册的定时任务。")
                return
            lines = ["可测试的定时任务："]
            lines.extend(f"- {task.id}：{task.description}" for task in tasks)
            lines.append("\n用法：/测试定时任务 <任务 ID>")
            await self.send_reply(message, "\n".join(lines))
            return

        task_id = args[0]
        task_by_id = {task.id: task for task in tasks}
        task = task_by_id.get(task_id)
        if task is None:
            await self.send_reply(message, f"未找到已注册的定时任务：{task_id}")
            return

        await self.send_reply(message, f"开始执行定时任务：{task.id}")
        try:
            await scheduler.run_now(task.id)
        except Exception:
            _log.exception("manual scheduled task execution failed: id=%s", task.id)
            await self.send_reply(
                message,
                f"定时任务执行完成，但结果异常：{task.id}。请查看汇报频道和程序日志。",
            )
            return

        await self.send_reply(message, f"定时任务执行成功：{task.id}")
