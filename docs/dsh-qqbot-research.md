# dsh-qqbot 接入研究

研究日期：2026-10-27。固定源码提交：`d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9`（研究时 HEAD）。以下是源码评估，未安装插件、未调用模型、未改变 Bot 配置。

## 结论

可以借鉴其方法，但不能把它直接导入当前 Python Bot。它是 QQ 消息与 DeepSeek Harness（dsh）Agent 之间的 TypeScript/Cordis 插件，不是“开放 AI 接入”的新鉴权协议，也不是独立的模型 HTTP 接口。

插件自身初始化 QQBot，并使用 WebSocket 传输。不能据此推断现有 Python 机器人必须迁移传输方式或重新申请凭据。[网关源码](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/src/gateway/bootstrap.ts)

## 关键证据

| 项目 | 源码事实及对我们的影响 |
| --- | --- |
| 运行环境 | 包版本 0.5.3，需要 Node.js ≥20.3.0，并依赖 dsh Agent/Session/LLM 与 Cordis。不能作为 Python 包安装。见 [package.json](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/package.json)。 |
| 消息场景 | 入站消息只建模 c2c/group，并按场景构造回复目标。我们的主命令入口是频道 AT 消息，不能将 QQ 群聊等同于频道子频道。见 [inbound.ts](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/src/transport/inbound.ts)、本地 `main.py`。 |
| 模型接入 | 入站内容经过整理后交给 `record.agent.followup`，等待 `whenIdle`；模型推理与工具能力由 dsh 宿主提供，而非这个插件自行请求聊天模型。见上述入站源码。 |
| 会话隔离 | 会话键包含 appId、scope、peerId；C2C 按用户，群聊按 groupOpenid，因此默认是群共享会话，并非每个群成员单独一份。重启恢复依赖其宿主持久化。见 [session-manager.ts](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/src/session/session-manager.ts)。 |
| 流式输出 | `shouldStream` 要求配置开启、C2C 且存在 msgId。不能据此认为我们当前频道消息可以直接使用同一流式方案。见 [outbound.ts](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/src/transport/outbound.ts)。 |
| 并发与访问 | 中间件先做访问控制、消息整理、限流、命令路由，再按 peer 合并/排队处理。群历史在 @ 门控前记录，因此照搬前需决定是否允许未主动参与聊天的成员内容进入模型。见 [middleware-setup.ts](https://github.com/tencent-connect/dsh-qqbot/blob/d998f72fb4ab5492eaab3c5e1cc9de1d7901e8a9/src/gateway/middleware-setup.ts)。 |

## 当前项目差异

本地 `commands/chat.py` 仍是直接调用模型、按 user_id 保存 JSON 历史的旧实现；`commands/__init__.py` 尚未启用它。`main.py` 频道 AT 消息交由 CommandManager；群聊和私信入口没有同等的命令接入。引入新插件并不会自动迁移现有指令、DAO、定时任务或管理面板。

## 建议方案（设计推断，不是仓库现成功能）

首选保留 botpy 和现有命令体系，移植“消息适配 → 会话管理 → 模型/Agent → 输出适配”的分层思想。第一版先恢复显式 `/聊天` 文本命令，默认按频道及用户隔离会话，加异步并发控制、取消、预算、持久化和输出失败状态。不要直接照搬群共享记忆、后台收集聊天历史或 C2C 流式发送。

如果确实需要 dsh 的工具、审批、会话压缩等 Agent 能力，可评估本机隔离运行 dsh，由 Python 调用一个经过鉴权的窄接口；这个桥接层需要另外实现或先核实宿主已有接口，不能将 qqbot 插件本身当成现成 HTTP 服务。QQ 事件只保留一个明确入口，避免两个进程同时处理同一消息、重复回复。

若目标只是恢复人设聊天，直接改造 Python 聊天模块比同时维护 Node/dsh 运行环境更小、更可控。若目标是让机器人执行工具任务，再做独立 dsh 试点更合适。

## 未确认项

- QQ 账号的具体 AI 准入、审核和权限，以应用后台及官方场景文档为准；项目存在本身不是所有应用都已获准的证据。
- 频道场景的新发送能力、流式支持与 botpy 兼容性需要单独核验。
- 未评估实际模型成本、插件供应链、工具可访问路径、凭据隔离和主机权限；生产环境不应直接赋予 Agent 现有 Bot 主机的完整执行权限。
