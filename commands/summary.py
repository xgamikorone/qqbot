"""Three-step quoted channel range summarization commands."""

from botpy import message as botpy_message

from botpy_ext import channel_history
from chat import model_client
from chat import summary
from . import base
from . import help_catalog
from . import text_query


class SummaryCommand(base.Command):
    """Shared command entry preserving the original SDK Message reference."""

    action = "generate"

    async def execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        service = getattr(self.client, "summary_service", None)
        if not isinstance(service, summary.SummaryService):
            await self.reply_guild(message, "AI 总结尚未启用。")
            return False
        key = (
            str(message.guild_id),
            str(message.channel_id),
            str(message.author.id),
        )
        if args:
            await self.reply_guild(
                message, "这些命令不需要参数；起点和终点请使用引用消息。"
            )
            return False
        try:
            if self.action in {"start", "end"}:
                identifier = message.message_reference.message_id
                if not identifier:
                    raise model_client.ChatError(
                        "请引用一条当前子频道消息后再发送标记命令。"
                    )
                await service.mark(
                    key, identifier, start=self.action == "start"
                )
                await self.reply_guild(
                    message,
                    (
                        "已设置总结起点（原终点已清除）。"
                        if self.action == "start"
                        else "已设置总结终点，请发送 /开始总结。"
                    ),
                )
            else:
                content = await service.summarize(key)
                for chunk in text_query.split_group_text(content):
                    await self.reply_guild(message, chunk)
            return True
        except (model_client.ChatError, channel_history.HistoryError) as error:
            await self.reply_guild(message, str(error))
            return False
        except Exception:
            await self.reply_guild(
                message,
                "读取频道记录或生成总结失败，请检查消息读取权限和模型配置。",
            )
            return False

    async def after_execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> None:
        """Keeps quoted request bodies and summaries out of command storage."""
        return


@base.command("总结起点")
class StartSummaryCommand(SummaryCommand):
    name = "summary_start"
    cn_name = "总结起点"
    action = "start"
    help = help_catalog.CommandHelp(
        title="总结起点",
        category="工具",
        summary="引用消息设置频道总结起点",
        usage="引用起点消息后发送 /总结起点",
    )


@base.command("总结终点")
class EndSummaryCommand(SummaryCommand):
    name = "summary_end"
    cn_name = "总结终点"
    action = "end"
    help = help_catalog.CommandHelp(
        title="总结终点",
        category="工具",
        summary="引用消息设置频道总结终点",
        usage="引用终点消息后发送 /总结终点",
    )


@base.command("开始总结")
class GenerateSummaryCommand(SummaryCommand):
    name = "summary_generate"
    cn_name = "开始总结"
    help = help_catalog.CommandHelp(
        title="开始总结",
        category="工具",
        summary="将选定区间的可见消息发送给已配置的大模型总结",
        usage="/开始总结",
        details="依次引用起点、终点发送 /总结起点、/总结终点，最后发送 /开始总结。仅处理文字和附件标记；逐条查询最多200条，遇到失败时总结从起点连续读取成功的部分并注明范围；列表查询最多500条。仍受模型输入长度限制。内容会发送到配置的模型供应商；仅限已开放聊天功能的子频道，不写入个人会话历史。",
    )
