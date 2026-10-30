# M2 最小 bot：规划与设计意图交接

交接日期：2026-10-30。代码基线：`e15fb3a`（提供公共 ID 目录查看命令）。

## 1. 从哪里继续

M0、M1 已完成，M1.8 微内核集成验收通过。下一阶段是 M2：在现有 core 上装配最小 bot，完成模型调用、流式输出、一次工具循环、取消和状态恢复。

`aurora_model_adapter` 与 `aurora_bot` 当前只有包骨架和依赖声明，尚无 ModelClient、ReAct 或对话运行实现。不能将公共 ID 目录中的规划对象理解为已经存在的实现。

本文件是用户明确要求的交接文档，用于新对话继续任务；本次只整理规划与设计意图，不开始 M2 编码。

推荐阅读顺序：

1. 根目录 [AGENTS.md](../AGENTS.md)：协作与编码规范。
2. 本文件：已确定边界、设计背景、下一步切片。
3. [设计文档](aurorabot-design-v0.2.2.md)：重点阅读第 7、8、9、11 节。
4. [公共 ID 目录](aurorabot-id-catalog-v0.2.2.md)：第 5、6 节的模型、bot、状态与事件身份。
5. [总体计划](plan.md)：M2.1–M2.8 及 D03、D05、D06、D07、D10。
6. [变更记录](CHAGELOG.md)：现有接口的实际语义；历史条目按日期和上下文阅读，不把早期实现描述当作当前实现。

新对话先检查工作区与最新提交，保留用户改动。建议从 M2.1 的模型协议和确定性假模型开始，完成可离线验收的切片；具体未决语义按第 5 节收敛。

## 2. 设计意图的来源与效力

### 2.1 已有设计约束

- core 提供登记、寻址、状态、订阅、连接、生命周期和单次调用机制；bot、模型、工具及业务流程属于各功能包或插件。
- `hook_handler` 表达插头，`hook_slot` 表达插槽。组件可以同时提供两者，运行时连接必须区分组件实例。
- 从根组件进入业务执行；每个组件决定如何调用自己插槽中的连接，如何传递结果、处理失败和终止。
- 顺序、并行、选择、循环由相应控制组件提供。core 不通过一次通用遍历决定所有组件的执行行为。
- 登记成功、声明被接收、实例已连接、实际调用是不同阶段。ID、发现顺序和目录表格顺序不自动成为业务执行顺序。
- 插槽接收方判断兼容性；无需以 schema 相同作为全局条件，也不要求每个内部函数都拥有公共 ID。
- 实际依赖由装配表达，不从隐藏的 ctx 读写关系自动推断。
- 默认装配先服务实际 bot 场景，不提前冻结完整装配语言、任意执行图或通用流程引擎。

### 2.2 用户补充的思考：作为背景理解

用户在进入 M2 前分享了与另一 AI 的讨论，并明确说明：上下文不完整，**不要直接当作要求**。

该段思考的核心是：hook 更像 slot；插件可以接入插头，也可以向其他插件暴露能力；组件像插线板一样组合成树形结构。普通顺序组合可能表现得像前序遍历，但特殊控制组件应真正拥有并行、选择和循环的控制权。用户认可连接式组合相对代码紧耦合的价值，也意识到其中可能产生隐式依赖，希望通过装配和运行控制改善。

这段思考帮助解释已有设计方向，但不授权立即实现所有控制组件、依赖推断器或图优化算法。

### 2.3 助手提出的分析：尚非用户确认的新增约束

以下是讨论中给出的建议，应在具体实现时检验，不能伪装成已经冻结的协议：

- 插件是能力提供和装配单位，组件实例更适合作为运行结构节点。
- 树可以描述拥有关系或调用层级；共享服务可能使静态连接成为图，不必强制所有关系都是严格树。
- 循环组件可以重复调用同一连接，不一定需要在结构中创建环。
- 调用关系、资源所有权和生命周期依赖应分别考虑；调用共享服务不意味着调用者拥有关闭它的权力。
- 装配算法可以检查已表达的依赖，不能可靠补齐所有隐藏依赖。
- 接口除了参数类型，还可能涉及可重入、并发、重复调用、取消和失败语义；只补当前组合真正需要的约定。

M2 应用一个小而完整的 bot 验证这些想法，而不是先建设一套覆盖所有未来场景的框架。

## 3. 当前可复用的实现

### 3.1 core

源码目录：[aurora_core](../packages/aurora_core/src/aurora_core)。

| 能力 | 当前接口与约束 |
| --- | --- |
| 公共身份与总表 | `Id`、`RegistryEntry`、`DefinitionRegistry`；同一作用域 ID 唯一，批量登记原子检查，替换须显式进行 |
| 插件发现 | `Plugin`、`load_plugins`、`register_plugins`；entry point group 为 `aurorabot.plugins`，外部入口只按显式选择启用，必需依赖须同时选中 |
| 声明接收 | `inspect_admissions`；缺席可选 CLI/API 接收方保留声明并告警，不阻断插件其余能力 |
| 声明装饰器 | `@operation`、`@hook_handler`、`entry_from`；只附加声明，登记与连接由装配显式完成 |
| ctx | `Context`、`StateKey`、`install_context`；地址为完整状态 ID 加业务定位，读写复制，set 整项替换，每次成功 set 都通知 |
| 订阅 | ctx 订阅后续变更；EventBus 提供同步进程内发布订阅，监听器失败不撤销已提交状态 |
| 持久化 | `ContextPersistence` 与 `JsonSnapshotStore`；默认保存全部 ctx 状态，严格 JSON，临时文件写完后替换正式快照，后台合并写入 |
| 存储 | `StorageService`；宿主显式传入数据目录，提供框架 SQLite JSON KV、ctx 快照路径及插件目录 |
| 实例连接 | `HookConnections.connect` 显式给出两端 ID、实例标识及可选绑定 callable；排序为 priority 从小到大，同值保持连接顺序 |
| 单次调用 | `invoke_callable`、`invoke_operation`、`HookConnections.invoke`；同步在宿主线程运行，异步结果等待，取消向调用传播 |
| 生命周期 | `Lifecycle`、`LifecycleComponent`；按显式依赖 prepare/start，依赖者先停止，最后由宿主保证 flush |

注意：

- ctx 保存的是状态数据，不是函数、服务实例、连接或任务。模型配置的可恢复描述与实际 ModelClient 对象必须分开。
- ctx 访问限宿主线程；同线程并发协程中的单次修改有顺序，读改写组合不是事务。
- 生命周期恢复快照后执行 `configure`，再执行组件 prepare/start；配置所需的状态定义应在恢复前登记。
- `Lifecycle.run` 跟踪通过它接收的调用。组件自行创建的任务须由组件 stop 收束。
- 关闭顺序：停止入口 → 等待或取消在途调用 → 组件最后写入并结束来源 → 最终 flush → 释放存储和 ctx。
- 失败不得假报成功；停止或落盘失败保留可重试资源。协程超时不能抢占同步阻塞函数。
- 路由包装器中的 target、registry、identity 等参数已采用仅限位置参数，业务可使用同名关键字参数。
- 不要为 ReAct 循环、工具流程或模型选择给 core 增加业务特例。

### 3.2 CLI

源码目录：[aurora_cli](../packages/aurora_cli/src/aurora_cli)。

- `main` 负责进程入口与错误码；`commander` 负责发现、解析后分派；`host` 负责运行期装配。
- `declarations` 定义命令描述和接收规则；`execution` 统一调用执行绑定；`parsing` 处理 argv；`presentation` 提供目录和分组帮助。
- 内置 `commands/` 的直接子包导出无参数 `plugin()`，返回 core `Plugin`，宿主自动发现。新增命令无需修改中央白名单或按具体 ID 分派的分支。
- 命令绑定 `operation` 或 `executor`，两者择一。operation 运行于宿主并默认输出 JSON；executor 可以自定义输出，支持同步或异步，通过 `runtime` 声明是否需要宿主。
- `CommandContext` 提供 root、output、registry 与已接收命令目录；`assembly_argument` 声明由宿主消费的装配选择参数。
- 当前装配入口是同步工厂，以关键字接收 registry、ctx、hooks、storage，返回 `LifecycleComponent` 可迭代对象；工厂负责连接，资源初始化放在 prepare/start。这是现有 CLI 宿主约定，不等于已冻结所有 bot 装配格式。
- bot 可用 core 的普通登记项声明 CLI 命令，不能为使用 CLI 的辅助类型而建立 bot 对 CLI 实现的硬依赖。
- `passthrough` 为显式启用的原样参数透传；保留 argv 列表和分隔符，不拼接 shell 字符串。具体语义见当前 parsing 与测试。
- 当前命令包含 about、check、donk、ctx、help、run、id/list；`-v/--version` 读取已安装 CLI 版本并快速退出。
- `id list` 展示启动装配前已登记的总表，不含 prepare/start 中动态登记的定义；它不启动宿主。
- CLI 当前只操作本进程宿主。另起一个 `cancel` 进程不能凭共享数据目录取消已有进程中的任务；M2 的取消入口必须按实际进程关系设计。
- about 和帮助表格直接使用 Rich `box.SIMPLE`，无外框、不隔行变暗；不恢复 `utils.table` 自绘层。

M2.7 特别注意：operation 的通用 JSON 输出不自动变成流式对话 UI。需设计 CLI 如何消费增量并处理取消，同时维持 bot 无 CLI/API 实现依赖，以及命令自包含扩展能力。

### 3.3 验收基线

M1.8 验收时完整检查通过：196 项 Python 测试、9 项工具链测试、Pyright basic、格式/lint、TypeScript 与工作区入口检查。

关键证据：

- [关闭顺序集成测试](../tests/e2e/test_m1_shutdown.py)：磁盘 I/O 阻塞期间接收 20 个在途调用，记录 22 次状态变化与最终资源关闭顺序，恢复全部业务地址。
- [真实 CLI 进程测试](../tests/e2e/test_m1_cli_process.py)：watch、SIGINT、最后写入、下一进程恢复；停止和落盘故障均非零退出。
- [生命周期与持久化集成测试](../tests/e2e/test_lifecycle_persistence.py)：可选处理器禁用、落盘失败重试、损坏快照保护。
- [命令扩展集成测试](../tests/e2e/test_cli_extensions.py)：命令包新增/移除、外部入口显式启用、运行期执行器与状态恢复。
- [独立计数器](../examples/core_counter/main.py)：仅安装本次 core wheel 的环境中，两次执行输出 2 和 5；CLI、bot、API、模型适配包均不可导入。

M1.8 后还有调用参数、透传和 ID 列表提交；196 是该里程碑的历史验收数字，不是对当前测试总数的新声明。本次交接整理未重跑全套测试。

## 4. M2 任务拆分与建议交付顺序

以下沿用总体计划的任务编号；文件名是建议落点，按实际职责调整，不为目录齐全创建空实现。

| 任务 | 交付内容 | 可验证出口 |
| --- | --- | --- |
| M2.1 模型协议与假实现 | model_adapter 的请求、响应、流式 chunk、工具调用、能力声明、ModelClient 与工厂协议；确定性假模型 | 文本、流式、工具请求、失败、取消均可离线驱动；公共接口不含 SDK 类型 |
| M2.2 默认装配与绑定 | bot 默认 assembly、逻辑模型角色、实例创建、连接及资源所有权；可恢复绑定描述 | 同一定义可产生不同实例；先恢复配置再创建运行对象；无 CLI/API 也能启动 |
| M2.3 LiteLLM 适配 | 单独适配器负责 SDK 转换、增量工具参数组装、错误与取消映射、连接释放 | 模拟 SDK 响应完成边界测试；能力不足明确拒绝或按显式配置降级 |
| M2.4 对话运行与状态 | 进程内 send/cancel、会话和运行身份、状态机、事件与重启处理 | started 后恰有一个终态；完成、失败、取消可区分；重复请求与取消竞态有明确定义 |
| M2.5 默认 ReAct 控制 | bot 控制组件、提示词资源、prepare/infer/act/observe/finish/error 插槽与默认处理器 | 根组件控制调用；无工具时结束，有工具时再次推理；轮次限制可解释；控制逻辑不进入 core |
| M2.6 基本工具路径 | 工具登记、参数校验、before_call/after_call、结果/失败表达；确定性本地工具 | 未知工具和非法参数不执行；工具结果进入下一轮；失败、超时、取消不悬挂 |
| M2.7 CLI 对话接入 | bot 命令声明、CLI 流式展示与取消、进程内调用保留 | CLI 可显示增量和唯一终态；中断完成清理；CLI 缺席不影响 bot 进程内运行 |
| M2.8 最小 bot 验收 | 模型/插槽契约测试、默认装配、工具循环、取消、重启 | 无网络与密钥即可验收假模型；可用配置下另做真实模型冒烟，分开报告结果 |

建议小步推进：

1. 首先交付 M2.1：围绕“返回文本”和“请求一个工具”定义最小协议，再加入流式与取消验证；不先实现所有供应商参数。
2. M2.2 使用假模型打通装配与生命周期，证明服务注入、同定义多实例和收尾可用。
3. M2.3 可与假模型驱动的 M2.4–M2.6 路径分开推进；真实供应商连接不应阻塞离线开发。整个 M2 验收仍包含适配器。
4. M2.4 先明确运行语义，再实现 M2.5 的控制组件和 M2.6 的工具往返。插槽表只是接入位置，不能代替实际控制组件。
5. 业务行为稳定后接 CLI，避免让 CLI 输出和参数格式决定底层对话协议。

首次演示目标：输入 → 模型请求确定性工具 → 执行并记录观察 → 再次推理 → 输出最终结果；另演示一次流式取消和一次工具失败。

## 5. 实现前或实现中必须收敛的决策

| 决策 | 时点 | 需要明确的问题 |
| --- | --- | --- |
| D07 模型边界 | M2.1，M2.3 复核 | async 接口形态、文本与工具增量的关联、结束标记、能力检查、错误映射、调用取消和服务关闭责任 |
| D03 绑定恢复 | M2.2 | ctx 保存哪些配置和引用，实例由谁持有，恢复如何重建；凭证如何注入，避免无意纳入完整状态快照 |
| D05 装配格式 | M2.2 | 根组件选择、组件实例标识、连接与注入的最小表示；调用关系、共享服务和生命周期依赖如何表达 |
| D06 资源收尾 | M2.2–M2.6 | 模型流、HTTP 客户端、工具任务由谁关闭；组件自行创建的任务如何等待或取消 |
| D10 运行语义 | M2.4 | send 的返回与等待语义、忙碌会话策略、重复请求、run ID、取消竞态、终态提交、遗留进行中运行的恢复 |
| CLI 流式接入 | M2.7 | 谁订阅增量、谁打印、谁处理 Ctrl+C；cancel 如何作用于同一宿主；命令如何避免导入 CLI 实现 |

上述问题没有全部确定。可以先开展不依赖它们的工作；影响公共接口或明显存在多种产品语义时及时询问用户，不把候选默认值写成用户已批准的要求。

尤其不能直接假定：

- 所有 ctx 写入都触发业务执行，或写入某个状态天然等同于 send。
- 事件订阅会自动提供历史回放、远程传输或可靠投递。
- 已登记的 conversation/send、cancel 或 HTTP 端点规划强制决定未来 TUI/Panel 交互。
- 重启后可以透明续跑模型调用或工具执行；消息和配置恢复与运行恢复是不同问题。
- 共用 ModelClient 意味着任意并发安全，或所有组件均有权关闭该实例。
- 凭证、服务实例可以直接放进 ctx；当前持久化语义是保存全部状态数据。

推荐先使用明确的进程内调用关系验证执行，再按实际需求设计状态与事件通知；这属于实施建议，不是已经确认的完整提交协议。

## 6. 公共身份与包边界

沿用现有目录中的规划身份，不为同一能力新造同义 ID。主要入口：

- model_adapter：adapters 注册表、model_client 服务、litellm 适配器、model_request/response/chunk/capabilities、state/config 与 state/bindings。
- bot：assemblies/default、operations/conversation/send 与 cancel、commands/chat 与 cancel、prompts/soul 与 react。
- ReAct：react/prepare、infer、act、observe、finish、error；默认 handlers/react/* 由控制组件接入并调用。
- 工具：registries/tools、tools/before_call 与 after_call、tool_definition/call/result。
- 状态和事件：state/config、messages、run；run/started、completed、cancelled、failed 和 message/delta。

完整 namespace、kind 与路径以 [ID 目录](aurorabot-id-catalog-v0.2.2.md) 为准。公共 ID 表示定义，模型名、会话和 run 等业务定位不能通过不断修改定义 ID 来表达。

依赖方向保持：core ← model_adapter ← bot；bot 也直接使用 core。CLI/API 通过公开接入方式参与装配，不能成为 bot 的必装实现依赖。LiteLLM SDK 类型只停留在适配器边界。

M2 暂不承接 M3 的 HTTP/WS、远程 client/TUI，也不承接 M4 的多模型编排、agent 通信或 MCP。并行、选择等控制组件按最小 bot 的实际需要引入。

## 7. 工作方式与命令

- 主要注释、docstring 和提交信息使用中文；小步提交，提交信息以动词开头。
- 修改 README.md 或 AGENTS.md 前必须征得用户确认；普通变更说明放入 docs/CHAGELOG.md。本交接文件是用户明确指定的独立文档。
- scripts/ 首选 Node/TypeScript；Python 类型检查采用 Pyright basic。编辑器可能与命令行类型桩有所不同，输出流等可空对象要真实校验，不用忽略诊断掩盖问题。
- PyPI 统一安装包为 aurorabot-ai，依赖各功能包。当前 donk 暂统一更新 Python 工作区版本和内部依赖；未来拆仓策略未冻结。
- 用户希望命令自包含、插件可插拔；不要把新命令的 ID 特例加回 commander 或 host。
- 旧项目只可参考文件组织和用户可见效果，不借用其旧架构与实现来覆盖当前设计。
- 安装和检查：

```powershell
uv sync --all-packages
pnpm install --frozen-lockfile
uv run aurora check
pnpm typecheck:python
uv run pytest tests/e2e/test_m1_shutdown.py tests/e2e/test_m1_cli_process.py
uv run aurora id list
```

针对故障用对应工具的精准命令；check 不做任意参数透传。M2 提交前保留 M1 核心和 CLI 回归检查，新增测试聚焦模型协议、控制行为与可观察结果。

真实模型验证须在可用配置下进行，不索要或输出明文密钥；没有可用连接时如实记录真实冒烟未执行，不能将模拟 SDK 测试当作真实连接成功。
