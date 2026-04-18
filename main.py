from typing import List
import botpy
from botpy import logging
from botpy.message import Message, GroupMessage, DirectMessage
from botpy.interaction import Interaction
import commands
from commands import CommandManager
from commands.categories import categories
from commands.guards import get_num_followers, get_num_guards, get_user_info_by_uids
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from zoneinfo import ZoneInfo




_log = logging.get_logger()
BEIJING_TZ = ZoneInfo("Asia/Shanghai")



async def generate_fans_and_guards_message():
    category = "wan"
    uids = categories[category]
    user_infos = await get_user_info_by_uids(uids)
    if user_infos is None:
        return "获取用户信息失败"
    fans_data = await get_num_followers(uids)
    if fans_data is None:
        return "获取粉丝信息失败"
    _log.info(f"fans_data: {fans_data}")

    res_str = f"粉丝数:\n"
    record_time = ""
    fans_strs = []
    for uid in uids:
        fans_info = fans_data.get(str(uid), {})
        num_followers = fans_info.get("num_followers", None)
        delta = fans_info.get("delta", None)
        delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
        fans_this_uid_str = (f"{user_infos[str(uid)]['name']}: {num_followers if num_followers is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}")
        fans_strs.append(fans_this_uid_str)
        record_time = fans_info.get("record_time", "")
    
    res_str += "\n".join(fans_strs)
    res_str += f"\n\n"

    filtered_uids = []
    room_ids = []
    for uid in uids:
        user_info = user_infos.get(str(uid), None)
        if user_info is None:
            continue
        filtered_uids.append(uid)
        room_ids.append(user_info["room_id"])
    
    num_guards = await get_num_guards(filtered_uids, room_ids)
    _log.info(f"num_guards: {num_guards}")

    if num_guards is None:
        res_str += "获取舰长信息失败"
        return res_str

    num_guards_strs = []
    record_time = ""
    for uid in filtered_uids:
        guard_info = num_guards.get(str(uid), {})
        num_guards_this_uid = guard_info.get("num_guards", None)
        delta = guard_info.get("delta", None)
        name = user_infos[str(uid)]['name']
        record_time = guard_info.get("record_time", "")
        delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
        num_guards_str = (f"{name}: {num_guards_this_uid if num_guards_this_uid is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}")
        num_guards_strs.append(num_guards_str)
    
    res_str += "\n".join(num_guards_strs)
    res_str += f"\n\n对比时间: {record_time}"

    return res_str






class MyClient(botpy.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd_manager = CommandManager(self)
        self.scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)
        print(list(self.cmd_manager.commands.keys()))
        print(commands._command_name_to_formal_name)

    async def on_ready(self):
        if not self.scheduler.running:
            self.scheduler.start()
            _log.info("调度器已启动")
        await self.add_scheduled_message(
            channel_id="8338248", 
            content="测试定时发送！", 
            hour=23, 
            minute=55,
            message_generator=generate_fans_and_guards_message)

    async def on_at_message_create(self, message: Message):
        print(message.content)
        msgs = message.content.split()
        
        if len(msgs) < 2:
            await self.api.post_message(
                channel_id=message.channel_id,
                content="你在说什么？",
                msg_id=message.id
            )
            return
        
        if not await self.cmd_manager.execute(message, msgs):
            await self.api.post_message(
                channel_id=message.channel_id,
                content="未知命令",
                msg_id=message.id
            )

            

    async def on_group_at_message_create(self, message: GroupMessage):
        print(message.content)
        msgs = message.content.split()
        
        
        if msgs[0].lstrip("/") == "hello":
            await message.reply(content="hi")
            return
        

    async def on_direct_message_create(self, message: DirectMessage):
        print(message.content)
        msgs = message.content.split()
        
        # if len(msgs) < 2:
        #     await self.api.post_message(
        #         channel_id=message.channel_id,
        #         content="你在说什么？",
        #         msg_id=message.id
        #     )
        #     return
        
        cmd_name = msgs[0].lstrip("/")
        if cmd_name == "hello":
            await self.api.post_dms(
                guild_id=message.guild_id,
                content="hi"
            )

    async def on_forum_thread_create(self, thread):
        print(thread)

    
    async def on_interaction_create(self, interaction: Interaction):
        pass

    async def add_scheduled_message(self, channel_id: str, content, hour: int, minute: int, message_generator=None):
        """
        添加定时发送消息任务
        :param channel_id: 频道ID
        :param content: 要发送的消息内容（字符串）
        :param hour: 小时 (0-23)
        :param minute: 分钟 (0-59)
        :param message_generator: 生成消息的异步函数，会覆盖 content 参数。函数应该返回字符串
        示例:
            # 方式1：直接传入字符串
            await client.add_scheduled_message(channel_id="123", content="早上好", hour=10, minute=0)
            
            # 方式2：传入函数，动态生成消息
            async def get_message():
                data = await some_api_call()
                return f"现在是{data['time']}，请开播"
            
            await client.add_scheduled_message(channel_id="123", hour=10, minute=0, message_generator=get_message)
        """
        async def send_message():
            try:
                # 如果提供了消息生成器，使用它；否则使用 content
                if message_generator:
                    msg_content = await message_generator() if asyncio.iscoroutinefunction(message_generator) else message_generator()
                else:
                    msg_content = content
                
                await self.api.post_message(channel_id=channel_id, content=msg_content)
                _log.info(f"已发送定时消息到 {channel_id}: {msg_content}")
            except Exception as e:
                _log.error(f"发送定时消息失败: {e}")
        
        trigger = CronTrigger(hour=hour, minute=minute, timezone=BEIJING_TZ)
        job_id = f"scheduled_message_{channel_id}_{hour}_{minute}"
        self.scheduler.add_job(send_message, trigger=trigger, id=job_id, replace_existing=True)
        _log.info(f"已添加定时任务: {job_id}")

    async def remove_scheduled_message(self, channel_id: str, hour: int, minute: int):
        """删除定时发送消息任务"""
        job_id = f"scheduled_message_{channel_id}_{hour}_{minute}"
        try:
            self.scheduler.remove_job(job_id)
            _log.info(f"已移除定时任务: {job_id}")
        except Exception as e:
            _log.error(f"移除定时任务失败: {e}")
        


if __name__ == '__main__':
    
    intents = botpy.Intents().default()
    client = MyClient(intents=intents)

    client.run(appid="102824382", secret="Ce6Z2W0V0W3a8gFoOyZAmO1eIwbGwcJ0")


