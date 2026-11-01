# 实时 SC / 礼物转发（默认关闭）

## 职责和链路

live-monitor 推送所有正常解析并成功记录的 SC、礼物事件，不按主播、金额或目标频道筛选。
SEND_GIFT/V2 复用现有解析入口；现有未验证盲盒跳过策略保持不变，上舰事件不属于本版范围。
免费礼物也会推送，是否转发由 qqbot 各频道独立决定。

每个直播连接使用最多 32 个包批次的有界队列；四个专用工作线程按连接内顺序处理同步 DAO。
数据库慢时不会占用 asyncio 事件循环，高峰队列满时对该连接施加背压，不无限创建任务。
SC/gift 业务行与 outbox 使用同一 MySQL 事务写入，提交后线程安全地立即唤醒 HTTP 投递器。
HTTP 连接池常驻，最多四条并发请求；一秒补扫仅用于恢复/重试，不是正常链路的固定等待。
首次请求优先于失败重试，发送失败不删除待投递事件。数据库自身不可用时仍不能承诺不丢上游事件。

qqbot 独立监听 `127.0.0.1:8091`，不依赖 admin-panel 是否启用。接收验证后写入本机
`live_forwarding.db`（已 Git 忽略），一次事务完成事件去重和频道任务创建，然后返回 202。
接收确认只表示持久化成功，不表示 QQ 已收到消息。多个频道各有独立发送任务和限速。

## 配置（先启动 qqbot，再启用采集端）

两端生成同一个独立随机令牌，只存各自 `.env`，不要复用 QQ 密钥或管理面板令牌。

qqbot 根目录 `.env`：

```env
LIVE_FORWARD_TOKEN=replace-with-a-long-random-secret
LIVE_FORWARD_PORT=8091
```

live-monitor `.env`：

```env
QQBOT_FORWARD_ENABLED=true
QQBOT_EVENT_URL=http://127.0.0.1:8091/internal/live-events
QQBOT_EVENT_TOKEN=replace-with-the-same-long-random-secret
```

跨机器部署需使用受保护的 HTTPS 反向代理/隧道，不能直接公网暴露监听端口；采集端仅允许
本机 HTTP 或 HTTPS 目标，不跟随重定向。独立 Bearer 令牌认证，不改变原 Live Monitor API 契约。
启用采集端时需要建表权限，会创建 `qqbot_event_outbox`；应先备份并在测试数据库验收建表与事务。
代码测试模拟了 MySQL 游标，未对生产 MySQL 实施迁移或发送真实通知。

qqbot 的 `config/live_forwarding.yaml` 示例：

```yaml
enabled: true
dry_run: true
max_event_age_seconds: 300
send_interval_seconds: 1
channels:
  - channel_id: "723086974"
    enabled: true
    streamer_uids: ["123456", "654321"]
    super_chat:
      enabled: true
      min_amount_cents: 3000
    gift:
      enabled: true
      min_amount_cents: 10000
      paid_only: true
  - channel_id: "987654321"
    enabled: true
    all_streamers: true
    super_chat: {enabled: true, min_amount_cents: 10000}
    gift: {enabled: false}
```

频道/主播 ID 必须为带引号字符串；每个频道必须选择 all_streamers 或非空 UID 列表，不能二者兼选。
阈值为单个事件的总金额（人民币分），含等于阈值，不是单价、连击累计或用户累计。
现有 gold 总瓜子按 1000=1 元换算，不再乘数量；silver 人民币金额为零，保留原币值。
同一事件多频道独立判断，(event_id,channel_id) 唯一。首次接收时冻结匹配结果，修改规则不会自动补发。
配置通过重启生效。先保持 dry_run=true 检查 SQLite deliveries 中的 dry_run 任务，再关闭 dry_run。
dry_run 任务不会自动转为真实发送，避免一开开关就补发旧消息。

## 投递状态和边界

- 有稳定 SC ID/礼物标识时源端持久去重；无标识时生成一次 UUID 并持久化用于 HTTP 重试。
  无标识的上游重放无法严格识别，不能按用户/金额/时间硬去重以免吞掉真实重复赠送。
- 超过接收时间 300 秒的事件仍确认接收，但不创建通知；队列内超过此期限标为 expired。
  received_at 在采集入队前记录，积压不会刷新有效期。
- QQ 返回消息 ID：sent；304023：audit，不自动重发，也未实现审核回调跟踪。
- 明确 HTTP 429 限流：有上限的退避重试；其他 SDK 异常标 failed 等待人工判断。
- 超时/无法确认：unknown；进程重启时将 sending 改为 unknown，防止盲目重复主动消息。
- HTTP 投递成功但 ACK 丢失会重推，由 qqbot 的持久 event_id 去重，不再创建频道任务。
  对同一 ID 重推内容不更新，保留第一次收到的事件。
- 频道文本中的尖括号全角化，避免用户 SC 文本触发 QQ 提及；正文截取 2000 字符。
  当前没有礼物合并，也没有按频道严格保证全局事件顺序（网络并发可能重排），优先低延迟。
- 数据库表为通知审计记录，首版不自动清理。上线前应安排容量监控和保留策略；不要直接删表重新投递。
- QQ 主动推送权限、限速及审核仍需测试频道实测，不承诺最终展示延迟或严格“恰好一次”。

## 离线验收及后续

qqbot：`python -X utf8 -m unittest discover -s tests`。
live-monitor：在有完整采集依赖的环境运行相同命令。
覆盖金额换算、事务回滚、重复事件、慢数据库/有界背压、逐频道阈值、鉴权、审核、超时与重启状态。

本地完成后先仅启用一个测试频道，验证正常链路接收/发送耗时和真实数据库事务；
再测试 qqbot 停机、恢复和过期积压。需单独批准后才能操作线上服务。
禁用顺序：先关采集端转发，再关 qqbot 接收并重启。保留两端数据库，以便排查未完成记录。
