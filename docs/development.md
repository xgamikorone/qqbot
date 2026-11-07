# 本地开发与换电脑接续

从仓库根目录执行以下命令。目录职责与迁移后的导入路径见
[项目结构](project-layout.md)，工作规则见根目录的 [AGENTS.md](../AGENTS.md)。

## 环境准备

安装 Git、Python 3.11 和支持 `node --test` 的 Node.js。
`requirements.txt` 记录运行时依赖；YAPF、mypy 是单独安装的开发工具。
不要复制旧电脑的虚拟环境，也不要依赖某台电脑的 Conda 环境路径。

克隆仓库或在已有仓库中确认分支、远端和工作区状态后，再同步代码。
已有未提交修改时先妥善保存，不使用强制重置覆盖它们。

Windows PowerShell：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install yapf mypy
```

Linux/macOS：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install yapf mypy
```

可以激活虚拟环境后使用下文的 `python`，或直接使用上述虚拟环境中的
Python 路径。开发工具目前未单独锁定版本；遇到工具版本差异时应记录版本，
不要把新出现的历史代码告警直接当成本轮引入的问题。

## 凭据与本地数据

- 根据 `.env.example` 的变量名配置本地 `.env`，不要提交真实值。
- 离线测试使用替身和临时数据，不需要生产凭据或生产数据库。
- 需要联网联调时再通过安全方式配置必要的测试凭据；不要贴进聊天记录。
- `user.db`、`live_forwarding.db` 和 `reply_sources.db` 不通过 Git 同步。
  如果确需迁移已有数据，先明确数据范围并备份，作为独立操作处理。
- 配置仍在 `config/` 下。个人未提交配置需要单独核对，不要覆盖服务器配置。
- 不要在新电脑直接运行使用生产凭据的 bot，以免和服务器重复连接或推送。
- `.env`、虚拟环境、SSH 私钥和个人 Codex 登录状态不应作为项目文件同步。

## 验证

在虚拟环境中、从仓库根目录运行：

```text
python -X utf8 -m unittest discover -s tests
node --test tests/admin_ui.test.cjs
git diff --check
```

`-X utf8` 用于避免 Windows 默认编码影响中文测试数据。
前端测试不需要启动管理面板，不需要安装 npm 依赖。

修改 Python 时对具体文件执行格式和类型检查，例如：

```text
python -m yapf --style=.style.yapf --diff messaging/audits.py
python -m mypy --follow-imports=silent --ignore-missing-imports --strict messaging/audits.py
```

确认格式差异后，可用 YAPF 的 `-i` 替换 `--diff` 写回文件；只格式化本轮
修改的范围，不要为了迁移目录重新格式化整个遗留模块。
以上类型检查命令是单模块示例，不代表整个仓库已经通过严格类型检查。

## 在另一台电脑继续使用 Codex

打开克隆后的仓库，先让 Codex 阅读 `AGENTS.md` 和本文件，再确认当前分支、
最近提交与未完成工作。不要求沿用本次聊天才能理解项目。

个人技能、插件、连接和权限按新电脑实际环境配置，不要整目录复制旧电脑
的认证文件。项目规则应以仓库中的文档为准；缺少个人技能时应明确说明，
不要假设旧电脑的用户路径仍然存在。

交接时记录：

- 已完成的改动和对应提交。
- 测试、格式与类型检查结果，以及未验证的部分。
- 未提交的本地改动、后续事项及必要的非敏感配置说明。
- 是否已经推送或部署；提交不等于推送，推送也不等于部署。

## 启动与部署

机器人入口仍是 `python main.py`；`app.py` 是独立下载服务，不是新的机器人
入口。仅在获准的隔离联调或部署场景中启动服务。
服务器操作、真实发消息和付费接口调用应另行确认，不作为离线验证的一部分。
