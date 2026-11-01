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

项目支持的 Node 范围为 `>=26.4.0 <27`，`.node-version` 也固定为 26.13.0。终端里的裸 `node` 仍可能指向系统版本；通过 `pnpm exec` 或 pnpm 脚本使用项目运行时。OpenTUI 原生渲染还需要 `--experimental-ffi`，TUI 界面与启动入口尚待交付。

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

另一个终端的 Node 客户端使用共享包（在工作区执行）：

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

## 真实模型验收

[scripts/accept_m2.py](../scripts/accept_m2.py) 创建独立 TOML profile 和 bot 配置，经 CLI 验证流式、完整响应、工具往返与恢复。该脚本会调用指定供应商，需要事先配置凭证；`--data-dir` 必须是尚不存在的目录。

```powershell
uv run --locked --env-file .env python scripts/accept_m2.py --data-dir build/model-acceptance --model deepseek/deepseek-flash --credential-env DEEPSEEK_API_KEY
```

可用 `--base-url` 指定兼容网关，`--timeout` 设置每种模式的总时限。脚本生成验收报告，不将运行期凭证写入配置或快照。

## 数据目录

快照位于 `<data-dir>/framework/ctx.json`，各示例不共用数据目录，也不并发访问同一目录。恢复要求所有状态定义已经登记；运行时不映射旧 ID，也不自动续跑任务。验证新命名空间时请使用新的数据目录，已有数据如需保留应先备份并离线转换对应 ID。

`build/` 是 Git 忽略的本地输出目录。对任意保留入口使用 `--help` 可查看完整参数。
