"""Explicit, browser-safe allowlist for the personal BotAPI control panel."""

from dataclasses import dataclass
from typing import Literal


FieldKind = Literal["text", "textarea", "number", "boolean", "json", "permission", "file"]


@dataclass(frozen=True)
class OperationField:
    name: str
    label: str
    kind: FieldKind = "text"
    required: bool = True
    placeholder: str = ""
    expand: bool = False


@dataclass(frozen=True)
class AdminOperation:
    id: str
    category: str
    title: str
    description: str
    api_method: str
    fields: tuple[OperationField, ...]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "fields": [field.__dict__ for field in self.fields],
        }


def field(name: str, label: str, **kwargs) -> OperationField:
    return OperationField(name=name, label=label, **kwargs)


GUILD_ID = field("guild_id", "频道 ID")
CHANNEL_ID = field("channel_id", "子频道 ID")
USER_ID = field("user_id", "用户 ID")
ROLE_ID = field("role_id", "身份组 ID")
MESSAGE_ID = field("message_id", "消息 ID")


OPERATIONS: tuple[AdminOperation, ...] = (
    AdminOperation("me", "基础查询", "机器人资料", "获取当前机器人信息。", "me", ()),
    AdminOperation("me_guilds", "基础查询", "已加入频道", "分页查看机器人已加入的频道。", "me_guilds", (
        field("guild_id", "起始频道 ID", required=False), field("limit", "数量", kind="number", required=False, placeholder="100"), field("desc", "倒序", kind="boolean", required=False),
    )),
    AdminOperation("get_ws_url", "基础查询", "网关地址", "获取 QQ Gateway 地址。", "get_ws_url", ()),
    AdminOperation("get_guild", "频道与成员", "频道信息", "获取指定频道信息。", "get_guild", (GUILD_ID,)),
    AdminOperation("get_channels", "频道与成员", "子频道列表", "获取频道下的子频道。", "get_channels", (GUILD_ID,)),
    AdminOperation("get_channel", "频道与成员", "子频道信息", "获取一个子频道的信息。", "get_channel", (CHANNEL_ID,)),
    AdminOperation("get_guild_members", "频道与成员", "频道成员", "按页获取频道成员。", "get_guild_members", (
        GUILD_ID, field("after", "起始用户 ID", required=False, placeholder="0"), field("limit", "数量", kind="number", required=False, placeholder="100"),
    )),
    AdminOperation("get_guild_member", "频道与成员", "指定成员", "获取频道内指定成员。", "get_guild_member", (GUILD_ID, USER_ID)),
    AdminOperation("get_voice_members", "频道与成员", "语音频道成员", "获取语音子频道中的成员。", "get_voice_members", (CHANNEL_ID,)),
    AdminOperation("mute_member", "禁言", "禁言指定成员", "按秒禁言指定成员；填写 0 可解除禁言。", "mute_member", (
        GUILD_ID, USER_ID, field("mute_seconds", "禁言时长（秒）", placeholder="3600"),
    )),
    AdminOperation("mute_multi_member", "禁言", "禁言多个成员", "按秒禁言多个成员；填写 0 可解除禁言。", "mute_multi_member", (
        GUILD_ID, field("user_ids", "用户 ID 列表 JSON", kind="json", placeholder='["用户 ID 1", "用户 ID 2"]', expand=False), field("mute_seconds", "禁言时长（秒）", placeholder="3600"),
    )),
    AdminOperation("mute_all", "禁言", "全员禁言", "按秒禁言频道内所有非管理员成员；填写 0 可解除禁言。", "mute_all", (
        GUILD_ID, field("mute_seconds", "禁言时长（秒）", placeholder="3600"),
    )),
    AdminOperation("create_channel", "频道与成员", "创建子频道", "创建新的子频道。", "create_channel", (
        GUILD_ID, field("name", "名称"), field("type", "类型", kind="number"), field("sub_type", "子类型", kind="number"), field("options", "可选参数 JSON", kind="json", required=False, placeholder='{"position": 1}', expand=True),
    )),
    AdminOperation("update_channel", "频道与成员", "更新子频道", "更新子频道的名称或权限配置。", "update_channel", (
        CHANNEL_ID, field("fields", "更新字段 JSON", kind="json", placeholder='{"name": "新名称"}', expand=True),
    )),
    AdminOperation("get_guild_roles", "身份组与权限", "身份组列表", "获取频道身份组。", "get_guild_roles", (GUILD_ID,)),
    AdminOperation("create_guild_role", "身份组与权限", "创建身份组", "创建频道身份组。", "create_guild_role", (
        GUILD_ID, field("fields", "身份组字段 JSON", kind="json", placeholder='{"name": "管理员", "color": 16711680}', expand=True),
    )),
    AdminOperation("update_guild_role", "身份组与权限", "更新身份组", "修改频道身份组。", "update_guild_role", (
        GUILD_ID, ROLE_ID, field("fields", "身份组字段 JSON", kind="json", placeholder='{"name": "新名称"}', expand=True),
    )),
    AdminOperation("create_guild_role_member", "身份组与权限", "添加身份组成员", "将成员加入身份组。", "create_guild_role_member", (
        GUILD_ID, ROLE_ID, USER_ID, field("channel_id", "子频道 ID", required=False),
    )),
    AdminOperation("get_guild_role_members", "身份组与权限", "身份组成员", "分页获取身份组成员。", "get_guild_role_members", (
        GUILD_ID, ROLE_ID, field("start_index", "起始索引", required=False, placeholder="0"), field("limit", "数量", kind="number", required=False, placeholder="100"),
    )),
    AdminOperation("get_channel_user_permissions", "身份组与权限", "用户子频道权限", "获取用户在子频道内的权限。", "get_channel_user_permissions", (CHANNEL_ID, USER_ID)),
    AdminOperation("get_channel_role_permissions", "身份组与权限", "身份组子频道权限", "获取身份组在子频道内的权限。", "get_channel_role_permissions", (CHANNEL_ID, ROLE_ID)),
    AdminOperation("update_channel_user_permissions", "身份组与权限", "更新用户权限", "使用权限 JSON 增加或移除用户权限。", "update_channel_user_permissions", (
        CHANNEL_ID, USER_ID, field("add", "增加权限 JSON", kind="permission", required=False), field("remove", "移除权限 JSON", kind="permission", required=False),
    )),
    AdminOperation("update_channel_role_permissions", "身份组与权限", "更新身份组权限", "使用权限 JSON 增加或移除身份组权限。", "update_channel_role_permissions", (
        CHANNEL_ID, ROLE_ID, field("add", "增加权限 JSON", kind="permission", required=False), field("remove", "移除权限 JSON", kind="permission", required=False),
    )),
    AdminOperation("get_permissions", "身份组与权限", "机器人权限", "获取机器人在频道内可用权限。", "get_permissions", (GUILD_ID,)),
    AdminOperation("post_permission_demand", "身份组与权限", "请求接口授权", "在频道创建 API 权限授权链接。", "post_permission_demand", (
        GUILD_ID, CHANNEL_ID, field("api_identify", "API 标识"), field("desc", "说明"),
    )),
    AdminOperation("get_message", "消息", "获取消息", "获取指定子频道中的一条消息。", "get_message", (CHANNEL_ID, MESSAGE_ID)),
    AdminOperation("post_message", "消息", "发送频道消息", "发送文本、图片 URL 或结构化消息。", "post_message", (
        CHANNEL_ID, field("content", "文本内容", kind="textarea", required=False), field("image", "图片 URL", required=False), field("file_image", "本地图片", kind="file", required=False), field("embed", "Embed JSON", kind="json", required=False), field("ark", "Ark JSON", kind="json", required=False), field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False),
    )),
    AdminOperation("post_keyboard_message", "消息", "发送键盘消息", "发送 Markdown 和内联键盘消息。", "post_keyboard_message", (
        CHANNEL_ID, field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False),
    )),
    AdminOperation("patch_guild_message", "消息", "更新 Markdown 消息", "更新既有频道 Markdown 消息。", "patch_guild_message", (
        CHANNEL_ID, field("patch_msg_id", "待更新消息 ID"), field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False), field("msg_id", "回复消息 ID", required=False), field("event_id", "事件 ID", required=False),
    )),
    AdminOperation("on_interaction_result", "消息", "交互回调", "提交消息按钮交互结果。", "on_interaction_result", (field("interaction_id", "交互 ID"), field("code", "结果代码", kind="number"))),
    AdminOperation("create_dms", "消息", "创建私信会话", "创建与频道成员的私信会话。", "create_dms", (GUILD_ID, USER_ID)),
    AdminOperation("post_dms", "消息", "发送私信", "向已经创建的私信会话发送消息。", "post_dms", (
        field("guild_id", "私信频道 ID"), field("content", "文本内容", kind="textarea", required=False), field("image", "图片 URL", required=False), field("file_image", "本地图片", kind="file", required=False), field("embed", "Embed JSON", kind="json", required=False), field("ark", "Ark JSON", kind="json", required=False), field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False),
    )),
    AdminOperation("post_group_message", "群与 C2C", "发送群消息", "向群聊发送消息。", "post_group_message", (
        field("group_openid", "群 OpenID"), field("msg_type", "消息类型", kind="number", required=False, placeholder="0"), field("content", "文本内容", kind="textarea", required=False), field("embed", "Embed JSON", kind="json", required=False), field("ark", "Ark JSON", kind="json", required=False), field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False),
    )),
    AdminOperation("post_c2c_message", "群与 C2C", "发送 C2C 消息", "向用户发送 C2C 消息。", "post_c2c_message", (
        field("openid", "用户 OpenID"), field("msg_type", "消息类型", kind="number", required=False, placeholder="0"), field("content", "文本内容", kind="textarea", required=False), field("embed", "Embed JSON", kind="json", required=False), field("ark", "Ark JSON", kind="json", required=False), field("markdown", "Markdown JSON", kind="json", required=False), field("keyboard", "键盘 JSON", kind="json", required=False),
    )),
    AdminOperation("post_group_file", "群与 C2C", "发送群媒体", "上传或发送群聊媒体 URL。", "post_group_file", (
        field("group_openid", "群 OpenID"), field("file_type", "媒体类型", kind="number"), field("url", "资源 URL"), field("srv_send_msg", "直接发送", kind="boolean", required=False),
    )),
    AdminOperation("post_c2c_file", "群与 C2C", "发送 C2C 媒体", "上传或发送 C2C 媒体 URL。", "post_c2c_file", (
        field("openid", "用户 OpenID"), field("file_type", "媒体类型", kind="number"), field("url", "资源 URL"), field("srv_send_msg", "直接发送", kind="boolean", required=False),
    )),
    AdminOperation("create_announce", "内容运营", "创建消息公告", "将消息发布为频道公告。", "create_announce", (GUILD_ID, CHANNEL_ID, MESSAGE_ID)),
    AdminOperation("create_recommend_announce", "内容运营", "创建推荐频道公告", "创建推荐子频道公告。", "create_recommend_announce", (
        GUILD_ID, field("announces_type", "公告类型", kind="number"), field("recommend_channels", "推荐频道 JSON", kind="json"),
    )),
    AdminOperation("get_schedules", "内容运营", "日程列表", "获取日程子频道的日程。", "get_schedules", (CHANNEL_ID, field("since", "起始时间戳", required=False))),
    AdminOperation("get_schedule", "内容运营", "日程详情", "获取单个日程。", "get_schedule", (CHANNEL_ID, field("schedule_id", "日程 ID"))),
    AdminOperation("create_schedule", "内容运营", "创建日程", "在日程子频道创建日程。", "create_schedule", (
        CHANNEL_ID, field("name", "名称"), field("start_timestamp", "开始时间戳"), field("end_timestamp", "结束时间戳"), field("jump_channel_id", "跳转子频道 ID", required=False), field("remind_type", "提醒类型", kind="number", required=False),
    )),
    AdminOperation("update_schedule", "内容运营", "更新日程", "更新既有日程。", "update_schedule", (
        CHANNEL_ID, field("schedule_id", "日程 ID"), field("name", "名称"), field("start_timestamp", "开始时间戳"), field("end_timestamp", "结束时间戳"), field("jump_channel_id", "跳转子频道 ID", required=False), field("remind_type", "提醒类型", kind="number", required=False),
    )),
    AdminOperation("put_reaction", "内容运营", "添加表情", "为消息添加表情表态。", "put_reaction", (CHANNEL_ID, MESSAGE_ID, field("emoji_type", "表情类型", kind="number"), field("emoji_id", "表情 ID"))),
    AdminOperation("get_reaction_users", "内容运营", "表情用户", "获取对表情做出反应的用户。", "get_reaction_users", (
        CHANNEL_ID, MESSAGE_ID, field("emoji_type", "表情类型", kind="number"), field("emoji_id", "表情 ID"), field("cookie", "分页 Cookie", required=False), field("limit", "数量", kind="number", required=False, placeholder="20"),
    )),
    AdminOperation("put_pin", "内容运营", "设为精华", "将消息设为精华。", "put_pin", (CHANNEL_ID, MESSAGE_ID)),
    AdminOperation("get_pins", "内容运营", "精华消息", "获取子频道精华消息。", "get_pins", (CHANNEL_ID,)),
    AdminOperation("get_threads", "内容运营", "帖子列表", "获取子频道帖子。", "get_threads", (CHANNEL_ID,)),
    AdminOperation("get_thread_detail", "内容运营", "帖子详情", "获取帖子详情。", "get_thread_detail", (CHANNEL_ID, field("thread_id", "帖子 ID"))),
    AdminOperation("post_thread", "内容运营", "发布帖子", "在帖子子频道发布内容。", "post_thread", (
        CHANNEL_ID, field("title", "标题"), field("content", "内容", kind="textarea"), field("format", "格式", kind="number"),
    )),
    AdminOperation("update_audio", "音频", "更新音频状态", "使用 AudioControl JSON 控制音频。", "update_audio", (CHANNEL_ID, field("audio_control", "AudioControl JSON", kind="json"))),
    AdminOperation("on_microphone", "音频", "开启麦克风", "开启机器人在语音子频道的麦克风。", "on_microphone", (CHANNEL_ID,)),
    AdminOperation("off_microphone", "音频", "关闭麦克风", "关闭机器人在语音子频道的麦克风。", "off_microphone", (CHANNEL_ID,)),
)


_OPERATIONS_BY_ID = {operation.id: operation for operation in OPERATIONS}


def list_operations() -> tuple[AdminOperation, ...]:
    return OPERATIONS


def get_operation(operation_id: str) -> AdminOperation | None:
    return _OPERATIONS_BY_ID.get(operation_id)
