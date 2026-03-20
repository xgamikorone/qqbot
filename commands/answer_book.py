import random
from typing import List
from textwrap import dedent
from botpy.message import Message
from botpy import logging
from .base import command, Command, cooldown

_log = logging.get_logger()

with open("answer_book", "r") as f:
    answer_book = f.readlines()
answers = [line.split()[1].strip() for line in answer_book if line]
print(f"Loaded {len(answers)} answers from answer_book.")

@command("answer_book", "答案之书")
class AnswerBookCommand(Command):
    name = "answer_book"
    cn_name = "答案之书"
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Executing {self.name} command with args {args}")
        if not args:
            await self.send_reply(message, "你的问题呢？")
            return
        
        question = " ".join(args)
        answer = random.choice(answers)

        reply = (
            f"<@!{message.author.id}>\n"
            f"你的问题: {question}\n\n"
            f"答案之书的回答:\n{answer}"
            )
        await self.send_reply(message, reply)

answer_book_help_str = dedent("""\
    /答案之书 [问题] 向答案之书提问，获取回答。
    例子: /答案之书 我今天会中奖吗？

    说明：答案之书的回答仅供参考，请不要盲目相信。
    """
)

@command("answer_book_help", "答案之书帮助")
class AnswerBookHelpCommand(Command):
    name = "answer_book_help"
    cn_name = "答案之书帮助"
    async def execute(self, message: Message, args: List[str]):
        # _log.info(f"Executing {self.name} command with args {args}")
        await self.send_reply(message, answer_book_help_str)