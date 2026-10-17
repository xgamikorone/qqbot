# botpy HTTP 接口扩展

当前本地验证版本为 qq-botpy 1.2.1，运行环境 Python 3.11 及以上。
`botpy_ext.ExtendedBotAPI` 继承 SDK 的 `BotAPI`，增加 SDK 尚未提供的方法。
`MyClient` 在父类初始化后，用同一个 `self.http` 创建扩展 API，原有 API 调用保持可用。

## 查询全局自定义菜单

在已登录的 `MyClient` 异步方法内调用：

```python
result = await self.api.get_global_menu()
if result is None:
    # botpy 超时可能返回 None，不能将其理解为“尚未设置菜单”。
    return

version = result["version"]
menu = result.get("menu")  # 未配置菜单时允许为空
items = menu["items"] if menu else []
```

对应官方文档截图的 `GET /v2/menu`，限频为 30 QPM。方法不在启动或心跳中自动执行。
本次仅做离线验证，没有查询或修改线上菜单；正式使用还需用实际机器人账号确认接口权限与响应。
响应保留为原始字典，`botpy_ext.models` 只提供类型提示，不过滤新增字段。

后续新增 HTTP 方法时，继续在扩展类中声明 `Route` 并调用 `self._http.request`。
鉴权、token 生命周期、请求超时、沙箱域名和错误处理沿用 SDK；
不会额外实现限流或 token 刷新。SDK 的沙箱支持不代表新接口一定在沙箱可用。
不要把请求头、token 或应用密钥写入日志，也不要直接修改 site-packages。
