# DeepSeek 聊天联网

联网使用独立工具模块，聊天模型通过 tool_calls 按需调用，再结合返回资料回答。
没有工具调用时不请求搜索。原有人设、频道白名单、并发、每日请求限制、取消、
会话重置和 QQ 发送确认继续生效。仅最终问答入库，不保存工具原始网页或推理。

## 启用

在本地根目录 `.env` 设置以下变量，不要把真实 Key 提交到 Git 或发到聊天中：

```dotenv
CHAT_BASE_URL=https://api.deepseek.com
CHAT_MODEL=deepseek-flash
CHAT_API_KEY=填写你的DeepSeek官方APIKey
```

模型名称按你账号实际可用、支持工具调用的型号填写，本功能不会自动改你的
现有模型设置。模型处于非思考模式，避免未处理的推理消息参与工具协议。

在 `config/chat.yaml` 保持原有聊天功能开启及频道白名单，设置：

```yaml
web_enabled: true
web_max_searches: 2
web_max_fetches: 2
web_max_context_chars: 8000
web_timeout_seconds: 90
```

重启 bot 后照常使用聊天命令，例如询问近期新闻，或明确要求“请联网核实”。
模型自动决定是否调用工具；本版没有新增强制联网命令。默认 `web_enabled`
为 false，关闭时保留原来兼容其他厂商的纯文本请求方式。

## 行为与安全

- 仅接受 DeepSeek 官方聊天地址（根路径或 `/v1`）；代理地址不会自动获得
  搜索权限，不会误用智谱备用 Key。搜索与模型共用 `CHAT_API_KEY`。
- 搜索只提交模型产生的必要关键词，不直接提交会话历史；启用联网意味着
  这些关键词会发送到 DeepSeek 的搜索接口，避免输入不宜外发的资料。
- bot 始终只连接固定的 DeepSeek 官方端点。网页由 DeepSeek 远程读取，
  不会由 bot 服务器请求任意网页或向网页传送认证头。只允许读取本轮搜索
  返回的公开 HTTPS 链接；拒绝嵌入凭据、常见本地地址、私有 IP 和任意新链接。
  远程网页重定向和 DNS 安全由 DeepSeek Fetch 负责，本版没有本地爬虫。
- 每轮最多两次搜索、两次网页读取，至多五次模型调用，所有工具调用顺序执行。
  原有单次模型请求超时仍生效，整轮排队和联网总超时默认 90 秒。
- 单个工具响应最多 256 KiB；网页文本、搜索摘要和总工具上下文均有截断。
- 网页以不可信资料封装，提示模型不得执行其中指令。程序追加真实来源链接；
  网络失败会追加未核实提醒，不会把提供方的错误正文传给用户。
- 日志只包含工具名、返回字符数和成功失败，不包含搜索词、聊天历史或 Key。
- QQ 对消息长度和链接的限制仍生效；过长或未确认发送成功的回答不进入历史。

联网增加多轮模型 token 和搜索/读取服务用量，搜索费用不包含在模型 token
统计内，具体以官方账单为准。默认关闭；本次开发测试只用模拟响应，未调用
真实 DeepSeek 接口，没有验证你账号是否已开通 Search/Fetch 权限。

## 官方参考

- [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [Search](https://api-docs.deepseek.com/api/search/)
- [Fetch](https://api-docs.deepseek.com/api/fetch/)

禁用时将 `web_enabled` 改回 false 并重启即可，不需要迁移聊天数据库。
