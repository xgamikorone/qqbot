import json
import os
from typing import List
from textwrap import dedent

from dotenv import load_dotenv
from openai import OpenAI
# from zai import ZhipuAiClient
from botpy.message import Message
from botpy import logging
from .base import command, Command

load_dotenv()

_log = logging.get_logger(__name__)


class PersistentSessionManager:
    def __init__(self, file_path="sessions.json", max_history=100, system_prompt=None):
        self.file_path = file_path
        self.max_history = max_history
        self.system_prompt = system_prompt or "你是一个QQ频道的聊天机器人。"
        self.user_histories = self.load_sessions()

    def load_sessions(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_sessions(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.user_histories, f, ensure_ascii=False, indent=2)

    def add_user_message(self, user_id: int, content: str):
        history = self.user_histories.get(str(user_id), [])
        history.append({"role": "user", "content": content})
        self.user_histories[str(user_id)] = history[-self.max_history :]
        self.save_sessions()
        _log.info(f"[User] {user_id}: {content}")

    def add_bot_message(self, user_id: int, content: str):
        history = self.user_histories.get(str(user_id), [])
        history.append({"role": "assistant", "content": content})
        self.user_histories[str(user_id)] = history[-self.max_history :]
        self.save_sessions()
        _log.info(f"[Assistant] {user_id}: {content}")

    def get_history(self, user_id: int):
        """返回带 system prompt 的完整消息列表"""
        history = self.user_histories.get(str(user_id), [])
        return [{"role": "system", "content": self.system_prompt}] + history

    def reset_session(self, user_id: int):
        self.user_histories.pop(str(user_id), None)
        self.save_sessions()
        _log.info(f"[Reset] {user_id}")


system_prompt = """你是QQ频道“四禧丸子”的聊天机器人。四禧丸子是一个虚拟偶像组合，由恬豆、梨安、沐霂、又一四位成员组成，经营百年老字号中式点心店“禧运楼”。  

角色设定：
- 恬豆：禧运楼老板娘兼首席糕点师，可爱、元气、从不着急，贤惠能干。  
- 梨安：看板娘，外表性感内心细腻，有目标和信念，生活中有些迷糊。  
- 沐霂：掌柜兼队长，沉着冷静，有主见，有时显得傲娇。  
- 又一：舞台总管，古灵精怪爱吐槽，但行为经常被吐槽，沉浸在自己的世界。  

你的人设是一位了解“四禧丸子”的小女孩。
如果用户提及相关成员，请严格遵循以上设定回答。
如果没有提及，则正常回答用户的问题。  

与用户对话时：
- 尽量简洁、有趣、可爱  
- 避免冗长、正式或机械化，除非用户提及，否则尽量将篇幅缩短。
- 隐藏自己的 DeepSeek 身份
"""

# client = OpenAI(
#     api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
# )
client = OpenAI(api_key=os.environ.get("ZHIPU_API_KEY"),
                base_url="https://open.bigmodel.cn/api/paas/v4/")

# response = client.chat.completions.create(
#     model="deepseek-chat",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant"},
#         {"role": "user", "content": "Hello"},
#     ],
#     stream=False,
#     temperature=1.3,
#     max_tokens=1024,
# )

# print(response.choices[0].message.content)

session_manager = PersistentSessionManager(max_history=100, system_prompt=system_prompt)


@command("聊天", "chat")
class ChatCommand(Command):
    name = "chat"
    async def execute(self, message: Message, args: List[str]):
        user_id = message.author.id
        user_name = message.author.username
        user_input = " ".join(args).strip()

        if not user_input:
            await self.send_reply(message, "请输入你想说的话。")
            return

        # 支持 /reset 命令清空会话
        if user_input.lower() == "/reset":
            session_manager.reset_session(user_id)
            await self.send_reply(message, f"{user_name} 的聊天会话已重置。")
            return

        # 添加用户消息
        session_manager.add_user_message(user_id, user_input)

        # 调用 DeepSeek/OpenAI API
        try:
            history = session_manager.get_history(user_id)
            response = client.chat.completions.create(
                model="glm-4.5-flash", messages=history
            )
            reply_content = response.choices[0].message.content
            if reply_content is None:
                await self.send_reply(message, "聊天失败，请稍后重试。")
                return

            # 保存机器人回复
            session_manager.add_bot_message(user_id, reply_content)
            _log.info(f"[Chat] {user_name}: {user_input} => {reply_content}")

            await self.send_reply(message, reply_content)
        except Exception as e:
            _log.error(f"调用API 出错: {e}")
            await self.send_reply(message, "聊天失败，请稍后重试。")

chat_help_str = dedent("""\
    聊天帮助：
    
    聊天 <内容>
        与机器人进行聊天
        示例：聊天 你好，你是谁？
    
    特殊命令：
        /reset - 重置你的聊天会话，清空所有聊天历史
        示例：聊天 /reset
    
    聊天帮助
        显示此帮助信息""")

@command("聊天帮助", "chat_help")
class ChatHelpCommand(Command):
    """聊天命令的帮助"""
    name = "chat_help"
    async def execute(self, message: Message, args: List[str]):
        
        await self.send_reply(message, chat_help_str)
