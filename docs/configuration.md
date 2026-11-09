# 配置与 MCP

核对日期：2026-11-09。首次启动见[助手指南](../examples/START.md)，运行入口见[操作指南](operations.md)。

## 配置与数据目录

安装助手默认使用 `build/onboarding`，正式产品默认使用 `data`。两者独立；助手可以按用户要求修改正式配置，不会自动复制自己的历史或覆盖已有配置。

| 相对于数据目录的位置 | 内容 |
| --- | --- |
| `config/host.toml` | 显式插件列表与装配 ID |
| `config/org.aurora.bot/config.toml` | Bot 实例、模型角色、工具与功能开关 |
| `config/org.aurora.adapter/model/profiles.toml` | 供应商、模型、适配器与凭证环境变量名 |
| `config/org.aurora.adapter/model/bindings.toml` | reasoning / cadence 等角色到 profile 的绑定 |
| `config/org.aurora.adapter/mcp.toml` | MCP 连接和工具选择 |
| `config/org.aurora.world/config.toml` | 已启用 world 配置插件时的来源与视图 |
| `config/org.aurora.bot/cadence.toml` | 已启用 cadence 时的决策节律配置 |
| `framework/ctx.json` | 持久业务快照 |
| `namespaces/` | 按命名空间隔离的文件及 SQLite 归档 |
| `logs/` | 宿主日志 |

配置服务只复制缺失文件，全部结构与关联校验通过后再注入非持久 ctx 状态。修改 TOML 后正常重启宿主；运行期 ctx 覆盖不自动写回文件或重建资源。模型、MCP 凭证在运行期从环境解析，不写入模板和快照。

## 模型

每个 profile 配置 `adapter`、`model`，以及可选的 `provider`、`base_url`、`credential`、`capabilities`、`thinking`、`reasoning_effort`。支持情况以实际供应商为准，错误参数不会自动降级。

```toml
[primary]
adapter = "org.aurora.adapter:adapters/model/litellm"
provider = "deepseek"
model = "deepseek-flash"
credential = "AURORA_MODEL_API_KEY"

[primary.capabilities]
streaming = true
tool_calls = true
file_input = false
```

这是助手的示例 profile；按你的供应商修改。`credential` 只填变量名，密钥由用户在环境或本机 `.env` 中设置。角色文件使用 `reasoning = "primary"`，Bot 使用 `model_role = "reasoning"`。首次助手只需要一个聊天模型，不需要 choice 模型。

需要思考时，在支持的 profile 中添加 `thinking` 表或 `reasoning_effort`；未填写时沿用供应商默认。文件输入须与模型真实能力一致，不能仅靠声明获得多模态能力。

## 本地 terminal MCP

助手使用的完整可复制模板是 [mcp.toml](../examples/onboarding/config.tomls/org.aurora.adapter/mcp.toml)。启动命令为 `uvx --from terminal-mcp==0.4.7 terminal-mcp`，工作目录是宿主明确传入的仓库根目录。首次下载需要网络。

| 远端工具 | Bot 中的名称 |
| --- | --- |
| session_create | terminal_create |
| session_send | terminal_send |
| session_interact | terminal_interact |
| session_read | terminal_read |
| session_list | terminal_list |
| session_close | terminal_close |
| session_wait_for | terminal_wait_for |

终端拥有当前用户的实际文件和进程权限，不是隔离沙箱。会话可以在同一助手后端内复用；后端退出会关闭自有 MCP 进程树，旧 session_id 不代表可恢复的进程。

local 配置中的 `command` 是参数数组，不拼接 shell；相对 `cwd` 基于宿主 workspace_root。子进程只继承 SDK 的基础环境，加上显式 `environment`，不会自动得到全部模型凭证。需要工具访问额外变量时显式配置，例如 `APP_TOKEN = "{env:APP_TOKEN}"`，不填凭证原文。

## 扩展 MCP 服务

Aurora 配置以 `schema_version = 2` 和 `[servers.<连接名>]` 组织，连接名是稳定身份。`type = "local"` 使用 command / cwd / environment；`type = "remote"` 使用 url / headers。两种传输均支持 legacy、auto 和固定协议选择，默认 legacy。启动、目录、执行与关闭分别有 timeout。

```toml
schema_version = 2

[servers.service]
type = "remote"
url = "http://127.0.0.1:8000/mcp"
required_capabilities = ["tools"]

[servers.service.tools]
include = ["echo"]
aliases = { echo = "service_echo" }
```

默认发现全部工具并自动命名；显式 include/exclude 控制集合，include=[] 不暴露工具，aliases 覆盖名称。安装助手只选择上表 7 个工具。公共动态定义属于 `org.aurora.adapter:tools/mcp/<工具名>`。

安装 extra 与启用插件分别处理。工具链需要 aurora_adapter.mcp、aurora_adapter.mcp.tools 及 agent 工具插件；默认 MCP Bot 装配另需 aurora_adapter.mcp.bot 与 aurora_bot.assembly。完整最小清单见助手的 [host.toml](../examples/onboarding/config.tomls/host.toml)。

独立生成正式 MCP 产品模板，可在目标目录不存在或已核对后执行：

```powershell
uv run --locked python -m aurora_adapter.mcp.preset data --api
```

它只补缺文件。已有 host 与候选不同会输出差异和 host.mcp.toml，不覆盖原选择，需审阅后显式应用。填写目标目录中的模型和 MCP 配置，再按操作指南启动。

旧 MCP 格式通过 `python -m aurora_adapter.mcp.migrate 旧文件 --output 新候选` 生成迁移候选；不会自动迁移快照、插件名或旧命名空间。其他客户端的 JSON 配置不能直接作为 Aurora TOML 使用。

## 世界与主动行为

正式产品可启用 aurora_world、aurora_world.configuration、aurora_world.environment，以及可选 aurora_adapter.mcp.world；world 配置用 sources 显式选择来源、source_id 和配置。MCP 来源还需 connection_id 和资源 URI，借用已配置客户端。安装助手不启用这些插件。

时间、天气、世界事件、cadence、笔记和计划唤醒的语义见[上下文与运行](context.md)。配置结构以包内模板和 schema 为准：[world](../packages/aurora_world/src/aurora_world/config.toml)、[MCP](../packages/aurora_adapter/src/aurora_adapter/config.tomls/mcp.toml)、[Bot](../packages/aurora_bot/src/aurora_bot/config.toml)、[cadence](../packages/aurora_bot/src/aurora_bot/cadence/config.tomls/cadence.toml)。
