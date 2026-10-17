import re

from .base import Command, command, cooldown
from .help_catalog import CommandHelp
from utils.baidu_translate import MAX_TEXT_LENGTH, TranslationError, translate


LANGUAGE_NAMES = {
    "中文": "zh", "英语": "en", "英文": "en", "日语": "jp", "日文": "jp",
    "韩语": "kor", "法语": "fra", "德语": "de", "西班牙语": "spa",
    "俄语": "ru", "繁体中文": "cht", "自动": "auto",
}


def parse_arguments(args: list[str]) -> tuple[str, str, str]:
    source, target = "auto", "zh"
    index = 0
    seen = set()
    while index < len(args):
        option = args[index]
        if option == "--":
            index += 1
            break
        if not option.startswith(("/", "--")):
            break
        if option not in {"/f", "/t"} or option in seen:
            raise TranslationError("参数错误，用法：/翻译 [/f auto] [/t zh] 文本")
        if index + 1 >= len(args):
            raise TranslationError(f"{option} 后需要填写语言代码，例如 en、zh、jp。")
        language = LANGUAGE_NAMES.get(args[index + 1], args[index + 1].lower())
        if not re.fullmatch(r"[a-z]{2,8}", language) or (option == "/t" and language == "auto"):
            raise TranslationError("语言代码无效；目标语言不能为 auto。常用代码：zh/en/jp/kor。")
        if option == "/f":
            source = language
        else:
            target = language
        seen.add(option)
        index += 2
    text = " ".join(args[index:]).strip()
    if not text:
        raise TranslationError("请输入要翻译的文本，例如：/翻译 Hello world；/翻译 /t en 你好")
    if len(text) > MAX_TEXT_LENGTH:
        raise TranslationError(f"单次最多翻译 {MAX_TEXT_LENGTH} 个字符，请分段发送。")
    return source, target, text


@command("翻译", "translate")
class TranslateCommand(Command):
    name = "translate"
    cn_name = "翻译"
    help = CommandHelp(
        title="翻译", category="工具", summary="使用百度翻译文本，默认自动识别并译为中文",
        usage="/翻译 [/f 源语言] [/t 目标语言] 文本",
        examples=("/翻译 Hello world", "/翻译 /t en 你好", "/翻译 /f jp /t zh こんにちは"),
        details=("用法：/翻译 [/f 源语言] [/t 目标语言] 文本\n"
                 "例子：/翻译 Hello world\n/翻译 /t en 你好\n/翻译 /f jp /t zh こんにちは\n\n"
                 "默认自动识别原文，目标语言为中文（zh）；源语言可用 auto，目标语言不能为 auto。\n"
                 "常用代码：zh 中文、en 英语、jp 日语、kor 韩语、fra 法语、de 德语。"
                 "也支持上述中文语言名。/f 指定源语言，/t 指定目标语言。参数放在文本前；用 -- 分隔可翻译以 / 或 -- 开头的文本。\n"
                 "单次最多 1000 字符，成功后全局冷却 3 秒。文本会发送给百度，请勿提交敏感信息。"
                 "命令记录沿用 Bot 现有机制；连续空白会被命令解析器合并。"),
    )

    @cooldown(3)
    async def execute(self, message, args: list[str]):
        try:
            source, target, text = parse_arguments(args)
            result = await translate(text, source=source, target=target)
        except TranslationError as error:
            await self.send_reply(message, str(error))
            return False
        output = result.text
        if len(output) > 3500:
            output = output[:3500] + "\n（译文过长，已截断；请缩短原文后重试）"
        await self.send_reply(message, f"翻译（{result.source} → {result.target}）：\n{output}")
        return True
