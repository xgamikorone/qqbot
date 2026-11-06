# 项目目录

按功能聚合代码，先整理模块职责，再考虑进一步拆分大文件。

| 路径 | 职责 |
| --- | --- |
| `main.py` | 机器人启动、事件接收和模块装配 |
| `commands/` | 用户命令及命令管理 |
| `chat/` | 聊天会话、模型调用和联网工具 |
| `admin/server.py` | 本地管理面板 HTTP 入口与鉴权 |
| `admin/operations.py` | 面板可调用操作的白名单 |
| `admin/static/` | 面板页面、样式及浏览器脚本 |
| `scheduling/scheduler.py` | 任务注册、调度与执行上下文 |
| `scheduling/config.py` | 定时任务配置解析与校验 |
| `scheduling/jobs.py` | 任务构建和具体任务逻辑 |
| `scheduling/errors.py` | 手动执行任务的参数错误 |
| `botpy_ext/` | QQ SDK 扩展 |
| `database/` | 数据库结构、连接及仓储 |
| `config/` | 原有配置文件，位置不变 |
| `tests/` | Python 和前端离线测试 |
| `docs/` | 功能与运维说明 |

这轮只迁移管理面板和调度模块。消息模块、外部接口和资源目录暂不移动，
避免一次改动涉及过多路径。

## 启动与部署兼容性

- 仍从仓库根目录运行 `python main.py`，无需修改 qqbot 服务启动命令。
- `.env`、`config/scheduled_tasks.yaml`、数据库位置和管理面板 URL 不变。
- `SCHEDULED_TASKS_CONFIG` 的自定义路径语义不变。
- 面板从包内定位静态资源；默认定时配置从仓库根目录定位。
- 内部 Python 导入已更新，不保留根目录的同名转发文件。
  外部脚本若直接导入旧模块，需要改为上述新路径。
- 不需要数据库迁移；服务器更新代码后按常规重启服务。

回归命令：

```text
python -X utf8 -m unittest discover -s tests
node --test tests/admin_ui.test.cjs
```
