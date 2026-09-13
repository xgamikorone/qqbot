# Bot 管理控制台

控制台和 Bot 运行在同一台服务器上，默认仅监听服务器的
`127.0.0.1:8090`。请不要在防火墙中开放该端口，也不要将
`BOT_ADMIN_HOST` 改为 `0.0.0.0`。

## 服务器配置

在服务器仓库根目录的 `.env` 中设置一个随机、独立的管理令牌：

```env
BOT_ADMIN_TOKEN=replace-with-a-long-random-secret
BOT_ADMIN_HOST=127.0.0.1
BOT_ADMIN_PORT=8090
```

重启 Bot 后，日志会显示控制台已经在 `http://127.0.0.1:8090` 启动。
未配置令牌时，控制台不会启动。

## 从个人电脑访问

在个人电脑终端建立 SSH 隧道，并保持该命令运行：

```bash
ssh -N -L 8090:127.0.0.1:8090 ubuntu@your-server
```

如果服务器的 SSH 端口不同，追加 `-p <port>`；如使用私钥，追加
`-i <private-key-path>`。

然后在个人电脑的浏览器打开：

```text
http://127.0.0.1:8090
```

输入服务器 `.env` 中的 `BOT_ADMIN_TOKEN` 登录。浏览器请求会经由 SSH
加密隧道发送到服务器本机，不会公开 Bot 控制台端口。
