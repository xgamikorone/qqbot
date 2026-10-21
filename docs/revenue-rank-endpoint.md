# 营收排行域名迁移

`commands.api.get_revenue_rank` 默认直接请求 `https://dc.yioio.top`：
当月走 `/gift`，历史月份走 `/gift/by_month`，保留 month/filter 参数。
不依赖旧域名的 301 跳转，不自动跟随重定向，防止旧入口将 HTTPS 降级为 HTTP。

可在仓库根目录 `.env` 设置：

```env
REVENUE_RANK_BASE_URL=https://dc.yioio.top
```

留空或未设置使用新默认值。值应为 HTTPS 基础域名，可带尾斜杠，
不要包含 /gift、查询参数、账号密码。它与 Live Monitor 的 API_URL、
LIVE_MONITOR_BASE_URL 无关。无需修改数据库或删除历史缓存。

部署：推送后在服务器拉取代码，检查没有旧的域名覆盖配置，重启 qqbot。
执行一次当月和历史月份的营收排行，确认图表正常、日志来源为 remote。
历史月份的缓存命中不代表远程接口验证成功。

配置变更后需重启 Bot。保留配置覆盖入口用于回滚到已验证兼容的 HTTPS 服务，
但旧域名当前跳转到 HTTP，不能仅改回旧域名就认为恢复可用。
现有历史月份失败回读缓存策略不变，当月不使用历史缓存兜底。

## 验证记录

2026-10-21 在本地通过 curl 和修改后的 Bot aiohttp 函数验证新域名：
VR 分类 202610 当月返回 57 条，202609 历史月份返回 60 条；
顶层 anchors/filter/refresh_time 及图表所需的全部主播字段均存在。
这不代表其他分类、所有历史月份或服务器网络都已验证，也未发送实际频道消息。
