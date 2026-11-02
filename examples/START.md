# 启动示例

在仓库根目录执行，使用 Python 3.12+ 和 uv：

```powershell
uv sync --locked --all-packages
```

使用 TS 客户端或运行完整检查时，先安装前端工作区。pnpm 12.15.0 会按 `package.json` 的声明准备 Node 26.13.0，系统全局 Node 不受影响：

```powershell
pnpm install --frozen-lockfile
pnpm exec node --version
pnpm exec uv run --locked aurora check
```

项目支持的 Node 范围为 `>=26.4.0 <27`，`.node-version` 也固定为 26.13.0。终端里的裸 `node` 仍可能指向系统版本；通过 `pnpm exec` 或 pnpm 脚本使用项目运行时。OpenTUI 原生渲染需要 `--experimental-ffi`，TUI 启动脚本已包含该参数。

以下五个示例使用本地数据和假模型，无需模型密钥、外部模型服务或前端。每个示例使用独立数据目录。

| 示例 | 入口 | 主要依赖与职责 |
| --- | --- | --- |
| 持久化计数器 | [core_counter/main.py](core_counter/main.py) | core：声明、ctx、生命周期与落盘 |
| 控制流 | [control_flow/main.py](control_flow/main.py) | control + core：顺序、分支、循环与并发 |
| 独立 Agent | [react_agent/main.py](react_agent/main.py) | agent + control + model_adapter + core：运行调度、模型工具往返与引导 |
| 默认 Bot | [default_bot/main.py](default_bot/main.py) | bot：TOML 配置、资源工厂和默认装配 |
| 持续巡检宿主 | [live_workshop/main.py](live_workshop/main.py) | bot + CLI/API：持续运行、世界变化、远程观察和报告 |

## 持久化计数器

```powershell
uv run --locked python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount 2
uv run --locked python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount 3
```

在新数据目录中，两次输出分别为 `visits: 2` 和 `visits: 5`。同名计数器累加，不同名称独立保存。此示例只依赖 core，业务参数和结果使用普通函数参数及返回值。

## 控制流

```powershell
uv run --locked python examples/control_flow/main.py --data-dir build/control-demo --steps 3 --delay 0.2
```

装配为 `Serial → While(Serial → Branch) → Parallel → 汇总`。默认结果为 `{"count":3,"double":6,"square":9}`。运行时展示控制状态和业务状态；退出只保留最近一次运行的结果，不续跑历史调用。

执行契约和四种组合从 `aurora_control` 导入。控制定义使用 `org.aurora.control:*`，在途状态为 `org.aurora.control:state/control`。此示例不需要 agent、bot 或模型适配包。

使用较大的 `--delay`，在运行中按 Ctrl+C，可观察取消传播及控制状态清理。

## 独立 Agent

```powershell
uv run --locked python examples/react_agent/main.py --data-dir build/agent-demo --guide "保留当前计算进度"
uv run --locked python examples/react_agent/main.py --data-dir build/agent-demo --text "无需行动"
```

第一次由假模型请求本地加法工具，回填观察后输出 `计算结果：5`；流式推理期间通过 `AgentRuntime.submit()` 追加引导。第二次恢复上下文和消费进度，完成一次无需工具的激活。

示例直接装配 `ReActAgent`、`ModelCall`、`ToolExecutor`、`ReActDefaults` 和 `AgentRuntime`，不导入 bot。宿主提供状态地址及执行入口，并管理资源关闭与结果保留。运行回执通过 `wait()` 等待，等待者取消与 agent 取消分别管理；宿主关闭时停止提交并等待 runtime 收尾，再关闭模型。

其他可观察场景：

```powershell
# 普通工具失败进入下一轮模型观察
uv run --locked python examples/react_agent/main.py --data-dir build/agent-failure --tool-error
# 工具超时
uv run --locked python examples/react_agent/main.py --data-dir build/agent-timeout --tool-delay 0.2 --timeout 0.01
# 执行工具期间可按 Ctrl+C，随后用同一目录恢复
uv run --locked python examples/react_agent/main.py --data-dir build/agent-cancel --tool-delay 10 --timeout 20
uv run --locked python examples/react_agent/main.py --data-dir build/agent-cancel --text "无需行动"
```

中断的工具轮次保留可获得的结果，下一次激活接纳观察，不自动重复执行动作。模型文本是内部输出，不自动发送用户消息。

## 默认 Bot

```powershell
uv run --locked python examples/default_bot/main.py --data-dir build/bot-demo
uv run --locked python examples/default_bot/main.py --data-dir build/bot-demo --text "你好"
uv run --locked python examples/default_bot/main.py --data-dir build/bot-demo --profile secondary --text "再次见面"
```

无输入时只启动装配，不自动激活。提交文本后，假模型调用回显工具。`--profile` 保存模型角色绑定，后续启动继续使用该选择。配置由包内 `config.tomls/` 模板生成，位于 `<data-dir>/config/`，模型 profile、角色绑定和 bot 配置分开保存；业务状态保存在 ctx 快照中。示例的 bot 配置文件为 `org.aurora.bot/bot.toml`。

bot 提供 `org.aurora.bot:assemblies/default`、运行操作和 CLI 命令。它分配的消息、引导和运行状态地址归属 bot；注入这些地址的 agent 组件定义归属 `org.aurora.agent`。

持续运行离线默认 bot，并显式开放直接交流端点及 bot 状态：

```powershell
uv run --locked python examples/default_bot/main.py --data-dir build/bot-api --serve --port 10270
```

另开一个交互终端，在仓库根目录启动 TUI：

```powershell
pnpm --filter @aurorabot/tui start --connect http://127.0.0.1:10270 --instance main
```

顶部“交流 / 状态”页签可点击，或使用 Tab、F1、F2 切换。交流页按运行分组，模型文本显示为过程输出；Enter 发送，Shift+Enter 或 Alt+Enter 换行，也支持粘贴多行文本。运行中发送消息会追加引导。Ctrl+T 展开工具参数与结果，Ctrl+X 取消当前运行，点击运行内“停止”可指定目标。状态页展示后端开放的 ctx，可按 ID 或 location 筛选，↑/↓ 选择地址，F6 编辑选中项，Ctrl+N 填写新地址。

ctx 编辑器使用完整状态 ID、精确 location（JSON 对象）和 JSON 值，Tab 切换字段。F5 重新读取并替换草稿；F8 准备整项替换，Ctrl+D 准备删除；核对目标与内容后按 F9 执行，Esc 取消确认，再按 Esc 关闭编辑器并丢弃未保存草稿。JSON `null` 与地址不存在有不同反馈。写入仍受宿主 `--keys` 限制，不扩大开放范围；ctx 的读改写不是事务，也没有跨客户端冲突保护。写入配置状态仅覆盖运行期 ctx，不保存 TOML，不自动重建模型或工具。

TOML 配置编辑需要宿主显式开放，可在离线示例启动时添加 `--edit-config`：

```powershell
uv run --locked python examples/default_bot/main.py --data-dir build/bot-api --serve --edit-config
```

TUI 中按 F7 打开配置文件列表，↑/↓ 选择，F5 读取；Tab 进入原始 TOML 编辑区，F8 准备保存，F9 确认。保存保留提交文本和注释，经全部声明配置的结构、默认值及关联校验后替换文件，提示“重启后端后生效”；当前 ctx、模型、工具及正在执行的运行保持原配置。校验不创建资源，因此不能替代重启时的资源创建验证。凭证继续使用环境变量引用，不把密钥填写到配置中。

配置端点只访问已登记的 `ConfigSpec` 文件，不编辑 `host.toml`、`.env` 或任意路径。单文件编辑上限为 256 KiB；保存携带覆盖全部声明文件的读取修订，任一文件变化返回冲突并保留草稿，需重新读取后编辑。同一宿主的保存串行执行；不能保证与外部编辑器之间的跨进程原子比较，也不提供跨文件事务。保存失败不会把配置注入 ctx。ctx 与 TOML 写入遇到断线或响应丢失时均不自动重试，应先 F5 读取核对；编辑草稿不进入本地偏好。

底栏 `? 帮助` 可点击。输入为空时按 `?`（Shift+/）展开分组快捷键面板；已有文字时问号正常输入，F12 随时打开帮助。面板打开后按 `?`、Esc 或 F12 关闭，恢复原页面、草稿和焦点；帮助期间不发送消息、不切页或执行运行操作，Ctrl+C 仍可退出。宽终端分栏展示，窄终端纵向排列，可用 ↑/↓、PgUp/PgDn 或鼠标滚动翻阅。

模型输出及历史模型消息默认按 Markdown 渲染，包括标题、列表、强调、代码块和表格；流式输出会增量更新。用户输入和工具参数/结果保持原文展示。

PgUp/PgDn 翻阅，F3 回到底部。向上滚动时新输出不抢占位置；切页保留草稿、滚动位置和工具展开状态。编辑器外，运行结果不确定时 F5 核对，F4 明确重试最近一条未确认交流请求，保持原身份；重启后旧请求不自动重放。Ctrl+C 只退出 TUI，后端继续运行；在后端终端按 Ctrl+C 才关闭宿主。界面保留本次连接观察到的运行活动，断线期间不补发历史事件。

连接设置可以显式保存，下次启动无需重复传参。保存命令立即退出，不要求交互终端，也不连接后端：

```powershell
pnpm --filter @aurorabot/tui start --connect http://127.0.0.1:10270 --instance main --save-preferences
pnpm --filter @aurorabot/tui start
```

启动优先级为命令行参数、本地偏好、内置默认值。普通启动的 `--connect` / `--instance` 只覆盖本次连接；只有 `--save-preferences` 才保存连接选择。切换到不同地址且未指定 `--instance` 时，自动选择新后端提供的首个实例，不沿用旧后端的实例。地址仅接受不含凭证、查询参数和片段的 HTTP(S) URL。

本地偏好默认位于 Windows 的 `%APPDATA%/AuroraBot/tui.json`（无 APPDATA 时使用用户目录下的 `AppData/Roaming`），其他系统使用 `$XDG_CONFIG_HOME/aurorabot/tui.json` 或 `~/.config/aurorabot/tui.json`。`--preferences PATH` 可指定独立文件；相对路径以 TUI 进程工作目录为准，跨目录使用时建议传绝对路径。`--help` 显示当前默认路径。

正常退出时自动保存改变的页面和 Ctrl+T 全局工具展开偏好，下次启动恢复页面与输入焦点。按运行单独展开的工具、筛选词、草稿、消息和请求身份不保存。保存前重新读取文件并合并本次改变的界面字段；多个进程同时写同一文件时，最后一次完整写入生效，需要独立偏好时指定不同文件。

文件使用版本 1 的 JSON，允许字段为 `version`、`connect`、`instance`、`page`（`chat` / `state`）和 `showTools`（布尔值）。删除 `instance` 字段恢复自动选择。缺失文件使用默认值；无效 JSON、未知版本或字段会报告错误并保留原文件，需手动修正或换用其他偏好文件。写入失败会在终端恢复后报告，不影响后端运行。本地偏好不进入后端 TOML、ctx 或业务快照。

也可以使用共享 Node 客户端（在工作区执行）：

```ts
import { CtxClient } from '@aurorabot/client';

const client = new CtxClient('http://127.0.0.1:10270');
try {
  const info = await client.conversation.info();
  const message = {
    session_id: info.session_id,
    instance_id: info.instance_ids[0]!,
    request_id: crypto.randomUUID(),
    text: '你好',
  };
  const receipt = await client.conversation.submit(message);
  console.log('引导已接纳', receipt);
  console.log(await client.conversation.query({
    session_id: message.session_id,
    instance_id: message.instance_id,
    request_id: message.request_id,
  }));
} finally {
  await client.close();
}
```

`accepted` 表示接纳，查询的 `run_status` 才表示关联运行的进度；pending 包括排队和清理。需要停止时调用 `client.conversation.cancel({session_id, instance_id, run_id})`，目标来自同一回执。运行中提交新 request_id 会追加引导，收尾边界会关联下一次运行；关闭客户端不取消 bot。

网络结果不确定时保留原 message，先按其身份查询；同一会话下显式重试须使用原 request_id 和原文本，客户端不会自动重发。宿主重启返回 session_expired，需核对恢复状态后再决定是否发起新消息。每会话最多保留 4096 条回执，达到上限拒绝新消息，旧回执仍可查询；不承诺跨重启去重。完整信封和错误边界见[设计文档](../docs/aurorabot-design-v0.2.3.md#102-界面动作边界)。

已配置默认装配的 CLI 宿主可用 `serve --endpoints '["org.aurora.bot:endpoints/conversation"]'` 显式开放该端点；ctx 状态仍由 `--keys` 独立选择。`aurora_api` 插件提供端点接收方声明，未启用时不妨碍进程内运行；安装包不会自动启用插件或开放路由。接口仍限本机客户端，不接受浏览器 Origin。

## 持续巡检宿主

```powershell
uv run --locked python examples/live_workshop/main.py --data-dir build/workshop-demo serve --port 10270
```

该进程持续运行，模拟世界变化并通过示例内的调度策略触发巡检。工具内部组合四种控制组件，报告保存在本地台账中。按 Ctrl+C 关闭宿主、任务、模型和存储。

`aurora_world` 已提供独立的世界记录、来源去重、按位置读取、来源登记、固定身份接纳、可选 TOML 装配与后台主循环托管，W2.3 还提供时间与天气周期来源，接口见[世界输入设计](../docs/aurorabot-design-v0.2.3.md#77-直接交流与世界输入)。cadence 尚待接入；本示例的模拟来源和调度仍属示例实现，M4.W4 再替换为正式能力。仅安装 core/world 的来源装配、接收及恢复验收使用 `tests/fixtures/world_roundtrip.py`，不另增第六条示例路径。

TOML 路径需要安装 `aurora-world[config]`，显式启用 aurora_config、aurora_world、aurora_world.configuration 及来源提供插件；宿主同时装配 `configuration_component` 和 `configured_sources_component`。后者在 config 阶段读取 `org.aurora.world/config.toml`，默认空列表不启动任何来源。每个 `[[sources]]` 包含 source 定义 ID、唯一 source_id 和可选的 `[sources.config]`。来源参数不承载运行期凭证；修改配置需重新启动，状态覆盖不保存到文件。夹具的 `--configured` 模式验证此路径：

```powershell
uv run --locked python tests/fixtures/world_roundtrip.py .aurora/world-config-check --configured
```

重复运行同一存储目录可验证去重与恢复。后台失败状态位于 `org.aurora.world:state/sources`，按 source_id 查询或订阅；失败关闭对应来源入口，其他来源继续接纳，资源在宿主关闭时释放。配置及运行状态均不进入业务快照。

在另一个终端观察报告及控制状态：

```powershell
uv run --locked aurora --connect http://127.0.0.1:10270 ctx watch --key dev.example.workshop:state/reports
uv run --locked aurora --connect http://127.0.0.1:10270 ctx watch --key org.aurora.control:state/control
```

手动提交请求：

```powershell
uv run --locked aurora --connect http://127.0.0.1:10270 ctx set dev.example.workshop:state/request '{"text":"手动巡检","steps":4}'
```

## 插件发现与定义目录

插件发现分组为 `aurora.plugins`，依赖插件必须显式列出；CLI 内置启用 aurora_config 并装配配置服务，程序化宿主需显式启用和装配。定义查询不创建模型客户端：

```powershell
uv run --locked aurora --plugin aurora_control --plugin aurora_agent.model --plugin aurora_model_adapter id list
```

默认 bot 的宿主插件清单为：

```toml
plugins = [
  "aurora_config",
  "aurora_model_adapter",
  "aurora_agent.model",
  "aurora_agent.react",
  "aurora_agent.tools",
  "aurora_agent.react_defaults",
  "aurora_bot.assembly",
]
assembly = "org.aurora.bot:assemblies/default"
```

只使用执行契约不要求启用控制插件；使用四种控制组合时额外启用 `aurora_control`。组件定义、执行端口和状态归属见[公共 ID 目录](../docs/aurorabot-id-catalog-v0.2.3.md)。

## 使用已有配置启动真实模型后端

已有 `data/config/` 配置时，使用正式 CLI 宿主启动。`data/config/host.toml` 的插件列表须包含默认 bot 所需插件及 `aurora_api`，并选择 `org.aurora.bot:assemblies/default`。模型由 `profiles.toml` 与 `bindings.toml` 决定；profile 的 `credential` 保存环境变量名，凭证由 uv 从根目录 `.env` 加载。

```powershell
uv run --locked --env-file .env python scripts/serve_bot.py
```

脚本默认使用 `--data-dir data --port 10270`，可显式覆盖。它在 Python 内构造四项 bot 状态和直接交流端点的 JSON 参数，再交给正式 CLI 宿主，避免 Windows PowerShell 的原生参数传递移除 JSON 双引号；不加载另一套配置或装配实现。

需要从 TUI 编辑 TOML 时，在上述命令末尾加 `--edit-config`，显式开放 `org.aurora.config:endpoints/configuration`。已有宿主需先正常关闭再用该参数启动；保存配置后再次正常重启生效。未加此参数时，F7 会提示配置入口未开放，直接交流与 ctx 访问仍可用。

另一个终端运行 `pnpm --filter @aurorabot/tui start`。此后端按现有配置连接真实供应商，启动本身不激活 bot；TUI 发送消息才触发模型调用。工具是否可用由 bot 配置的 `tools` 决定。后端终端按 Ctrl+C 关闭并落盘；不要同时启动多个宿主使用同一 `data` 目录。

### 在默认装配中观察时间和天气

工作区统一安装已包含环境来源；独立安装使用 `aurora-world[environment]`。在现有 host.toml 的 plugins 列表中显式加入 `aurora_world`、`aurora_world.configuration`、`aurora_world.environment`，保留原来的 bot、模型和 API 插件。默认装配会托管 world 配置选中的来源；没有启用 world 配置插件时保持原来的装配行为。

编辑 `<data-dir>/config/org.aurora.world/config.toml`。缺失文件的模板默认为空列表，启用以下来源时移除 `sources = []`，不要保留两个同名声明：

```toml
[[sources]]
source = "org.aurora.world:sources/environment/time"
source_id = "environment/time"
[sources.config]
interval_seconds = 60

[[sources]]
source = "org.aurora.world:sources/environment/weather"
source_id = "environment/weather"
[sources.config]
place = "南京"
latitude = 32.0617
longitude = 118.7778
interval_seconds = 900
timeout_seconds = 10
```

地点名称和经纬度须一起修改；时间使用宿主本地时区。每次启动立即采样，此后按各自间隔采样，不补发停机期间的周期。移除某个来源项可单独停用，`sources = []` 停用全部来源，修改后重启生效，模板不覆盖已有配置。时间间隔至少 1 秒，天气至少 60 秒，天气总请求超时至多 30 秒。

```powershell
uv run --locked --env-file .env python scripts/serve_bot.py --world --edit-config
pnpm --filter @aurorabot/tui start
```

两个命令分别在两个终端运行。`--world` 开放世界记录与来源状态，TUI 状态页筛选 `org.aurora.world` 即可读取，F7 可编辑 TOML。观察包含采样时间、地点、温度、天气描述及数据有效时间；天气来自 [Open-Meteo 当前天气接口](https://open-meteo.com/en/docs)，属于天气模型数据，载荷保留提供方归属。超时、网络失败或无效响应写入 `status=unavailable` 和固定错误代码，不伪造天气；时间来源继续运行，下一个天气周期会重新采样。

环境采样只进入世界记录，不自动形成引导或调用模型；默认装配继续由显式交流激活。世界日志沿用完整保存策略，每次采样是新的观察，即使天气数据有效时间相同也不冒充同一外部事件；恢复后只新增当前观察。来源状态显示主循环是否运行，天气是否可用以对应观察的 status 为准。

## 真实模型验收

[scripts/accept_m2.py](../scripts/accept_m2.py) 创建独立 TOML profile 和 bot 配置，经 CLI 验证流式、完整响应、工具往返与恢复。该脚本会调用指定供应商，需要事先配置凭证；`--data-dir` 必须是尚不存在的目录。

```powershell
uv run --locked --env-file .env python scripts/accept_m2.py --data-dir build/model-acceptance --model deepseek/deepseek-flash --credential-env DEEPSEEK_API_KEY
```

可用 `--base-url` 指定兼容网关，`--timeout` 设置每种模式的总时限。脚本生成验收报告，不将运行期凭证写入配置或快照。

## 数据目录

快照位于 `<data-dir>/framework/ctx.json`，各示例不共用数据目录，也不并发访问同一目录。恢复要求所有状态定义已经登记；运行时不映射旧 ID，也不自动续跑任务。验证新命名空间时请使用新的数据目录，已有数据如需保留应先备份并离线转换对应 ID。

`build/` 是 Git 忽略的本地输出目录。对任意保留入口使用 `--help` 可查看完整参数。
