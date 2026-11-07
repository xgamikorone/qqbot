import textwrap

from botpy import message as botpy_message

from . import base
from . import help_catalog

birthday_template = textwrap.dedent("""\
    {to}，今天是你的生日，{from_}为你献上了生日祝福：
    ✨🎉 对所有的烦恼说 bye bye 👋💫
    🎈💖 对所有的快乐说 hi hi 🌈✨
    🎂🎀 亲爱的亲爱的{to}生日快乐 🎊🥳
    🌟✨ 每一天都精彩 🌸💐
    🌺🌼 看幸福的花儿为你盛开 🌷🌷
    🎵🎶 听美妙的音乐为你喝彩 👏✨
    🎂🎉 亲爱的亲爱的{to}生日快乐 💖🎁
    💝🌟 祝你幸福永远 ✨
    ♾️💖 幸福永远 🎊🎊
""")


@base.command("生日快乐", "happy_birthday")
class BirthdayCommand(base.Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "birthday"
    cn_name = "生日快乐"
    help = help_catalog.CommandHelp(
        title="生日快乐",
        category="娱乐",
        summary="生成一条生日祝福",
        usage="/生日快乐 <过生日的人> [送祝福的人]",
        examples=("/生日快乐 又一", "/生日快乐 又一 丸子"),
        details="用法：/生日快乐 <过生日的人> [送祝福的人]\n"
        "频道默认提及发起人；群聊使用可用昵称，缺失时显示“一位朋友”。\n"
        "也可以手动填写送祝福的人，例如：/生日快乐 又一 丸子。",
    )

    @staticmethod
    def build_greeting(recipient: str, sender: str) -> str:
        """Renders the shared template without inspecting SDK identities."""
        return birthday_template.format(to=recipient, from_=sender).strip()

    async def execute(self, message: botpy_message.Message,
                      args: list[str]) -> bool:
        """Preserves compatibility with old direct channel callers."""
        return await self.execute_guild(message, args)

    async def execute_guild(self, message: botpy_message.Message,
                            args: list[str]) -> bool:
        """Preserves the existing channel mention and explicit sender rules."""
        if not args:
            await self.reply_guild(message, "请输入生日的用户!")
            return False
        sender = args[1] if len(args) > 1 else f"<@!{message.author.id}>"
        await self.reply_guild(message, self.build_greeting(args[0], sender))
        return True

    async def execute_group(self, message: botpy_message.GroupMessage,
                            args: list[str]) -> bool:
        """Uses available group display names without formatting OpenID as @."""
        if not args:
            await self.reply_group(message, "请输入生日的用户!")
            return False
        name = getattr(message.author, "username", "")
        default_sender = name.strip() if isinstance(name, str) else ""
        sender = args[1] if len(args) > 1 else default_sender or "一位朋友"
        await self.reply_group(message, self.build_greeting(args[0], sender))
        return True
