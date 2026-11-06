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
| 独立 Agent | [react_agent/main.py](react_agent/main.py) | agent + control + adapter.model + core：运行调度、模型工具往返与引导 |
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

该进程持续运行，模拟来源通过正式 world 归档事件，cadence 将事件交给同一个 AgentRuntime 触发巡检。工具内部组合四种控制组件，报告保存在本地台账中。按 Ctrl+C 关闭宿主、任务、模型和存储。

`aurora_world` 已提供独立的世界记录、来源去重、按位置读取、来源登记、固定身份接纳、可选 TOML 装配与后台主循环托管，W2.3 还提供时间与天气周期来源，接口见[世界输入设计](../docs/aurorabot-design-v0.2.3.md#77-直接交流与世界输入)。本示例已使用正式来源工厂、TOML 装配及 cadence；模拟来源仅提交事件，直接交流复用同一 AgentRuntime。仅安装 core/world 的来源装配、接收及恢复验收使用 `tests/fixtures/world_roundtrip.py`，不另增第六条示例路径。

TOML 路径需要安装 `aurora-world[config]`，显式启用 aurora_config、aurora_world、aurora_world.configuration 及来源提供插件；宿主同时装配 `configuration_component`、`records.component(hooks)` 和 `configured_sources_component(ctx, hooks, records, depends_on=("aurora_world/records",))`。后者在 config 阶段读取 `org.aurora.world/config.toml`，默认空列表不启动任何来源。每个 `[[sources]]` 包含 source 定义 ID、唯一 source_id 和可选的 `[sources.config]`。来源参数不承载运行期凭证；修改配置需重新启动，状态覆盖不保存到文件。夹具的 `--configured` 模式验证此路径：

```powershell
uv run --locked python tests/fixtures/world_roundtrip.py .aurora/world-config-check --configured
```

重复运行同一存储目录可验证去重与恢复。后台失败状态位于 `org.aurora.world:state/sources`，按 source_id 查询或订阅；失败关闭对应来源入口，其他来源继续接纳，资源在宿主关闭时释放。配置及运行状态均不进入业务快照。

启用 world 的默认装配会在每次推理前刷新近期事件和环境观察，将其作为临时 user 视图提供给模型。bot 配置文件可添加以下可选段；产品默认文件为 `org.aurora.bot/config.toml`，本示例为 `org.aurora.bot/bot.toml`，修改后重启生效：

```toml
[context_view]
enabled = true
events = true
environment = true
notes = true
actions = true
max_chars = 12000
```

缺少该段时采用上述默认值；`enabled=false` 关闭临时视图，另外四个开关分别控制事件、环境、已启用的工作笔记和行动证据。字符预算包含视图元数据，各类非空材料平分预算并优先呈现最新记录；超长正文标记 abridged，整条省略计入 omitted，已呈现记录保留完整身份。近期事件并非完整归档，环境观察也不属于事件归档；该预算不裁剪消息历史或数据库。离线巡检模型识别并跳过观察块，只对引导生成巡检动作；真实模型如何使用视图须另行验收。直接交流、工具关联和历史恢复保持原有行为，`--direct-only` 不生成世界视图。

需要约束包含历史消息与工具定义的完整模型请求时，在 bot 配置文件中添加并重启：

```toml
[input_budget]
enabled = true
max_chars = 128000
```

默认关闭，最小预算为 1024。预算覆盖统一 ModelRequest 的完整 JSON 字符数，包含 system、业务观察、工具定义、历史消息及转义；不等同于供应商 token 上限。超限时只省略较早的完整交流段，保留当前交流中的引导和完整工具关系，并提供计入预算的省略提示。持久历史、笔记和归档保留原样，当前业务视图仍使用自己的 context_view 预算。

system、观察、工具定义或当前交流本身放不下时，运行返回 ModelInputBudgetExceeded，不继续请求模型。可以调整预算或输入策略后显式再次激活；已经完成的工具不会因预算失败重复执行，原始结果仍留存。运行中的长任务没有完整回复边界时也可能超限。行为及恢复回归见 `tests/e2e/test_input_budget_integration.py`，详细边界见[完整请求字符预算](../docs/aurora_bot_ctx_prompt_design.md#已实现的完整请求字符预算)。

工作笔记独立于 world，默认关闭。在同一个 bot 配置文件中添加以下配置并重启，即可向模型提供 notes_write、notes_read 和 notes_list；不需要将它们手工填入 tools：

```toml
[notes]
enabled = true
```

notes_write 创建示例参数：

```json
{
  "note_id": "inspection",
  "expected_revision": 0,
  "text": "等待核实通知结果，尚未确认发送成功。",
  "status": "active",
  "references": []
}
```

更新时携带最近读取到的 revision，并完整提供正文、状态和引用。冲突返回 note_conflict，原文保持不变。active 笔记在下一轮视图中可见且不会随时间过期；status=archived 将其移出当前视图，仍可通过 notes_read 或 notes_list 的 status=all 读取。notes_list 返回 200 字符预览和 next_after，每页最多 50 条；notes_read 返回全文。每实例最多 128 条，单条正文最多 16000 字符，达到容量后仍可更新已有笔记，归档不释放容量。

笔记由宿主快照保存，正常关闭后恢复；关闭 `[notes]` 不删除已有内容，恢复也不自动执行计划。笔记和引用本身不证明工具动作成功。`scripts/serve_bot.py` 将笔记作为只读状态开放，可用 ctx get 读取 `org.aurora.bot:state/notes`、location 为目标 instance_id；`[context_view] notes=false` 只关闭视图展示，工具仍可使用。具体数据边界见[主动上下文设计](../docs/aurora_bot_ctx_prompt_design.md#已实现的持久工作笔记)。离线巡检示例不模拟模型自主写笔记，工具往返、取消与恢复由 `tests/e2e/test_work_notes_integration.py` 验证。

需要按视图或笔记中的 world_event 引用读取事件原文时，在同一个 bot 配置文件中启用：

```toml
[archive]
enabled = true
max_chars = 8000
```

该工具要求宿主已经装配 world 记录服务；live_workshop 的持续模式满足此条件，`--direct-only` 不支持此配置。不要将内置工具手工加入 tools 列表。模型调用 world_read_event 的参数为 `{"journal_id":"引用中的数据库 ID","record_id":"引用中的记录 ID","offset":0}`；返回 text 为原始 JSON 片段，按 next_offset 继续，直到 null 表示结束。各页 text 拼接后才构成完整 JSON；字符串载荷也保留 JSON 引号和转义，不能把第一页当作完整事件。

max_chars 限制每页 value 的完整 JSON 长度，含元数据及转义、不含工具结果外层信封，范围 1024–32000；不限制累计消息历史或整次模型输入。错库、缺失记录、越界分别返回 archive_wrong_journal、archive_not_found、archive_invalid_offset；服务不可用或元数据过长也明确失败，不自动换库或重试。工具只读取已知事件引用，不检索环境观察或 tool_call，不消费、重放事件或将事项标为完成。事件过期及重启后的引用读取由 `tests/e2e/test_event_archive_integration.py` 验证。

需要保存并核对工具调用结果时，在同一个 bot 配置中启用并重启：

```toml
[actions]
enabled = true
max_chars = 8000
```

该功能独立于 world 和 notes，不在 tools 中手工声明。模型可以使用 `actions_read`，例如 `{"run_id":"原运行身份","call_id":"原工具调用身份","offset":0}`；按 next_offset 继续分页，至 null 后拼接 text 得到完整证据 JSON。近期视图提供最近 16 次调用的引用及 outcome；`[context_view] actions=false` 只隐藏摘要。

completed/failed 表示工具返回成功/错误，unknown 表示需要核实，not_executed 表示执行器未进入调用；这些状态不由笔记内容决定。结果缺失不证明动作未发生，不自动重试。相同实例内 run_id/call_id 不允许复用；重复引用阻止整个新批次。记录独立保存于 bot 命名空间的 actions.sqlite3，关闭功能不删除记录，完整备份须在停机后包含数据库。当前不自动裁剪记录。回归见 `tests/e2e/test_action_evidence_integration.py`，存储、预算和错误边界见[行动证据设计](../docs/aurora_bot_ctx_prompt_design.md#已实现的行动证据)。

在另一个终端观察报告及控制状态：

```powershell
uv run --locked aurora --connect http://127.0.0.1:10270 ctx watch --key dev.example.workshop:state/reports
uv run --locked aurora --connect http://127.0.0.1:10270 ctx watch --key org.aurora.control:state/control
```

手动交流可通过 TUI 连接本机地址并选择 `workshop`，也可通过正式 conversation 端点提交：

```powershell
$base = "http://127.0.0.1:10270"
$info = Invoke-RestMethod "$base/conversation/info" -Method Post -ContentType "application/json" -Body '{}'
$body = @{ session_id = $info.result.session_id; instance_id = "workshop"; request_id = [guid]::NewGuid().ToString(); text = "手动巡检" } | ConvertTo-Json
Invoke-RestMethod "$base/conversation/submit" -Method Post -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

离线模型接受普通文本；也可将 `text` 填为含 `text`、`steps`、`delay`、`fail` 的 JSON 文本以演示步骤和工具失败。运行中交流仍属于当前运行；取消使用 conversation/cancel 的 session_id、instance_id、run_id，取消后需显式提交后续工作。设置 `settings.automatic=false` 暂停产生新巡检事件，已归档事件仍由 cadence 接纳，环境 tick 继续变化。

仅验证直接交流时使用独立目录：

```powershell
uv run --locked python examples/live_workshop/main.py --direct-only --data-dir build/workshop-direct serve --port 10270
```

该模式不启用 world/configuration/cadence 插件，不生成世界事件数据库。普通模式的来源与消费配置分别位于 `config/org.aurora.world/world.toml`、`config/org.aurora.bot/cadence.toml`；模板只补缺失文件。API 仅允许修改示例 settings 与模型 bindings，其他状态只读；绑定的文件配置仍需通过 TOML 修改并重启。

旧示例的 `dev.example.workshop:state/request` 及自有调度处理器已移除，不提供兼容转发。旧快照若包含这些状态须保留原目录并换新数据目录运行；本次不自动改写用户快照。已有 world/cadence 快照也不能直接以 --direct-only 恢复。报告台账仍持久保存，成功运行保留最近一组引导及完整工具往返，未收束工具结果沿默认恢复语义保留；恢复不重试工具副作用。

## 插件发现与定义目录

插件发现分组为 `aurora.plugins`，依赖插件必须显式列出；CLI 内置启用 aurora_config 并装配配置服务，程序化宿主需显式启用和装配。定义查询不创建模型客户端：

```powershell
uv run --locked aurora --plugin aurora_control --plugin aurora_agent.model --plugin aurora_adapter.model id list
```

默认 bot 的宿主插件清单为：

```toml
plugins = [
  "aurora_config",
  "aurora_adapter.model",
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

模型与 MCP 统一安装包为 `aurora-adapter`，模块分别为 `aurora_adapter.model` 和 `aurora_adapter.mcp`。独立模型配置插件安装 `[model]`，LiteLLM 安装 `[litellm]`；默认 bot 已依赖后者。模型配置位于 `<data-dir>/config/org.aurora.adapter/model/profiles.toml` 与 `model/bindings.toml`，MCP 配置位于同一命名空间下的 `mcp.toml`。旧包、插件名、配置路径和公共 ID 的迁移见[变更记录](../docs/CHAGELOG.md#2026-11-04)，宿主不自动迁移旧数据。

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

两个命令分别在两个终端运行。`--world` 开放近期事件、环境观察与来源状态，TUI 状态页筛选 `org.aurora.world` 即可读取，F7 可编辑 TOML。观察包含采样时间、地点、温度、天气描述及数据有效时间；天气来自 [Open-Meteo 当前天气接口](https://open-meteo.com/en/docs)，属于天气模型数据，载荷保留提供方归属。超时、网络失败或无效响应写入 `status=unavailable` 和固定错误代码，不伪造天气；时间来源继续运行，下一个天气周期会重新采样。

环境采样只更新 `org.aurora.world:state/environment`，按 source_id 区分，不进入普通事件数据库或自动触发 cadence。时间默认保留最新 1 条，天气按宿主接收时间保留一小时内最多 4 条；world 在接纳时、启动时和每 30 秒统一刷新，无新输入也会过期。普通事件保存于 `namespaces/ns-org.aurora.world/events.sqlite3`，`state/records` 只提供近期文本视图，历史与去重不因呈现裁剪丢失。

统一保留规则写在文件根级 `[view]`（不要放进 `[sources.config]`）：

```toml
[view]
recent_seconds = 3600
max_chars = 32000
max_event_chars = 8000
time_count = 1
weather_count = 4
weather_seconds = 3600
refresh_seconds = 30
```

普通条目按整对象纳入，字符预算允许多出一个边界条目；超过单条预算时展示明确预览和 record_id，完整事件可用 `WorldRecords.get_by_id` 查询。数据库、事件服务和消费者均由宿主显式持有；`WorldRecords(ctx, storage)` 注入来源和 cadence，不能重新构造一个 `WorldRecords(ctx)` 来读取已有服务的内存。

已有 v1/v2 世界日志不会自动转换。先停止宿主，运行 `uv run --locked python -m aurora_world.migrate --root data`，将保留记录导入数据库并保留原消费身份，原快照备份到 `framework/ctx.before-world-database.json`。旧日志没有统一接收时间，迁移使用导入时刻；迁移前已裁剪的历史不会补造。原有来源配置的 retain_count/retain_seconds 手动改到 `[view]` 的 time_count/weather_count/weather_seconds。以后备份及恢复须同时包含数据库与 ctx 快照。

### 最小 cadence：原样转发世界记录

在默认 bot 的 `host.toml` 插件清单中显式加入 `aurora_world`、`aurora_bot.cadence`，保留已有的 bot、模型和配置依赖。来源按前节另行配置；只接收程序写入的世界记录时，无需启用 world 配置或环境插件。MCP 默认 bot 装配同样复用这一路径。

首次启动只补齐缺失的 `<data-dir>/config/org.aurora.bot/cadence.toml`，默认 `source_ids = []` 不转发。选择实际来源实例后重启，例如只关注外部消息：

```toml
source_ids = ["external/resources"]
```

首次选择从数据库可用历史开始。每条选定世界记录的 payload 原样形成一条引导，空闲时可启动运行，运行中继续接纳；环境观察默认不进入事件序列；需要归档并转发的来源须在对应 [[sources]] 下显式配置 presentation = "events"。cadence 选择了仍按环境观察呈现的来源时会明确拒绝启动，避免配置看似生效却没有转交。来源及世界消息身份保存在转交关联中，不给模型载荷加包装；回执表示已提交引导，不表示业务完成。直接交流继续使用同一 AgentRuntime。

```powershell
uv run --locked --env-file .env python scripts/serve_bot.py --world --cadence --edit-config
```

`--cadence` 仅开放观察状态，不启用插件。TUI 状态页读取 `org.aurora.bot:state/cadence`，location 的 instance_id 与 bot 配置一致；其中 position 为扫描位置，pending 为尚无确定回执的原消息，receipts 保存消息、guidance_id、sequence 和 run_id。F7 可编辑来源选择，正常关闭后重启生效。已有消费状态绑定了原来源集合，改变集合会暂停，不能通过改配置悄悄改变消费范围。

`error=TransferUncertain` 表示须核对 pending 是否已经进入 agent；`CursorInvalid` 表示日志换代、缺失或裁剪缺口；`SelectionChanged` 表示来源范围不一致。暂停不阻断直接交流，也不会因重启自动解除。核对时先停止宿主并保留完整快照，对照 world、pending、receipts 与 agent 数据；不能仅凭文本相同认定已投递。首版没有自动核对或重置命令，须由宿主明确决定修复后的消费状态，不能直接删除游标来重放。

完整回执随宿主异步保存，暂不自动裁剪；不能据此承诺崩溃时恰好一次执行。world 的去重覆盖数据库历史，呈现窗口外的同身份重投仍返回原记录。离线回归为 `uv run --locked pytest packages/aurora_bot/tests/unit/test_cadence_state.py tests/e2e/test_cadence.py -q`；live_workshop 已完成正式替换，双路径与恢复验收见 `tests/e2e/test_live_workshop.py`。

## MCP 独立客户端验收

M4.B1 提供 `aurora-adapter[mcp]`；工作区开发依赖已包含该 extra，统一产品安装不自动启用 MCP。通过现有测试夹具启动并关闭一个本机 MCP 服务和独立宿主：

```powershell
uv run --locked python tests/fixtures/mcp_roundtrip.py build/mcp-acceptance
```

夹具只在指定验收目录创建测试配置，完成真实 Streamable HTTP 能力发现、测试工具往返、资源读取、断线诊断和最终落盘；不访问真实供应商或用户模型。它不是新增产品示例入口，不要将验收目录指向已有用户数据。

自定义宿主显式启用 `aurora_config` 和 `aurora_adapter.mcp`，登记生命周期插槽，装配 `configuration_component` 与 `MCPClients(ctx, hooks).component()`。消费者依赖默认组件身份 `aurora_adapter/mcp`，在 prepare 完成后借用：

```python
async with clients.connection("local") as client:
    tools = await client.list_tools()
```

SDK 对象仅在适配层使用，不存入 ctx 或传给 world/agent。借用期间不要跨任务退出或自行关闭客户端，退出后不要保留引用继续使用；长期消费者在自己的 stop 阶段收束。停止整个宿主会封闭借用入口并取消剩余借用，等待它们的 finally 完成后才释放连接。

缺失配置文件会在 `<data-dir>/config/org.aurora.adapter/mcp.toml` 生成 `schema_version = 2` 与空 `[servers]` 模板。下面是一份可运行的连接声明；服务名 `local` 就是原 connection_id，名称不表示传输类型：

```toml
schema_version = 2

[servers.local]
type = "remote"
url = "http://127.0.0.1:8000/mcp"
protocol = "2026-07-28"
required_capabilities = ["tools", "resources"]
timeout = { startup = 10, catalog = 30, execution = 30, shutdown = 10 }

# [servers.local.headers]
# Authorization = "Bearer {env:AURORA_MCP_TOKEN}"
```

headers 支持 `{env:NAME}` 引用和固定前缀；Authorization 等凭证字段不能填写纯字面量。引用只在 prepare 创建连接时解析，不进入 ctx、快照或日志；缺失或非法值报告服务名与字段位置。`enabled = false` 不创建连接、解析凭证或登记工具。地址不可包含凭证、查询串、片段或环境引用；修改配置后重启生效。

B5.2–B5.3 支持 HTTP(S) Streamable HTTP 和 stdio 的 legacy、auto 和固定 2026-07-28 三种策略，默认 legacy。允许的实际版本为 2025-11-25 与 2026-07-28；legacy 直接旧握手，auto 由 SDK 探测并按策略回退，固定新版显式 discover 后检查能力。HTTP 401/403、5xx、重定向和损坏 JSON 明确失败，不掩盖为成功回退；RPC 错误本身不作为版本证据。local 与 remote 使用相同协商及工具执行路径。SDK 固定 2.3.0，不自动处理多轮输入或重放工具动作。

本地服务由宿主显式装配 `MCPClients(ctx, hooks, workspace_root=workspace_root)`；workspace_root 是宿主选定的项目目录，不能把任意调用时 cwd 当作默认根。相对 cwd 基于该根目录，prepare 检查目录存在；不填写 cwd 时使用工作区根。command 是参数数组，不拼接 shell 字符串；环境变量只继承 SDK 基础集合，再覆盖显式 environment，不修改宿主环境。

```toml
schema_version = 2

[servers.files]
type = "local"
command = ["python", "server.py"]
cwd = "tools"
protocol = "legacy"

[servers.files.environment]
APP_TOKEN = "{env:APP_TOKEN}"

[servers.files.tools]
include = ["read_file"]
aliases = { read_file = "files_read_file" }
```

stdio 的 stdout 仅允许 JSON-RPC，每条消息上限 4 MiB，非法 JSON、未结束消息超限和 EOF 都明确失败；原始 stderr 丢弃，避免洪泛阻塞或泄露凭证。关闭先关 stdin、限时等待，再回收所属 Windows Job/POSIX 进程组，根进程已退出也会清理其所属后代。启动失败不自动重启，工具动作不自动重发；后台观察能报告本地进程退出，但不将 ready 当作永久健康保证。

根级 `[timeout]` 提供公共超时，各服务逐字段覆盖；startup/catalog/execution/shutdown 默认分别为 10/30/30/10 秒，限制握手、完整目录发现、单次工具调用和每服务每次 stop/clean 等待。工具执行同时受 agent 外层超时约束。SDK 请求与 HTTP 空闲读取上限取前三者的最大值，各操作通过自己的外层预算提前结束。关闭等待超时不取消正在执行的 finally，可再次等待；真正的关闭异常需诊断后重建宿主。

客户端状态使用 `org.aurora.adapter:state/mcp/clients`，location 为 `{"owner": "aurora_adapter/mcp", "connection_id": "local"}`；error_location 仅包含安全字段位置；configured_protocol 表示配置策略，negotiated_protocol 替代旧 protocol_version，negotiation_attempts 最多记录四次协商的方法、HTTP 状态和数值 RPC 错误码。状态非持久，无快照迁移；ready 表示启动准备完成，没有后台健康探测；失败不自动重连或重放请求。

旧 connections/tools 布局及混合布局均拒绝加载。先生成独立候选及规范化差异，审阅后自行应用；命令不覆盖任何已有文件、不读取凭证、不连接服务：

```powershell
uv run --locked python -m aurora_adapter.mcp.migrate data/config/org.aurora.adapter/mcp.toml --output build/mcp-v2-candidate.toml
```

迁移保留服务名、固定新版策略、工具名称与公共 ID；没有旧工具选择的连接转为 `include = []`。同一远端工具对应多个旧别名时停止转换。保留 bot 的显式工具选择及实例身份、world 的 connection_id 和业务快照，不合并多个 bot/工具实例；需核对 bot 的 tool_timeout。候选新增 shutdown=10 秒，关闭超时后仍须继续等待清理。差异忽略注释和排版，不回显原文件注释。

产品入口尚不自动装配 MCP；世界通知和工具分别通过下面的桥接组件显式装配。添加插件清单仅登记定义，不会自动连接服务。

### MCP 工具桥

安装 `aurora-adapter[mcp-tools]`，显式启用 `aurora_config`、`aurora_adapter.mcp`、`aurora_agent.tools`、`aurora_adapter.mcp.tools`；使用默认 bot 时同时启用其原有插件。只使用工具桥不需要安装或启用 world、bot、CLI、API。

在 `<data-dir>/config/org.aurora.adapter/mcp.toml` 的相应服务下添加：

```toml
[servers.local.tools]
include = ["echo"]
aliases = { echo = "local_echo" }
```

include/exclude 使用精确远端名称，exclude 优先；aliases 将已选远端名称映射到本地模型名称。名称须为小写字母开头的小写字母、数字或单下划线分隔名称，最长 64 字符。例如 `local_echo` 对应公共 ID `org.aurora.adapter:tools/mcp/local_echo`。不同服务的同名工具可指定不同本地名称；名称重复、远程工具缺失或参数 schema 无效会使启动失败。

工具桥默认 `include = ["*"]`，对声明 tools 能力的服务发现全部工具；无工具能力且没有显式选择要求的服务保留供其他消费者使用。未指定 aliases 的工具使用 `mcp_<server_slug>_<tool_slug>_<digest>`，digest 为原始服务名和远端工具名紧凑 UTF-8 JSON 的 SHA-256 前 12 位；slug 分别截取到 16/24 字符，名称最长 58 字符，算法以 v2 固定。自动名称、显式别名、既有本地工具名称与公共 ID 统一检查冲突，失败时不登记部分目录。`include = []`、空 exclude 表示不发现、不登记该服务的工具。修改配置或服务端目录后须重建宿主，不在运行中热改集合。

宿主将工具发现列为消费者的前置依赖：

```python
from aurora_adapter.mcp import MCPClients
from aurora_adapter.mcp.tools import MCPTools

clients = MCPClients(ctx, hooks)
tools = MCPTools(registry, ctx, hooks, clients)
components = [
    configuration_component(registry, ctx, hooks, storage),
    clients.component(),
    tools.component(),
    *assembly.components(depends_on=(tools.instance_id,)),
]
```

这里 `assembly` 是既有 `DefaultAssembly` 实例。它在发现完成后才检查工具并创建模型；bot 的配置选择相应工具（没有其他工具时删除模板中的 `tools = []`）：

```toml
[[tools]]
tool = "org.aurora.adapter:tools/mcp/local_echo"
instance_id = "echo"
```

无 bot 的宿主可从登记的 ToolSpec.factory 创建 ToolInstance，再将 plug 接入 ToolExecutor；完整代码见 [mcp_tools_roundtrip.py](../tests/fixtures/mcp_tools_roundtrip.py)。工厂不接受额外实例配置，连接和远程名称由 MCP 配置确定。实例关闭仅封闭自身入口，在途调用由消费者收束；共享连接由 MCPClients 最后释放。

结果保留 MCP JSON 字段（如 `content`、`structuredContent`、`isError`），包括图像、资源链接等内容块；桥不会自动下载附件。业务错误为 `mcp_tool_error`，其内容仍进入失败观察；协议错误为 `mcp_protocol_error`，只保留数值错误码。请求超时为 `mcp_timeout`，传输中断后的结果未知为 `mcp_result_unknown`，无有效结果为 `mcp_invalid_result`，尚未提交为 `mcp_unavailable`；额外交互为 `mcp_input_required`，不自动续发。外层执行器超时/取消沿用 `timeout`/`cancelled`。超时、取消及结果未知均不表示远端动作没有执行，不自动重试；调用始终通过 agent 的参数校验与 before_call/after_call。

本机验收命令（夹具创建测试配置，目录勿指向已有用户数据）：

```powershell
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-tools-acceptance
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-bot-acceptance --bot
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-legacy-acceptance --protocol legacy
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-auto-acceptance --protocol auto
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-stdio-acceptance --transport local --protocol legacy
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-stdio-bot-acceptance --transport local --protocol auto --bot
uv run --locked python tests/fixtures/mcp_tools_roundtrip.py build/mcp-auto-tools-acceptance --transport local --automatic --bot
```

两条路径均只访问本机测试 MCP 服务，默认 bot 使用假模型。外部真实 MCP 服务兼容性验证另行安排；B3 已完成工具桥与世界通知桥的 HTTP、stdio、混合连接共享关闭验收，使用正式产品装配和假模型。

### MCP 默认 bot 产品预设

安装 `aurora-adapter[mcp-bot]` 和所需宿主 `aurora-cli`；API 另需 `aurora-api`。工作区开发环境已有这些包。执行一次预设，填写生成的模型 profiles/bindings 与 MCP servers，即可通过正式入口使用工具，不需要手写 Python 装配：

```powershell
uv run --locked python -m aurora_adapter.mcp.preset .aurora-mcp --api --world
# 填写 .aurora-mcp/config 下的模型和 MCP 配置后：
uv run --locked aurora --root . -d .aurora-mcp org.aurora.bot:commands/run/submit "使用可用工具完成任务" --instance-id main
uv run --locked aurora --root . -d .aurora-mcp serve --port 8765 --endpoints '["org.aurora.bot:endpoints/conversation"]'
```

instance_id 应与 `org.aurora.bot/config.toml` 一致。`--world` 显式启用世界配置和 MCP 来源插件，来源列表仍需按下一节填写；`--api` 显式启用 API 插件。只需工具时可省略两项。预设不创建连接、子进程或模型，不覆盖已有文件。已有 host.toml 与预设不同时显示差异，写入 `host.mcp.toml` 并返回 2；审阅并显式应用候选后启动。候选已存在且不同则报错保留。

预设选择 `org.aurora.adapter:assemblies/mcp/default_bot`，先发现工具，再与 bot 的本地工具选择合并。自动补入工具的实例身份使用工具 ID 的 local_path；已显式选择的 MCP 工具保留原实例身份，不重复添加。运行期目录不写回 TOML 或配置状态，名称/实例冲突仍拒绝启动。标准装配工厂新增 workspace_root 关键字，第三方工厂须同步接收；它来自 `--root`，与数据目录独立，stdio 默认 cwd 和相对路径均以此为准。

### MCP 世界通知桥

世界来源目前使用 2026-07-28 的订阅契约；即使旧版连接声明 resources，来源也会明确报 unsupported_subscription_protocol，不尝试未实现的旧订阅。该连接仍可供工具使用。

安装 `aurora-adapter[mcp-world]`，宿主显式启用 `aurora_config`、`aurora_adapter.mcp`、`aurora_world`、`aurora_world.configuration` 和 `aurora_adapter.mcp.world`。保留上述 MCP 连接配置，使用共享 MCPClients，并用 `mcp_world_component` 替代通用 configured_sources_component；不要在同一 ctx 重复装配两个 world 来源所有者：

```python
from aurora_adapter.mcp import MCPClients
from aurora_adapter.mcp.world import mcp_world_component
from aurora_world import WorldRecords

clients = MCPClients(ctx, hooks)
records = WorldRecords(ctx, storage)
components = [
    configuration_component(registry, ctx, hooks, storage),
    clients.component(),
    records.component(hooks),
    mcp_world_component(ctx, hooks, clients, records, depends_on=("aurora_world/records",)),
]
```

在 `<data-dir>/config/org.aurora.world/config.toml` 的现有 sources 列表中增加来源。若文件只有 `sources = []`，先移除该行；已有环境来源可以与 MCP 来源共存于同一列表：

```toml
[[sources]]
source = "org.aurora.adapter:sources/mcp/resources"
source_id = "external/resources"
[sources.config]
connection_id = "local"
buffer_size = 64
max_content_bytes = 1048576
watch_tools = false

[[sources.config.resources]]
uri = "board://current"
mode = "resource"

[[sources.config.resources]]
uri = "events://latest"
mode = "event"
```

URI 精确匹配，不自动读取服务端报告的其他 URI 或子资源。mode 默认为 resource，读取当前资源内容；notification 只存变化提示、不读取；这两种模式均生成本地观察身份，不把 URI 或内容哈希当作稳定事件 ID。event 要求服务端返回单个文本资源，其文本是严格 JSON，例如 `{"message_id":"event-42","payload":{"text":"原文"}}`；缺失身份或额外字段会使来源失败。同连接、URI、message_id 在同 source_id 下重投同文不会重复记录，异文明确冲突。切换到另一逻辑上游时应选择新的 source_id 或 connection_id。去重限于 world 仍保留的记录。

订阅确认后才开始接纳，不在启动时自动读取资源或补发停机期间消息。MCP 资源变化是“可能需要重新读取”的提示，SDK 会合并尚未消费的同 URI 通知；读取时得到的是最新值，event 模式也不能据此保证完整业务事件历史。需要逐条可靠投递的上游必须另外提供可追读事件日志契约。

桥接状态位于 `org.aurora.adapter:state/mcp/world`，location 为 `{"source_id":"external/resources"}`。identity_modes 明确是本地观察还是来源消息身份，accepted/duplicates 表示 world 数据库接纳及去重结果。watch_tools 只设置 tools_dirty，不把目录变化写成世界输入，也不热更新工具。缺失能力、订阅未确认全部选择、身份错误、读取失败、连接丢失及队列溢出均有固定错误码，并封闭对应来源；不自动重订阅或重放。修正后需正常重启宿主。

buffer_size 限制适配器等待处理的通知数，不包括当前一项读取；max_content_bytes 限制读取后可接纳的序列化内容大小，不是 HTTP 响应下载上限。SDK 另有 1024 项不同待消费事件的上限，其丢流报告为 subscription_lost。HTTP 空闲读取上限取服务 startup/catalog/execution 超时的最大值，长时间无消息的服务应发送流心跳或配置相应超时。停止来源会等待订阅与在途读取收束，释放借用而不关闭共享客户端；已收到但尚未接纳的观察会记入 discarded，并报告 stopped_with_pending 或对应故障及日志。桥接诊断不持久化，重启不会恢复这些待处理通知；已接纳的 world 记录由宿主最终落盘。

独立验收夹具在本机启动真实 MCP 服务，验证通知、资源读取、稳定事件去重、宿主恢复、来源失败隔离和断流：

```powershell
uv run --locked python tests/fixtures/mcp_world_roundtrip.py build/mcp-world-acceptance
```

该命令只创建测试服务，但会写指定目录的验收配置，请使用独立目录。同一目录再次运行会验证保留记录的去重与新观察追加。它不调用真实模型，不是新的产品示例入口。

## 真实模型验收

真实模型手工验收使用当前 CLI。先按上文在独立数据目录中配置宿主插件、默认装配、模型 profile、角色绑定及所需工具，并通过环境变量提供凭证。以下以已配置好的 `build/model-acceptance` 为例；执行会调用配置的供应商及模型选择的工具。

```powershell
uv run --locked --env-file .env aurora --data-dir build/model-acceptance org.aurora.bot:commands/run/submit "请回复一条简短的验收消息" --instance-id main
```

按需在 bot TOML 中切换 `streaming`，检查 CLI 的运行终态和模型输出；需要工具验收时，使用该目录中显式启用的工具。重复启动同一目录可检查历史恢复，恢复本身不自动激活 agent。配置与快照不保存运行期凭证。

常规工具往返、流式/完整响应、收尾与重启回归由 [默认装配测试](../tests/e2e/test_default_assembly.py) 使用假模型或模拟传输验证，无需调用真实供应商。

## 数据目录

快照位于 `<data-dir>/framework/ctx.json`，各示例不共用数据目录，也不并发访问同一目录。恢复要求所有状态定义已经登记；运行时不映射旧 ID，也不自动续跑任务。验证新命名空间时请使用新的数据目录，已有数据如需保留应先备份并离线转换对应 ID。

`build/` 是 Git 忽略的本地输出目录。对任意保留入口使用 `--help` 可查看完整参数。
