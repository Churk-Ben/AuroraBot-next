# AuroraBot 公共 ID 目录 v0.2.2

版本：v0.2.2  
日期：2026-10-29  
对应主文档：`aurorabot-design-v0.2.2.md`。  
范围：沿用 v0.2.1 的全部公共 ID 与 kind，同步 v0.2.2 的统一登记、按需接口描述、接收方兼容判断和 client ctx 访问。覆盖十个包和应用。目录是规划基线，不表示对象已经实现、连接或启用，也不表示接口字段已经冻结。

## 1. 使用规则

- 格式为 `<namespace>:<domain>/<local_path>`，跨组件引用使用完整 ID，kind 显式说明对象类型。
- 一个 ID 在同一环境、同一登记作用域中对应一个公开定义；具体实例和业务数据使用必要的实例、会话、运行、agent 标识区分，不建立内部命名空间访问隔离。
- Python core 维护统一的 `Id → RegistryEntry` 内存表。登记项指向定义，状态值、事件实例和具体服务实例不与定义身份混为一项。
- 注册表可以是总表上的分类视图及接入逻辑。存在于总表不意味着接收方存在、连接成功或对象已执行；前端和静态资源在各自环境管理。
- `register_to` 表示接收方；`slot` 表示插槽目标；`operation` 表示一条调用绑定。组件实例连接另行表达，不由 ID 路径、同名或表格顺序推导。
- 插头与插槽通常各自描述接口，由插槽方判断兼容性。schema 可选；少量特殊连接可依双方约定和运行时行为，不要求新增正式契约 ID。
- 描述不同但兼容时可以连接，按需要告警；缺少接收方时保留未连接声明并 warning，不因可选 CLI/API 缺席阻断整个插件加载。
- 公共覆盖、实现选择和处理器替换由显式装配表达，不依赖加载顺序。
- client 实现统一 ctx 接口及既有 ctx 操作 ID 入口，不创建同义动作 ID；插件在进程内访问 ctx，TUI/Panel 通过 client 访问同一后端。
- 界面不承担后端插件装配；既有 send/cancel operation 和 conversation 端点不是本版规定的界面必经入口。消息提交与取消如何关联执行，另行讨论。
- 本目录不要求所有私有函数或局部组件登记公共 ID，也不要求各阶段一次性实现全部规划。

## 2. 命名空间总表

| 包或应用 | 命名空间 | 解析环境 |
| --- | --- | --- |
| `aurora_core` | `org.aurora.core` | Python 运行时 |
| `aurora_cli` | `org.aurora.cli` | Python 运行时 |
| `aurora_bot` | `org.aurora.bot` | Python 运行时 |
| `aurora_api` | `org.aurora.api` | Python 运行时 |
| `aurora_model_adapter` | `org.aurora.model_adapter` | Python 运行时 |
| `aurora_client` | `org.aurora.client` | TS 客户端 |
| `aurora_tui` | `org.aurora.tui` | TUI 本地 |
| `aurora_panel` | `org.aurora.panel` | WebUI 本地 |
| `docsite` | `org.aurora.docsite` | 文档构建环境 |
| `landing` | `org.aurora.landing` | 落地页构建环境 |

## 3. aurora_core

### 3.1 注册目标

以下是逻辑注册表，可以基于 core 统一内存表实现分类索引与专属接入规则，不要求重复保存所有对象。宿主直接引导建立总表、注册表目录和所需基础定义，随后登记其他注册表。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.core:registries/registries` | `registry` | 登记其他注册表的描述与接入规则 |
| `org.aurora.core:registries/plugins` | `registry` | 插件描述与能力声明 |
| `org.aurora.core:registries/operations` | `registry` | 可调用操作 |
| `org.aurora.core:registries/hook_slots` | `registry` | hook 插槽定义 |
| `org.aurora.core:registries/hook_handlers` | `registry` | hook 处理器定义及绑定 |
| `org.aurora.core:registries/resources` | `registry` | 静态或可加载资源 |
| `org.aurora.core:registries/services` | `registry` | 可注入服务的描述与绑定 |
| `org.aurora.core:registries/schemas` | `registry` | 数据契约 |
| `org.aurora.core:registries/state_keys` | `registry` | ctx 状态项定义 |
| `org.aurora.core:registries/events` | `registry` | 事件类型定义 |

注册表登记定义，不保存所有状态值或历史事件实例。`RegistryEntry` 是内部登记项名称，不是本版新增的公共 ID。

登记关系如下；目录中列出的注册表只有在提供方实际安装并启用时才存在。

| 注册表 | 登记目标／建立方式 |
| --- | --- |
| `org.aurora.core:registries/registries` | 宿主直接建立，自身描述是否列入目录由实现决定 |
| 本节其余 core 注册表 | `org.aurora.core:registries/registries` |
| `org.aurora.cli:registries/commands` | `org.aurora.core:registries/registries` |
| `org.aurora.model_adapter:registries/adapters` | `org.aurora.core:registries/registries` |
| `org.aurora.bot:registries/tools` | `org.aurora.core:registries/registries` |
| `org.aurora.bot:registries/agents` | `org.aurora.core:registries/registries` |
| `org.aurora.bot:registries/mcp_servers` | `org.aurora.core:registries/registries` |
| `org.aurora.api:registries/endpoints` | `org.aurora.core:registries/registries` |

resources 可以接收 `resource`、`assembly`、`contract` 等约定的 kind，保留原 kind，由接收方选择必要的加载和校验方式。提示词、主题等内容不必为登记而建立完整子类型体系。

### 3.2 操作、生命周期与基础契约

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.core:operations/ctx/get` | `operation` | 读取 ctx |
| `org.aurora.core:operations/ctx/set` | `operation` | 写入 ctx |
| `org.aurora.core:operations/ctx/delete` | `operation` | 删除 ctx 状态 |
| `org.aurora.core:operations/ctx/list` | `operation` | 枚举共享 ctx 状态项；API 对外暴露另行配置 |
| `org.aurora.core:operations/ctx/subscribe` | `operation` | 订阅 ctx 变化 |
| `org.aurora.core:operations/ctx/unsubscribe` | `operation` | 取消订阅 |
| `org.aurora.core:lifecycle/prepare` | `hook_slot` | 完成预配置、启动前装配 |
| `org.aurora.core:lifecycle/start` | `hook_slot` | 启动已装配能力 |
| `org.aurora.core:lifecycle/stop` | `hook_slot` | 停止并释放能力 |
| `org.aurora.core:events/ctx/changed` | `event` | ctx 状态发生变化 |
| `org.aurora.core:events/hook/failed` | `event` | hook 处理器执行失败 |
| `org.aurora.core:schemas/plugin_manifest` | `schema` | 插件身份、依赖与注册项；对外暴露需求单独表达 |
| `org.aurora.core:schemas/registration` | `schema` | 注册项的通用结构 |
| `org.aurora.core:schemas/ctx_access` | `schema` | ctx 访问动作、目标与业务定位描述；取消内部命名空间授权含义，具体字段待细化 |
| `org.aurora.core:schemas/hook_slot` | `schema` | 按需使用的插槽描述：输入输出、调度及错误策略 |

ctx 原语由 core 实现。Python 插件通过进程内接口访问，CLI 使用对应命令，client 实现携带上述同一 ID 的 ctx 访问入口，TUI/Panel 使用 client。各语言实现共享语义，不要求前端解析 Python 对象或插件安装 TS 包。

所有命名空间通过显式接口访问共享 ctx，需要恢复的数据异步落盘。退出时停止新工作，让组件收尾、结束最后状态写入，保持存储可用直至最终落盘完成，再释放剩余资源。宿主负责这一顺序，不要求为每个内置收尾动作增加公共 handler ID。生命周期插槽不代表 core 内置 bot 能力。

`ctx_access` 沿用历史规划 ID，仅描述访问动作、目标与业务定位，不表示内部授权。保留 ID 不表示旧授权字段继续适用，也不要求所有 ctx 动作共享这一份结构。

set 更新方式、list 内容、订阅句柄等在实现对应原语时明确并记录当前所需行为，本版不提前冻结。数据描述可以使用 Python 类型、签名或 schema；不批量为每种请求／响应新增公共 ID。目录、存储服务及流程控制插件继续按实际需要确定；局部控制组件可先内部装配，供外部引用时再登记公共 ID。

## 4. aurora_cli

| ID | kind | 用途或映射 |
| --- | --- | --- |
| `org.aurora.cli:registries/commands` | `registry` | 接收内置及第三方命令 |
| `org.aurora.cli:schemas/command` | `schema` | 参数、帮助信息、执行目标 |
| `org.aurora.cli:commands/help` | `command` | 展示命令帮助 |
| `org.aurora.cli:commands/ctx/get` | `command` | 调用 `org.aurora.core:operations/ctx/get` |
| `org.aurora.cli:commands/ctx/set` | `command` | 调用 `org.aurora.core:operations/ctx/set` |
| `org.aurora.cli:commands/ctx/delete` | `command` | 调用 `org.aurora.core:operations/ctx/delete` |
| `org.aurora.cli:commands/ctx/list` | `command` | 调用 `org.aurora.core:operations/ctx/list` |
| `org.aurora.cli:commands/ctx/watch` | `command` | 订阅并展示 ctx 变化，退出时取消订阅 |
| `org.aurora.cli:commands/run` | `command` | 应用预配置，启动选定装配 |
| `org.aurora.cli:state/config` | `state_key` | CLI 参数解析后的配置 |

命令由 CLI 接收并登记。未安装或未启用 CLI 时，指向命令表的声明保留为未连接并 warning，不阻断其他能力。`ctx/watch` 组合订阅、渲染与取消订阅，不要求与操作一一对应。

## 5. aurora_model_adapter

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.model_adapter:registries/adapters` | `registry` | 接收模型适配器工厂 |
| `org.aurora.model_adapter:services/model_client` | `service` | 上层消费的统一 ModelClient 契约 |
| `org.aurora.model_adapter:adapters/litellm` | `adapter` | 基于 LiteLLM 创建 ModelClient |
| `org.aurora.model_adapter:schemas/model_request` | `schema` | 统一模型请求 |
| `org.aurora.model_adapter:schemas/model_response` | `schema` | 统一模型响应 |
| `org.aurora.model_adapter:schemas/model_chunk` | `schema` | 统一流式响应片段 |
| `org.aurora.model_adapter:schemas/model_capabilities` | `schema` | 流式、工具调用等能力声明 |
| `org.aurora.model_adapter:state/config` | `state_key` | 适配器选择与连接配置 |
| `org.aurora.model_adapter:state/bindings` | `state_key` | 逻辑模型角色与服务实例的绑定信息；具体托管形式待讨论 |

具体适配器由 adapters 注册表接收。bot 使用 ModelClient，不直接引用 LiteLLM。工厂接口可通过 Python 类型和签名描述，配置结构按需要使用 schema，不强制新增独立工厂 schema ID。

ctx 内部跨命名空间共享。需要恢复的数据落盘，实际服务和连接不直接序列化落盘；绑定保存何种引用以及运行时对象如何托管继续讨论。client 只获取准备提供给界面的数据，凭证不随通用 ctx 接口自动导出；本版不建立完整状态分类或秘密管理系统。

## 6. aurora_bot

### 6.1 装配、对话与提示词

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.bot:assemblies/default` | `assembly` | 默认插件、资源和服务绑定清单 |
| `org.aurora.bot:operations/conversation/send` | `operation` | 提交一轮用户输入 |
| `org.aurora.bot:operations/conversation/cancel` | `operation` | 请求取消指定运行 |
| `org.aurora.bot:commands/chat` | `command` | CLI 对话入口 |
| `org.aurora.bot:commands/cancel` | `command` | CLI 取消入口 |
| `org.aurora.bot:prompts/soul` | `resource` | 基础身份与行为提示词 |
| `org.aurora.bot:prompts/react` | `resource` | 默认 ReAct 提示词模板 |
| `org.aurora.bot:schemas/message` | `schema` | 统一对话消息 |
| `org.aurora.bot:schemas/run_input` | `schema` | 一次运行的输入 |
| `org.aurora.bot:schemas/run_result` | `schema` | 一次运行的结果 |

bot 命令声明的目标是 `org.aurora.cli:registries/commands`，分别绑定本包 send 和 cancel；它们在 bot 命名空间声明，不需要导入 CLI 实现。CLI 缺席时保留未连接状态并告警。

这些是保留的规划入口，不规定 TUI/Panel 必须经它们交互。消息提交与取消如何关联 bot 执行不在本版展开，既不预设输入状态触发，也不以保留 operation ID 推导通用远端调用。

装配清单是一种可加载描述，保留 `assembly` kind，可由 resources 接收。M2 先确定默认装配实际需要的实例与连接格式，不要求提前增加独立 assembly schema ID。

### 6.2 ReAct 插槽

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.bot:react/prepare` | `hook_slot` | 准备上下文与模型输入 |
| `org.aurora.bot:react/infer` | `hook_slot` | 执行模型推理 |
| `org.aurora.bot:react/act` | `hook_slot` | 执行模型请求的工具动作 |
| `org.aurora.bot:react/observe` | `hook_slot` | 接纳动作结果，更新本轮上下文 |
| `org.aurora.bot:react/finish` | `hook_slot` | 收束运行并生成结果 |
| `org.aurora.bot:react/error` | `hook_slot` | 处理运行失败 |

插槽登记到 `org.aurora.core:registries/hook_slots`。表格顺序不构成可执行流程，循环与终止条件由 bot 装配的控制组件实现；顺序、并行、选择和循环由插件提供。双方按需描述接口，由插槽提供方判断兼容性；描述不同但兼容或没有正式 schema 的特殊连接均可成立。

### 6.3 ReAct 默认处理器

以下对象的 kind 均为 `hook_handler`，登记到 `org.aurora.core:registries/hook_handlers`，通过 `slot` 连接。它们属于默认插件实现，可以与 bot 装配同包发布；命名空间不强制物理目录或发布包一一对应。

| ID | 接入插槽 | 职责 |
| --- | --- | --- |
| `org.aurora.bot:handlers/react/build_prompt` | `org.aurora.bot:react/prepare` | 构建模型输入 |
| `org.aurora.bot:handlers/react/call_model` | `org.aurora.bot:react/infer` | 调用注入的模型服务 |
| `org.aurora.bot:handlers/react/execute_tools` | `org.aurora.bot:react/act` | 执行工具请求 |
| `org.aurora.bot:handlers/react/record_observation` | `org.aurora.bot:react/observe` | 记录观察结果 |
| `org.aurora.bot:handlers/react/finalize` | `org.aurora.bot:react/finish` | 收束结果 |
| `org.aurora.bot:handlers/react/report_error` | `org.aurora.bot:react/error` | 报告运行失败 |

### 6.4 工具、多模型与 MCP

工具能力按最小 bot 路径逐步接入；多模型、agent 通信和 MCP 属于后续扩展。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.bot:registries/tools` | `registry` | 可供 bot 调用的工具 |
| `org.aurora.bot:tools/before_call` | `hook_slot` | 工具调用前的校验与扩展 |
| `org.aurora.bot:tools/after_call` | `hook_slot` | 工具结果处理 |
| `org.aurora.bot:schemas/tool_definition` | `schema` | 工具名称、参数和结果契约 |
| `org.aurora.bot:schemas/tool_call` | `schema` | 具体工具调用请求 |
| `org.aurora.bot:schemas/tool_result` | `schema` | 工具调用结果 |
| `org.aurora.bot:registries/agents` | `registry` | 多模型参与者定义 |
| `org.aurora.bot:multi_model/select` | `hook_slot` | 选择参与推理的模型或 agent |
| `org.aurora.bot:multi_model/aggregate` | `hook_slot` | 汇总并行推理结果 |
| `org.aurora.bot:operations/agents/send` | `operation` | 向指定 agent 发送消息 |
| `org.aurora.bot:agents/on_message` | `hook_slot` | 接收并处理 agent 消息 |
| `org.aurora.bot:schemas/agent_message` | `schema` | agent 间消息信封 |
| `org.aurora.bot:registries/mcp_servers` | `registry` | MCP 服务装配描述 |
| `org.aurora.bot:services/mcp_runtime` | `service` | MCP 连接与服务生命周期 |
| `org.aurora.bot:schemas/mcp_server` | `schema` | MCP 服务配置与能力描述 |

### 6.5 状态与事件

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.bot:state/config` | `state_key` | bot 配置 |
| `org.aurora.bot:state/messages` | `state_key` | 当前会话的消息记录 |
| `org.aurora.bot:state/run` | `state_key` | 当前运行状态 |
| `org.aurora.bot:state/agents` | `state_key` | agent 运行状态 |
| `org.aurora.bot:events/run/started` | `event` | 运行开始 |
| `org.aurora.bot:events/run/completed` | `event` | 运行完成 |
| `org.aurora.bot:events/run/cancelled` | `event` | 运行取消 |
| `org.aurora.bot:events/run/failed` | `event` | 运行失败 |
| `org.aurora.bot:events/message/delta` | `event` | 对话输出增量 |
| `org.aurora.bot:events/tool/completed` | `event` | 工具调用完成 |

状态定义与具体值分开；事件类型与每次发布的事件实例分开。一次运行的终态区分完成、取消与失败。

## 7. aurora_api

### 7.1 传输契约与基础端点

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.api:registries/endpoints` | `registry` | 接收实际需要的 HTTP/WS 端点 |
| `org.aurora.api:endpoints/ctx` | `endpoint` | 为 client 提供允许的 ctx 访问传输 |
| `org.aurora.api:endpoints/events` | `endpoint` | 为 client 提供需要的事件与订阅传输 |
| `org.aurora.api:schemas/request_envelope` | `schema` | 请求关联、目标作用域等传输信息 |
| `org.aurora.api:schemas/event_envelope` | `schema` | 事件 ID、来源、序号与载荷 |
| `org.aurora.api:schemas/error` | `schema` | 对外错误结构 |
| `org.aurora.api:contracts/openapi` | `contract` | HTTP API 权威描述 |
| `org.aurora.api:contracts/ws_events` | `contract` | WS 消息与事件契约 |
| `org.aurora.api:state/config` | `state_key` | 监听地址、传输及暴露策略 |

端点由 endpoints 注册表接收。API 是 client 连接后端的传输实现，不是插件接入总线，也不要求实现任意 operation 的远端分发器。URL、HTTP 方法和 WS 消息不从 ID 路径推导；一个端点涉及多个动作时，由其实现描述各条绑定，不强制新增端点 schema ID。

core 负责进程内事件和 ctx 变化订阅，client 封装界面所需订阅，API 承担传输。不因使用 WS 就新增通用订阅 operation。取消、断线和重连行为在实现时明确，本版不承诺历史补发。

`contract` 表示可加载的生成描述，保留自己的 kind，可由 resources 承载。只导出实际需要、可传输的数据；不全量导出 Python 登记表或 ctx。

### 7.2 bot 提供的 API 扩展

| ID | kind | 注册目标与操作绑定 |
| --- | --- | --- |
| `org.aurora.bot:endpoints/conversation` | `endpoint` | 登记到 `org.aurora.api:registries/endpoints`，绑定 bot 的 conversation/send 与 conversation/cancel 操作 |

此 ID 属于 bot 命名空间，是保留的规划入口；API 缺席时声明保留为未连接并 warning，不阻断其他 bot 能力。保留此端点不规定 TUI/Panel 经其提交消息或取消，具体交互机制另行讨论。

API 传输实际需要的 bot/core 事件时保留原事件类型 ID，可添加传输信封，不另建同义业务事件身份。

## 8. aurora_client

以下对象在 TS 客户端环境解析；本地状态不自动成为 Python ctx 状态。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.client:services/api_client` | `service` | 共享 ctx 访问入口、对应 ID 支持与后端连接 |
| `org.aurora.client:services/event_stream` | `service` | 共享事件连接与订阅管理 |
| `org.aurora.client:state/connection` | `state_key` | 连接与重连状态 |
| `org.aurora.client:state/subscriptions` | `state_key` | 当前订阅记录 |
| `org.aurora.client:events/connection/changed` | `event` | 通知界面连接变化 |
| `org.aurora.client:contracts/generated` | `contract` | 从实际维护的后端公开描述按需生成的类型及 ID 常量 |

client 实现 ctx get/set/delete/list/subscribe/unsubscribe 等访问入口，复用第 3.2 节现有 ctx 操作 ID，不另建同义身份。这里是客户端接口实现，不是把 Python 对象导入 TS，也不是任意后端 operation 的通用调用器。

插件的进程内接口与 client 的 TS 实现共享 ctx 语义，实际状态操作在 core 完成。只生成真实使用的数据和 ID；保留的 bot operation 名称不要求前端使用，也不要求生成全部后端定义。

## 9. aurora_tui

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.tui:views/chat` | `view` | 对话界面 |
| `org.aurora.tui:views/config` | `view` | 配置界面 |
| `org.aurora.tui:views/ctx` | `view` | ctx 查看与操作 |
| `org.aurora.tui:actions/message/submit` | `ui_action` | 界面提交动作，经 client 交互；与执行的关联机制待讨论 |
| `org.aurora.tui:actions/run/cancel` | `ui_action` | 界面取消动作；具体交互机制待讨论 |
| `org.aurora.tui:resources/keymap/default` | `resource` | 默认按键映射 |
| `org.aurora.tui:state/preferences` | `state_key` | 终端界面偏好 |

## 10. aurora_panel

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.panel:views/chat` | `view` | Web 对话界面 |
| `org.aurora.panel:views/config` | `view` | Web 配置界面 |
| `org.aurora.panel:views/ctx` | `view` | Web ctx 查看与操作 |
| `org.aurora.panel:actions/message/submit` | `ui_action` | 界面提交动作，经 client 交互；与执行的关联机制待讨论 |
| `org.aurora.panel:actions/run/cancel` | `ui_action` | 界面取消动作；具体交互机制待讨论 |
| `org.aurora.panel:resources/theme/default` | `resource` | 默认界面主题 |
| `org.aurora.panel:state/preferences` | `state_key` | Web 界面偏好 |

TUI 与 Panel 使用同一个 client ctx interface，各自处理输入、反馈和本地状态，不参与后端插件装配。视图与动作在本地解析；本版不规定提交／取消动作绑定 bot operation 或端点，也不规定 ctx 写入如何触发执行。

## 11. docsite

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.docsite:pages/index` | `page` | 文档首页 |
| `org.aurora.docsite:pages/getting_started` | `page` | 入门文档 |
| `org.aurora.docsite:pages/architecture` | `page` | 架构说明 |
| `org.aurora.docsite:pages/plugins` | `page` | 插件开发说明 |
| `org.aurora.docsite:pages/reference/ids` | `page` | 公共 ID 目录 |
| `org.aurora.docsite:resources/navigation` | `resource` | 文档导航 |

## 12. landing

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.landing:pages/index` | `page` | 落地页首页 |
| `org.aurora.landing:resources/navigation` | `resource` | 落地页导航 |
| `org.aurora.landing:resources/brand` | `resource` | 品牌资源清单 |

静态页面的语言、文件位置和部署 URL 通过元数据或构建配置表达。`page` 是构建环境中的页面资源类型，不是 Python 运行时端点。

## 13. 关键引用关系

| 声明方 | 关系 | 目标 |
| --- | --- | --- |
| 各 Python 逻辑注册表 | 目录登记 | `org.aurora.core:registries/registries`；自举按第 3.1 节处理 |
| bot chat/cancel 命令 | `register_to` | `org.aurora.cli:registries/commands`；CLI 缺席时未连接并告警 |
| bot chat 命令 | 一条操作绑定 | `org.aurora.bot:operations/conversation/send` |
| bot cancel 命令 | 一条操作绑定 | `org.aurora.bot:operations/conversation/cancel` |
| bot 命令与 CLI 接收方 | 可使用的描述 | `org.aurora.cli:schemas/command`；不要求导入 CLI 实现 |
| bot conversation 端点 | `register_to` | `org.aurora.api:registries/endpoints`；API 缺席时未连接并告警 |
| bot conversation 端点 | 规划操作绑定 | bot conversation/send 与 conversation/cancel；不作为界面必经入口 |
| ReAct 默认处理器 | `register_to` | `org.aurora.core:registries/hook_handlers` |
| 提示词构建处理器 | `slot` | `org.aurora.bot:react/prepare` |
| 模型调用处理器 | 注入服务 | `org.aurora.model_adapter:services/model_client` |
| LiteLLM 适配器 | `register_to` | `org.aurora.model_adapter:registries/adapters` |
| ctx 传输端点与 client | 共用动作身份和语义 | 第 3.2 节的 core ctx 操作 ID |
| API 传输的事件 | 事件类型引用 | 原 bot/core 事件 ID |
| TUI/Panel 的 ctx 交互 | 共享客户端入口 | `org.aurora.client:services/api_client` |
| TUI/Panel 的订阅 | 连接与订阅支持 | `org.aurora.client:services/event_stream` |

界面动作到 bot 执行的关联不在本版建立具体绑定。ID 引用不等于代码导入、已连接或默认对外暴露。

## 14. 第三方声明示例

以下为扩展示例，不计入官方 ID 目录。

```yaml
id: dev.example.memory:handlers/inject_context
kind: hook_handler
register_to: org.aurora.core:registries/hook_handlers
slot: org.aurora.bot:react/prepare
```

```yaml
id: dev.example.models:adapters/private_gateway
kind: adapter
register_to: org.aurora.model_adapter:registries/adapters
```

示例只表达登记与连接关系，按实际需要补充提供者、加载入口和接口描述；schema 并非所有特殊连接的前置条件。双方描述不同仍可由接收方判断兼容，必要时告警。排序字段方向未定，示例不提供暗示规范的优先级数值。内部 ctx 共享，所有状态修改仍经显式接口。

## 15. 目录维护

- 新公共定义确定命名空间、kind、实际用途及登记环境；接口描述按需要维护，不强制独立 schema ID。
- 用途、输入输出或连接变化时同步文档和实际维护的接口；名称保留不等于字段或行为已经冻结。
- 内部局部组件可直接装配，确需外部引用时再登记公共 ID。
- client 对同一 ctx 动作沿用现有身份，不为语言或传输差异创建同义操作。
- 兼容与迁移围绕实际稳定的公共边界处理，不强制所有局部连接建立版本体系。
- `aurora_playground` 正式纳入包设计后再补充，本版不预占公共 ID。

## 16. v0.2.2 修订说明

- 沿用 v0.2.1 全部公共 ID 与 kind，不新增、删除或重命名定义。
- 同步 core 统一哈希表、登记项与逻辑注册表关系，并补充自举和跨包目录登记说明。
- 同步可选宿主缺席时 warning 与未连接处理，不因 CLI/API 缺席阻断整个插件。
- 明确双方按需描述接口，由插槽方判断兼容；特殊连接可没有正式 schema。
- client 实现统一 ctx 访问入口与现有 ID 支持；HTTP/WS 是传输，TUI/Panel 不参与后端插件装配。
- 保留 bot 操作与端点规划，但移除界面动作必须调用它们的表述；提交与取消的具体机制不在本版决定。
- 保留运行时对象与绑定管理的讨论空间，仅确定需要恢复的数据落盘及界面数据不全量导出。
- 同步逐步断开的退出顺序，最终落盘由宿主保证，不批量增加生命周期处理器 ID。

