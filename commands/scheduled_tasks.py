import re
from typing import List

from botpy import logging
from botpy.message import Message
from scheduled_task_errors import ScheduledTaskParameterError

from .base import Command, command
from .help_catalog import CommandHelp


_log = logging.get_logger(__name__)


def parse_task_parameter_overrides(args: List[str]) -> dict[str, object]:
    overrides: dict[str, object] = {}
    for argument in args:
        name, separator, raw_value = argument.partition("=")
        if (
            not separator
            or not re.fullmatch(r"[a-z][a-z0-9_]*", name)
            or not raw_value
        ):
            raise ValueError(f"参数必须使用 key=value 格式：{argument}")
        if name in overrides:
            raise ValueError(f"参数重复：{name}")
        overrides[name] = _parse_parameter_value(raw_value)
    return overrides


def _parse_parameter_value(value: str) -> object:
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return value


@command("测试定时任务", "run_scheduled_task")
class RunScheduledTaskCommand(Command):
    name = "run_scheduled_task"
    cn_name = "测试定时任务"
    owner_only = True
    help = CommandHelp(
        title="测试定时任务",
        category="管理",
        summary="立即执行一个已注册的定时任务",
        usage="/测试定时任务 [任务 ID] [key=value ...]",
        examples=(
            "/测试定时任务",
            "/测试定时任务 daily_maintenance_report",
            "/测试定时任务 daily_maintenance_report usage_top_limit=10",
        ),
        details=(
            "测试定时任务\n"
            "立即执行一个已注册的定时任务，执行逻辑与定时触发完全相同。\n\n"
            "不带任务 ID 时列出当前可测试的任务。参数使用 key=value 格式，"
            "只能覆盖任务明确允许的参数。\n\n"
            "用法：\n"
            "/测试定时任务 [任务 ID] [key=value ...]"
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
            lines.append(
                "\n用法：/测试定时任务 <任务 ID> [key=value ...]"
            )
            await self.send_reply(message, "\n".join(lines))
            return

        task_id = args[0]
        try:
            parameter_overrides = parse_task_parameter_overrides(args[1:])
        except ValueError as error:
            await self.send_reply(message, f"参数格式错误：{error}")
            return

        task_by_id = {task.id: task for task in tasks}
        task = task_by_id.get(task_id)
        if task is None:
            await self.send_reply(message, f"未找到已注册的定时任务：{task_id}")
            return

        parameter_text = " ".join(args[1:])
        suffix = f"（参数：{parameter_text}）" if parameter_text else ""
        await self.send_reply(message, f"开始执行定时任务：{task.id}{suffix}")
        try:
            runner = getattr(self.client, "run_scheduled_task", None)
            if runner is None:
                await self.send_reply(message, "手动任务执行器尚未初始化。")
                return
            await runner(task.id, parameter_overrides)
        except ScheduledTaskParameterError as error:
            await self.send_reply(message, f"任务参数错误：{error}")
            return
        except Exception:
            _log.exception("manual scheduled task execution failed: id=%s", task.id)
            await self.send_reply(
                message,
                f"定时任务执行完成，但结果异常：{task.id}。请查看汇报频道和程序日志。",
            )
            return

        await self.send_reply(message, f"定时任务执行成功：{task.id}")
