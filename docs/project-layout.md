# 项目目录

按功能聚合代码，先整理模块职责，再考虑进一步拆分大文件。

| 路径 | 职责 |
| --- | --- |
| `main.py` | 机器人启动、事件接收和模块装配 |
| `commands/` | 用户命令及命令管理 |
| `commands/manager.py` | 共用命令解析、场景分发、能力及权限检查 |
| `commands/text_query.py` | 文本查询共用频道/群聊入口和群文本分段 |
| `commands/image_query.py` | 图片查询共用入口、跨场景冷却及串行绘图 |
| `messaging/command_replies.py` | 每次事件独立的群聊/单聊回复序号 |
| `messaging/group_names.py` | 群昵称缓存与可选成员信息查询 |
| `chat/` | 聊天会话、模型调用和联网工具 |
| `admin/server.py` | 本地管理面板 HTTP 入口与鉴权 |
| `admin/operations.py` | 面板可调用操作的白名单 |
| `admin/static/` | 面板页面、样式及浏览器脚本 |
| `scheduling/scheduler.py` | 任务注册、调度与执行上下文 |
| `scheduling/config.py` | 定时任务配置解析与校验 |
| `scheduling/jobs.py` | 任务构建和具体任务逻辑 |
| `scheduling/errors.py` | 手动执行任务的参数错误 |
| `messaging/` | 消息审核、回复来源和消息 ID 工具 |
| `live_forwarding/server.py` | 直播事件接收、筛选、持久化和频道推送 |
| `integrations/live_data.py` | 原 `commands/api.py` 的外部数据请求 |
| `integrations/live_monitor.py` | Live Monitor 健康检查 |
| `integrations/baidu_translate.py` | 百度翻译请求与错误解释 |
| `botpy_ext/` | QQ SDK 扩展 |
| `botpy_ext/group_upload.py` | 本地群图片分片上传及合并 |
| `botpy_ext/group_events.py` | 连接专属群事件解析，保留昵称字段 |
| `botpy_ext/group_members.py` | 群成员昵称接口及无权限降级 |
| `database/` | 数据库结构、连接及仓储 |
| `config/` | 原有配置文件，位置不变 |
| `tests/` | Python 和前端离线测试 |
| `docs/` | 功能与运维说明 |

已整理管理面板、调度、消息、直播转发及主要外部接口模块。
群聊命令的支持范围、数据隔离和迁移规则见[群聊命令接入](group-commands.md)。
这轮不拆分接口函数、不改变业务规则，资源目录与维护脚本暂不移动。

## 启动与部署兼容性

- 仍从仓库根目录运行 `python main.py`，无需修改 qqbot 服务启动命令。
- `.env`、`config/scheduled_tasks.yaml`、数据库位置和管理面板 URL 不变。
- `SCHEDULED_TASKS_CONFIG` 的自定义路径语义不变。
- 面板从包内定位静态资源；默认定时配置从仓库根目录定位。
- 直播转发与回复来源的配置仍在 `config/` 下；
  `live_forwarding.db` 和 `reply_sources.db` 仍在仓库根目录，不创建新库替代旧库。
- 内部 Python 导入已更新，不保留根目录的同名转发文件。
  外部脚本若直接导入旧模块，需要改为上述新路径。
- `message_audits`、`reply_sources`、`qq_message_id` 分别改为
  `messaging.audits`、`messaging.reply_sources`、`messaging.message_id`。
- 原 `live_forwarding` 模块改为 `live_forwarding.server`；
  `live_monitor_client` 改为 `integrations.live_monitor`；
  `utils.baidu_translate` 改为 `integrations.baidu_translate`。
- 原频道模块整理不需要数据库迁移。群聊接入会增量创建独立表，
  不改写旧频道数据，见[群聊命令接入](group-commands.md)。

回归命令：

```text
python -X utf8 -m unittest discover -s tests
node --test tests/admin_ui.test.cjs
```
