# 定时消息审核记录

两个定时任务（每日维护汇报、粉丝舰长测试消息）以及它们的手动执行
都自动记录在主数据库 `user.db` 中。启动时自动创建表和视图，无需手动迁移。
发送前先记录任务和频道，发送响应再补充审核 ID、消息 ID 和结果。
日志分类为 `botpy.message_audit`；通用发送日志也会打印 `audit_id`。
不保存消息正文、凭据或原始错误响应。

查询最近的定时发送及其最终审核状态：

```sql
SELECT task_id, channel_id, status, audit_id, message_id, code,
       datetime(created_at, 'unixepoch', '+8 hours') AS submitted_at
FROM scheduled_message_delivery
ORDER BY created_at DESC LIMIT 50;
```

状态含义：

- `sending`：已开始提交；进程崩溃可能使其保持此状态，不能据此认定未发送。
- `sent`：发送接口直接返回消息 ID。
- `pending_audit`：304023/304024 或返回审核 ID；不代表已经送达。
- `audit_passed` / `audit_rejected`：收到 QQ 最终通过／拒绝事件。
- `rejected`：接口直接返回其他非零错误码。
- `unknown`：无有效响应、网络异常或取消，无法确定发送结果。

`scheduled_message_sends` 保存 HTTP 提交结果；`message_audit_events` 按
`audit_id` 保存审核事件；`scheduled_message_delivery` 视图优先展示最终事件。
先到事件、重复事件和重启后到达的事件均可关联，不会被迟到的 HTTP 响应覆盖。
非定时消息的审核事件也保存元数据，未匹配到定时发送的事件可直接查询事件表。

程序显式启用 `message_audit` intent，通过 botpy 审核回调接收结果。
当前安装的 botpy 只保留审核 ID、消息 ID、频道 ID 和子频道 ID；丢弃
`audit_time`、`create_time` 和 `seq_in_channel`，因此这些列可能为空。
`received_at` 是本地收到回调的 Unix 时间，不是平台审核时间。

没有收到回调的记录会保持待审核；不会自动推断成功或重新发送。
重启前的事件是否补发取决于 QQ 网关，不能保证补齐。
调度器任务完成仅表示任务逻辑和提交结束，不代表审核通过。
