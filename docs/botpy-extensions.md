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

## 菜单与指令面板

以下接口按提供的官方文档截图实现，复用同一个 HTTP 客户端：

| 方法 | HTTP | 限频 |
| --- | --- | --- |
| `update_global_menu(menu)` | PUT /v2/menu | 5 QPM |
| `get_panels(scope, cursor=None, limit=None)` | GET /v2/panels | 30 QPM |
| `create_panel(scope, target_type, panel, user_openids=None, group_openids=None)` | POST /v2/panels | 10 QPM |
| `get_panel(panel_id)` | GET /v2/panels/{panel_id} | 30 QPM |
| `update_panel(panel_id, panel)` | PUT /v2/panels/{panel_id} | 10 QPM |
| `delete_panel(panel_id)` | DELETE /v2/panels/{panel_id} | 10 QPM |
| `update_panel_targets(panel_id, op, user_openids=None, group_openids=None)` | PUT /v2/panels/{panel_id}/target | 60 QPM |

`scope` 支持 c2c/group/channel/dm。只有 c2c/group 支持 specific，分别传入
user_openids/group_openids，每次 1–20 个；all 模式不传关联对象。
关联操作 `op` 为 add/del。列表接口不自动翻页，使用 next_cursor 继续查询，
is_end 为 true 时停止；limit 为 1–50，不传时使用服务端默认值 20。

menu/panel 参数直接传配置对象，不要额外套一层同名字段。
菜单最多 10 项，面板最多 20 项。修改是完整覆盖，不是局部补丁；
修改面板不改变关联对象。菜单只支持 C2C。未设置的响应、空字典和 SDK 超时
返回的 None 保持原样；错误不吞掉。不自动重试写请求或实现额外限流。
本地校验结构、数量和关联组合，字段内容与权限仍由 QQ API 校验。
这些新增接口尚未使用真实机器人进行在线验证。
