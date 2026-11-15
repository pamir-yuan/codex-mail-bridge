# Codex Mail Bridge

一个实验性的 macOS 本地邮件通知与回复桥：

**Codex 发通知 → 手机邮箱收到 → 直接回复邮件 → 新正文自动进入原聊天。**

项目采用 MIT 许可证，提供 CLI、可选 MCP 入口和 macOS 后台服务。
桌面投递依赖私有 IPC，应用升级后可能需要适配；这不是 OpenAI 官方项目。

## 安装与配置

在项目目录中使用 Python 3.11 或更高版本：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ".[mcp]"
codex-mail-bridge init
codex-mail-bridge doctor --network
```

引导会询问邮箱地址、SMTP／IMAP 主机与端口，并隐藏输入授权码。
不会发送邮件或安装后台服务。需要先在邮箱服务商处开启 SMTP 与 IMAP。
当前版本支持**一个邮箱给自己发通知**，SMTP 与 IMAP 使用同一账号和授权码；
原通知必须能进入所监视的收件箱，以识别服务商改写后的邮件编号。

配置保存在 `~/.config/codex-mail-bridge/config.json`；授权码单独保存在
同目录的 `credentials.json`，权限为 0600，目录权限为 0700。
它们都在源代码目录之外。请勿把授权码写进项目、命令参数或聊天。

也可以先运行 `init --example` 生成占位配置，手动编辑后通过
`codex-mail-bridge set-password` 在本机终端保存授权码。

## 验证闭环

先在另一个终端运行：

```sh
codex-mail-bridge listen
```

然后让目标 Codex 聊天中的 shell 工具执行：

```sh
codex-mail-bridge send --title '需要你的意见' '请审核当前结果。'
```

CLI 自动读取该 shell 的 `CODEX_THREAD_ID`。在普通终端中需要明确传入
`--thread-id <真实聊天UUID>`。`--one-way` 表示只发邮件，`--dry-run` 不读授权码、不联网。

在手机中直接回复该通知，把意见写在引用原文上方。后台默认每 15 秒检查一次。
电脑需要联网，桌面应用需保持运行、登录并拥有目标聊天。
回复会以原聊天权限作为用户意见处理，请先阅读 [安全边界](SECURITY.md)。

## MCP 与后台服务

```sh
codex-mail-bridge mcp-config
```

把输出的配置表加入现有用户级 Codex 配置，保留其他设置，再重新加载 MCP 或新开本地聊天。
此命令只生成配置，不自动修改 Codex。MCP 的 `send_notification` 接受标题、正文和
真实聊天 UUID；`notification_status` 返回服务心跳与投递计数。
不要把某个聊天 UUID 固定写入全局配置。

配置好本机授权码文件后，可选择安装登录自启服务：

```sh
codex-mail-bridge service install --dry-run
codex-mail-bridge service install
codex-mail-bridge status
```

卸载后台服务：

```sh
codex-mail-bridge service uninstall
```

仅操作本项目的 `org.codexmailbridge.listener`，保留配置和历史。
完整移除时另行删除自己添加的 MCP 配置、卸载 Python 包，并审查私密配置及状态目录。

## 当前边界

- 原型已有手机回复进入活跃原聊天的实测记录；整理后的独立包采用隔离测试，空闲恢复还需真实验收。
- 未内建“所有聊天结束自动发信”或程序崩溃监控，提醒时机仍由用户要求和 Codex 调用决定。
- 不是通用邮箱管理器；不支持多账户、任意收件人或附件指令。
- 通过随机通知标记、邮件引用与发件人核对防止串信；这不是 DKIM／DMARC 验签。
- 去重可避免重复读取同一封信；失败或结果不明时保留状态，暂不自动重投。
- 通知有效期 14 天；单封邮件最多 512 KiB，新正文最多 24,000 字符。
- 桌面接口或本地聊天数据库结构改变后需要重新验证。

详细信息见 [英文 README](README.md)、[配置](docs/configuration.md)、
[兼容性](docs/compatibility.md)、[本地验证记录](docs/validation.md)。
