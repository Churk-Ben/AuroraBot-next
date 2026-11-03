# AuroraBot 公共 ID 目录 v0.2.3

版本：v0.2.3
设计版本日期：2026-10-29；执行包拆分、M2 验收与文档基线对齐：2026-11-01。

对应主文档：[设计文档](aurorabot-design-v0.2.3.md)。

范围：第 6.1–6.3 节列出 control、agent 和 bot 的实际插件定义；第 6.5 节列出世界记录定义及来源/cadence 的规划归属，其他章节按各节标注区分。目录中的存在不代表对象已连接、启用或接口字段冻结。

## 1. 使用规则

- 格式为 `<namespace>:<domain>/<local_path>`，跨组件引用使用完整 ID，kind 显式说明对象类型。
- 一个 ID 在同一环境、同一登记作用域中对应一个公开定义；具体实例和业务数据使用必要的实例、会话、运行、agent 标识区分，不建立内部命名空间访问隔离。
- Python core 维护统一的 `Id → RegistryEntry` 内存表。登记项指向定义，状态值、事件实例和具体服务实例不与定义身份混为一项。
- `component` 表示组件类或局部执行函数的定义。control 通过 component_entries 显式声明其 `/execute` 插头和可选 `/children` 插槽；core 不从路径推断 kind 或运行时父子关系。
- bot 的 definition_id、instance_id、run_id、execution_id 分别表示定义、实例、业务运行和单次调用。`definition_id.instance_id` 只是展示引用，不是新的公共 ID；实例默认 UUID。
- 注册表可以是总表上的分类视图及接入逻辑。存在于总表不意味着接收方存在、连接成功或对象已执行；前端和静态资源在各自环境管理。
- `register_to` 表示接收方；`slot` 表示插槽目标；`operation` 表示一条调用绑定。组件实例连接另行表达，不由 ID 路径、同名或表格顺序推导。
- 插头与插槽通常各自描述接口，由插槽方判断兼容性。schema 可选；少量特殊连接可依双方约定和运行时行为，不要求新增正式契约 ID。
- 描述不同但兼容时可以连接，按需要告警；缺少接收方时保留未连接声明并 warning，不因可选 CLI/API 缺席阻断整个插件加载。
- 公共覆盖、实现选择和处理器替换由显式装配表达，不依赖加载顺序。
- client 实现统一 ctx 接口及既有 ctx 操作 ID 入口，不创建同义动作 ID；插件在进程内访问 ctx，TUI/Panel 通过 client 访问同一后端。
- 界面不承担后端插件装配。直接交流经 bot 的专用入口复用 run 操作，M3.6 已实现传输回执与绑定，不创建 conversation/send、conversation/cancel 同义操作；world/cadence 向同一 AgentRuntime 提交的路径仍属 M4-W 规划。
- 参与执行连接的局部组件也应显式登记；普通私有辅助函数无需登记，不要求各阶段一次性实现全部规划。

## 2. 命名空间总表

| 包或应用 | 命名空间 | 解析环境 |
| --- | --- | --- |
| `aurora_core` | `org.aurora.core` | Python 运行时 |
| `aurora_config` | `org.aurora.config` | Python 运行时 |
| `aurora_adapters` | `org.aurora.adapters` | Python 运行时；MCP 可选插件 |
| `aurora_cli` | `org.aurora.cli` | Python 运行时 |
| `aurora_control` | `org.aurora.control` | Python 运行时 |
| `aurora_agent` | `org.aurora.agent` | Python 运行时 |
| `aurora_bot` | `org.aurora.bot` | Python 运行时 |
| `aurora_api` | `org.aurora.api` | Python 运行时 |
| `aurora_model_adapter` | `org.aurora.model_adapter` | Python 运行时 |
| `aurora_logging` | `org.aurora.logging` | Python 运行时；当前未登记公共定义 |
| `aurora_world` | `org.aurora.world` | Python 运行时；世界记录、来源登记与生命周期处理器，配置来源和 cadence 后续交付 |
| `aurora_client` | `org.aurora.client` | TS 客户端 |
| `aurora_tui` | `org.aurora.tui` | TUI 本地 |
| `aurora_panel` | `org.aurora.panel` | WebUI 本地 |
| `docsite` | `org.aurora.docsite` | 文档构建环境 |
| `landing` | `org.aurora.landing` | 落地页构建环境 |

## 3. 基础登记（core 与 config）

### 3.1 注册目标

以下逻辑注册表已实现，基于统一内存表提供分类索引与专属接入规则。宿主直接引导建立总表、注册表目录和所需基础定义，随后登记其他注册表；跨包注册目标是否存在取决于该包实现与启用情况。

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
| `org.aurora.config:registries/configs` | `registry` | 配置声明、结构校验与模板关系 |

注册表登记定义，不保存所有状态值或历史事件实例。`RegistryEntry` 是内部登记项名称，不是本版新增的公共 ID。

登记关系如下；目录中列出的注册表只有在提供方实际安装并启用时才存在。

| 注册表 | 登记目标／建立方式 |
| --- | --- |
| `org.aurora.core:registries/registries` | 宿主直接建立，自身描述是否列入目录由实现决定 |
| 本节其余 core 注册表 | `org.aurora.core:registries/registries` |
| `org.aurora.config:registries/configs` | `org.aurora.core:registries/registries` |
| `org.aurora.cli:registries/commands` | `org.aurora.core:registries/registries` |
| `org.aurora.model_adapter:registries/adapters` | `org.aurora.core:registries/registries` |
| `org.aurora.agent:registries/tools` | `org.aurora.core:registries/registries` |
| `org.aurora.bot:registries/agents` | `org.aurora.core:registries/registries` |
| `org.aurora.api:registries/endpoints` | `org.aurora.core:registries/registries` |

resources 可以接收 `resource`、`assembly`、`contract` 等约定的 kind，保留原 kind，由接收方选择必要的加载和校验方式。提示词、主题等内容不必为登记而建立完整子类型体系。

配置声明使用 `config` kind，由 `org.aurora.config:registries/configs` 接收；声明同时提供对应的非持久状态、结构校验与包内 TOML 模板。插件入口为 `aurora_config`。宿主在恢复业务状态后执行 config 阶段，全部文件与关联校验通过后才原子注入 ctx。

`aurora_config` 还登记 `org.aurora.config:endpoints/configuration`（`endpoint`），由 `org.aurora.api:registries/endpoints` 接收。宿主通过 `serve --endpoints` 显式选择后才开放 POST `/configuration/list`、`/configuration/get`、`/configuration/save`；便捷启动脚本与默认 bot 示例使用 `--edit-config`。仅编辑已登记 `ConfigSpec` 的 TOML 文件，以配置声明 ID 定位，保存通过结构与关联校验并检查全部声明文件的读取修订，重启生效，不改变运行期 ctx。未连接 API 时保留声明并告警，不要求配置包导入或安装 API。契约见 [editor_contract.py](../packages/aurora_config/src/aurora_config/editor_contract.py)。新增端点不重命名既有 ID、插件入口或快照地址，无数据迁移。

### 3.2 操作、生命周期与基础契约

当前 ctx 六个操作、五个生命周期插槽与 ctx/changed 事件已实现；hook/failed 事件和本表四个 schema ID 仍为规划。实际 ctx 与插件声明通过 Python 类型表达，不以规划 schema 已登记为前提。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.core:operations/ctx/get` | `operation` | 读取 ctx |
| `org.aurora.core:operations/ctx/set` | `operation` | 写入 ctx |
| `org.aurora.core:operations/ctx/delete` | `operation` | 删除 ctx 状态 |
| `org.aurora.core:operations/ctx/list` | `operation` | 枚举共享 ctx 状态项；API 对外暴露另行配置 |
| `org.aurora.core:operations/ctx/subscribe` | `operation` | 订阅 ctx 变化 |
| `org.aurora.core:operations/ctx/unsubscribe` | `operation` | 取消订阅 |
| `org.aurora.core:lifecycle/config` | `hook_slot` | 加载、校验并注入启动配置 |
| `org.aurora.core:lifecycle/prepare` | `hook_slot` | 按配置创建资源、完成启动前装配 |
| `org.aurora.core:lifecycle/start` | `hook_slot` | 启动已装配能力 |
| `org.aurora.core:lifecycle/stop` | `hook_slot` | 停止接收并收束在途工作 |
| `org.aurora.core:lifecycle/clean` | `hook_slot` | 关闭资源并解除连接 |
| `org.aurora.config:handlers/load` | `hook_handler` | 在 config 阶段执行全部配置校验与注入 |
| `org.aurora.core:events/ctx/changed` | `event` | ctx 状态发生变化 |
| `org.aurora.core:events/hook/failed` | `event` | hook 处理器执行失败 |
| `org.aurora.core:schemas/plugin_manifest` | `schema` | 插件身份、依赖与注册项；对外暴露需求单独表达 |
| `org.aurora.core:schemas/registration` | `schema` | 注册项的通用结构 |
| `org.aurora.core:schemas/ctx_access` | `schema` | ctx 访问动作、目标与业务定位描述；取消内部命名空间授权含义，具体字段待细化 |
| `org.aurora.core:schemas/hook_slot` | `schema` | 按需使用的插槽描述：输入输出、调度及错误策略 |

ctx 原语由 core 实现。Python 插件通过进程内接口访问，CLI 使用对应命令，client 实现携带上述同一 ID 的 ctx 访问入口，TUI/Panel 使用 client。各语言实现共享语义，不要求前端解析 Python 对象或插件安装 TS 包。

所有命名空间通过显式接口访问共享 ctx，需要恢复的数据异步落盘。配置声明由 `org.aurora.config:registries/configs` 接收，宿主在恢复业务状态后执行 config 阶段，再进入 prepare/start。退出时停止新工作，让组件收尾、结束最后状态写入，保持存储可用直至最终落盘完成，再释放剩余资源。宿主负责这一顺序，不要求为每个内置收尾动作增加公共 handler ID。生命周期插槽不代表 core 内置 bot 能力。

`ctx_access` 沿用历史规划 ID，仅描述访问动作、目标与业务定位，不表示内部授权。保留 ID 不表示旧授权字段继续适用，也不要求所有 ctx 动作共享这一份结构。

当前 ctx 的 set 整项替换、读写深复制；list 返回已赋值地址并排序。成功 set 均通知，订阅不回放历史，可显式取消；缺失 get 抛 KeyError，缺失 delete 返回 False。core 的 StorageService 提供目录与存储，控制组件见第 6.1 节。数据描述可使用 Python 类型、签名或 schema，不批量新增局部请求／响应 ID。

## 4. aurora_cli

本节定义均已实现。命令包自动发现，外部插件显式选择；id/list 只展示启动装配前的总表，不创建 ctx 或启动服务。

| ID | kind | 用途或映射 |
| --- | --- | --- |
| `org.aurora.cli:registries/commands` | `registry` | 接收内置及第三方命令 |
| `org.aurora.cli:configs/default` | `config` | CLI 扩展配置声明，目标为 CLI config 状态 |
| `org.aurora.cli:schemas/command` | `schema` | 参数、帮助信息、执行目标 |
| `org.aurora.cli:commands/help` | `command` | 展示命令帮助 |
| `org.aurora.cli:commands/about` | `command` | 展示工作区与环境信息 |
| `org.aurora.cli:commands/check` | `command` | 运行工作区检查 |
| `org.aurora.cli:commands/donk/show` | `command` | 展示 Python 工作区版本 |
| `org.aurora.cli:commands/donk/major` | `command` | 升级主版本 |
| `org.aurora.cli:commands/donk/minor` | `command` | 升级次版本 |
| `org.aurora.cli:commands/donk/patch` | `command` | 升级修订版本 |
| `org.aurora.cli:commands/id/list` | `command` | 按完整 ID 展示启动装配前的登记总表 |
| `org.aurora.cli:commands/ctx/get` | `command` | 调用 `org.aurora.core:operations/ctx/get` |
| `org.aurora.cli:commands/ctx/set` | `command` | 调用 `org.aurora.core:operations/ctx/set` |
| `org.aurora.cli:commands/ctx/delete` | `command` | 调用 `org.aurora.core:operations/ctx/delete` |
| `org.aurora.cli:commands/ctx/list` | `command` | 调用 `org.aurora.core:operations/ctx/list` |
| `org.aurora.cli:commands/ctx/watch` | `command` | 订阅并展示 ctx 变化，退出时取消订阅 |
| `org.aurora.cli:commands/run` | `command` | 应用预配置，启动选定装配 |
| `org.aurora.cli:state/config` | `state_key` | CLI 参数解析后的配置 |

命令由 CLI 接收并登记。未安装或未启用 CLI 时，指向命令表的声明保留为未连接并 warning，不阻断其他能力。`ctx/watch` 组合订阅、渲染与取消订阅，不要求与操作一一对应。

## 5. aurora_model_adapter

| ID | kind | 状态 | 用途 |
| --- | --- | --- | --- |
| `org.aurora.model_adapter:registries/adapters` | `registry` | 已实现 | 接收模型适配器工厂 |
| `org.aurora.model_adapter:services/model_client` | `service` | 已实现 | 上层消费的统一 ModelClient 协议 |
| `org.aurora.model_adapter:adapters/litellm` | `adapter` | 已实现 | 基于 LiteLLM 创建 ModelClient |
| `org.aurora.model_adapter:schemas/model_request` | `schema` | 已实现 | 统一模型请求 |
| `org.aurora.model_adapter:schemas/model_response` | `schema` | 已实现 | 统一模型响应 |
| `org.aurora.model_adapter:schemas/model_chunk` | `schema` | 已实现 | 文本增量、完整工具请求和结束片段 |
| `org.aurora.model_adapter:schemas/model_capabilities` | `schema` | 已实现 | streaming、tool_calls 能力声明 |
| `org.aurora.model_adapter:configs/profiles` | `config` | 已实现 | profile 模板、结构与状态关系 |
| `org.aurora.model_adapter:configs/bindings` | `config` | 已实现 | 角色绑定模板、结构与 profile 引用校验 |
| `org.aurora.model_adapter:state/config` | `state_key` | 已实现 | 适配器选择与连接配置；来源为包内 TOML 模板 |
| `org.aurora.model_adapter:state/bindings` | `state_key` | 已实现 | 逻辑模型角色与服务实例的可恢复绑定描述；来源为包内 TOML 模板 |

插件入口为 `aurora_model_adapter`，依赖 aurora_config，登记 adapters、model_client、四个模型 schema、两个配置声明及其非持久状态；FakeModel 是可直接注入的离线实现，没有单独的 adapter ID。LiteLLM 适配器、工厂加载、TOML profiles 与角色绑定恢复均已接入默认装配。bot 使用 ModelClient，不直接引用 SDK，不强制新增独立工厂 schema ID。

模型 complete 返回完整响应，stream 通过异步上下文消费文本增量、完整 ToolCall 与唯一结束片段。工具 JSON 参数由适配层组装，能力不足明确拒绝。调用方关闭单次流，装配在全部调用结束后关闭客户端；配置与 api_key 分开传入。ctx 快照仅包含 persistent 状态并使用严格 JSON，运行时对象由装配持有，凭证不写入 ctx；模型配置与绑定由包内 TOML 模板提供，只复制缺失文件并保留用户内容。

## 6. 控制、Agent、Bot 与世界定义

发现分组为 `aurora.plugins`。插件名称、公开定义和 Python 导入路径分别归属自己的包，运行时不提供旧名称别名。

### 6.1 aurora_control

`aurora_control` 仅依赖 core，提供执行身份、状态绑定与连接契约。控制插件登记 Controller 基类、Serial、Branch、While、Parallel 及其端口和在途状态，共十六项；Controller 基类不作为独立流程执行。

| ID | kind | 提供插件 |
| --- | --- | --- |
| `org.aurora.control:handlers/control` | `component` | `aurora_control` |
| `org.aurora.control:handlers/control/execute` | `hook_handler` | `aurora_control` |
| `org.aurora.control:handlers/control/children` | `hook_slot` | `aurora_control` |
| `org.aurora.control:handlers/control/serial` | `component` | `aurora_control` |
| `org.aurora.control:handlers/control/serial/execute` | `hook_handler` | `aurora_control` |
| `org.aurora.control:handlers/control/serial/children` | `hook_slot` | `aurora_control` |
| `org.aurora.control:handlers/control/branch` | `component` | `aurora_control` |
| `org.aurora.control:handlers/control/branch/execute` | `hook_handler` | `aurora_control` |
| `org.aurora.control:handlers/control/branch/children` | `hook_slot` | `aurora_control` |
| `org.aurora.control:handlers/control/while` | `component` | `aurora_control` |
| `org.aurora.control:handlers/control/while/execute` | `hook_handler` | `aurora_control` |
| `org.aurora.control:handlers/control/while/children` | `hook_slot` | `aurora_control` |
| `org.aurora.control:handlers/control/parallel` | `component` | `aurora_control` |
| `org.aurora.control:handlers/control/parallel/execute` | `hook_handler` | `aurora_control` |
| `org.aurora.control:handlers/control/parallel/children` | `hook_slot` | `aurora_control` |
| `org.aurora.control:state/control` | `state_key` | `aurora_control` |

控制状态按定义、实例、运行与单次执行定位，终态通知后删除，不保存调用历史。`ExecutionRequest` 只携带身份，业务数据通过显式绑定的 ctx 地址交换。

### 6.2 aurora_agent

agent 包依赖 control、core 与 model_adapter。ReAct 循环、模型调用、工具执行和默认阶段分别提供插件。`aurora_agent.react_defaults` 要求同时启用 `aurora_agent.react`、`aurora_agent.model` 与 `aurora_agent.tools`。

| ID | kind | 提供插件 |
| --- | --- | --- |
| `org.aurora.agent:handlers/model_call` | `component` | `aurora_agent.model` |
| `org.aurora.agent:handlers/model_call/execute` | `hook_handler` | `aurora_agent.model` |
| `org.aurora.agent:handlers/react_agent` | `component` | `aurora_agent.react` |
| `org.aurora.agent:handlers/react_agent/execute` | `hook_handler` | `aurora_agent.react` |
| `org.aurora.agent:react/prepare` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:react/infer` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:react/act` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:react/observe` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:react/finish` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:react/error` | `hook_slot` | `aurora_agent.react` |
| `org.aurora.agent:registries/tools` | `registry` | `aurora_agent.tools` |
| `org.aurora.agent:handlers/react/execute_tools` | `component` | `aurora_agent.tools` |
| `org.aurora.agent:handlers/react/execute_tools/execute` | `hook_handler` | `aurora_agent.tools` |
| `org.aurora.agent:handlers/react/execute_tools/children` | `hook_slot` | `aurora_agent.tools` |
| `org.aurora.agent:tools/before_call` | `hook_slot` | `aurora_agent.tools` |
| `org.aurora.agent:tools/after_call` | `hook_slot` | `aurora_agent.tools` |
| `org.aurora.agent:handlers/react/build_prompt` | `component` | `aurora_agent.react_defaults` |
| `org.aurora.agent:handlers/react/build_prompt/execute` | `hook_handler` | `aurora_agent.react_defaults` |
| `org.aurora.agent:handlers/react/interpret_response` | `component` | `aurora_agent.react_defaults` |
| `org.aurora.agent:handlers/react/interpret_response/execute` | `hook_handler` | `aurora_agent.react_defaults` |
| `org.aurora.agent:handlers/react/record_observation` | `component` | `aurora_agent.react_defaults` |
| `org.aurora.agent:handlers/react/record_observation/execute` | `hook_handler` | `aurora_agent.react_defaults` |

各 component 的 `/execute` 入口登记为 hook_handler，interface 指向自身组件。ReAct 的 prepare/infer/act/observe/finish/error 是具名插槽，连接属于具体实例。默认连接依次执行上下文构建、ModelCall、响应解释、ToolExecutor 和观察接纳；finish/error 可没有处理器。

AgentRuntime 提供提交、等待和取消，接入宿主显式提供的 agent 获取、执行与占用查询。运行句柄保留在进程内。agent 不规定全局消息、inbox 或运行状态地址，宿主通过 StateBinding 和 InstanceStateBinding 提供这些地址。

### 6.3 aurora_bot

bot 负责默认产品装配、配置、资源所有权和运行入口。定义使用 `org.aurora.bot`，其运行状态地址由本装配分配，不属于 agent 的固定状态协议。

| ID | kind | 提供插件 |
| --- | --- | --- |
| `org.aurora.bot:commands/run/submit` | `command` | `aurora_bot.assembly` |
| `org.aurora.bot:commands/run/activate` | `command` | `aurora_bot.assembly` |
| `org.aurora.bot:commands/run/cancel` | `command` | `aurora_bot.assembly` |
| `org.aurora.bot:assemblies/default` | `assembly` | `aurora_bot.assembly` |
| `org.aurora.bot:services/run_control` | `service` | `aurora_bot.assembly` |
| `org.aurora.bot:operations/run/submit` | `operation` | `aurora_bot.assembly` |
| `org.aurora.bot:operations/run/activate` | `operation` | `aurora_bot.assembly` |
| `org.aurora.bot:operations/run/cancel` | `operation` | `aurora_bot.assembly` |
| `org.aurora.bot:configs/default` | `config` | `aurora_bot.assembly` |
| `org.aurora.bot:state/config` | `state_key` | `aurora_bot.assembly` |
| `org.aurora.bot:state/agents` | `state_key` | `aurora_bot.assembly` |
| `org.aurora.bot:state/messages` | `state_key` | `aurora_bot.assembly` |
| `org.aurora.bot:state/run` | `state_key` | `aurora_bot.assembly` |
| `org.aurora.bot:state/react_work` | `state_key` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/prepare_model` | `hook_handler` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/clean_model` | `hook_handler` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/prepare_bot` | `hook_handler` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/start_bot` | `hook_handler` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/stop_bot` | `hook_handler` | `aurora_bot.assembly` |
| `org.aurora.bot:handlers/assembly/clean_bot` | `hook_handler` | `aurora_bot.assembly` |

`state/config` 的来源为 bot 的 TOML 模板，不进入快照。`state/agents` 保存实例级 inbox/progress，`state/messages` 保存上下文，`state/run` 保存最近运行状态，`state/react_work` 保存按 run_id 定位的工作数据。实例以 instance_id 隔离。

运行操作和命令均使用 `run/submit`、`run/activate`、`run/cancel`，要求显式 instance_id。运行管理服务按实例绑定 AgentRuntime；CLI 命令通过公共操作分发，不要求 bot 导入 CLI 实现。默认装配的资源在 prepare 创建，stop 收束运行，clean 关闭工具与模型并解绑实例。

### 6.4 扩展边界

多 agent 通信、多模型聚合、MCP 和额外消息传输属于后续扩展，未实现的规划名称不作为已登记定义列出。具体定义以所选插件的 `id list` 输出为准，名称存在不代表组件已连接或执行。

MCP 客户端与桥接实现计划归属可选包 `aurora_adapters.mcp`，不再预留 bot 的 mcp_servers 注册表。该旧规划 ID 从未登记，无配置或快照迁移；适配器定义的完整 ID 和插件入口随 M4-B 实现登记，不提供旧名兼容层。MCP 工具桥复用实际存在的 `org.aurora.agent:registries/tools`、工具 ExecutionPlug 及执行器插槽，bot 只负责装配。

### 6.5 世界记录与 cadence 的归属

`aurora_world` 的[插件入口](../packages/aurora_world/src/aurora_world/plugin.py)已登记下列记录与来源定义，启用时不创建来源或任务，仅依赖 core。包提供进程内 `WorldRecords.append/get/read` 和 `WorldSources` 装配；变化观察复用 core 的 ctx 订阅，不另建世界 operation 或事件的同义 ID。

| 当前定义 | kind | 定位与职责 |
| --- | --- | --- |
| `org.aurora.world:state/records` | state_key | 全局 `location={}`，保存版本化日志、来源消息身份、记录身份、递增序号及裁剪边界；由 WorldRecords 追加和裁剪，随宿主 ctx 快照保存 |
| `org.aurora.world:state/sources` | state_key | 按 source_id 定位运行阶段、接纳开关及固定错误代码；非持久化 |
| `org.aurora.world:registries/sources` | registry | 接收 `kind=source`、target 为 SourceSpec 的工厂定义，登记到 core 注册表目录 |
| `org.aurora.world:handlers/sources/prepare` | hook_handler | 接入 core prepare，创建已选来源实例 |
| `org.aurora.world:handlers/sources/start` | hook_handler | 接入 core start，开放来源接纳并启动实例 |
| `org.aurora.world:handlers/sources/stop` | hook_handler | 接入 core stop，等待已启动来源结束自有任务 |
| `org.aurora.world:handlers/sources/clean` | hook_handler | 接入 core clean，关闭已创建实例的资源 |
| `org.aurora.world:configs/sources` | config | 可选配置插件登记，声明来源选择列表及包内 TOML 模板 |
| `org.aurora.world:state/config` | state_key | 可选配置插件登记，全局来源配置，非持久化 |
| `org.aurora.world:handlers/sources/configure` | hook_handler | 可选配置插件登记，加载配置后选择来源，prepare 前完成引用检查 |
| `org.aurora.world:sources/environment/time` | source | 可选环境插件登记，按配置周期采集宿主本地时间 |
| `org.aurora.world:sources/environment/weather` | source | 可选环境插件登记，按配置地点和周期采集 Open-Meteo 当前天气；失败形成不可用观察 |

来源提供方用自身命名空间声明定义，并设置 `register_to=org.aurora.world:registries/sources`；插件依赖须显式启用 aurora_world。`WorldSources.add(definition_id, source_id=..., config=...)` 在准备前选择定义并固定实例身份，`component()` 返回宿主 LifecycleComponent。可选 `aurora_world.configuration` 插件要求显式启用 aurora_config 和 aurora_world，安装使用 `aurora-world[config]`；`aurora_world.configuration.configured_sources_component` 通过 config 阶段完成 TOML 装配，模板位于配置目录的 `org.aurora.world/config.toml`。默认 bot 在该配置定义已登记时装配来源组件。来源工厂只获得绑定身份的 emit 回调和配置，不获得原始 ctx。SourceInstance 提供 start/stop/aclose 及可选的托管 run 主循环；后台结束或失败封闭对应入口，失败不自动重启。状态、配置和资源不进入业务快照，后台错误只记录固定代码。只有所选来源进入对应 start 时才可提交，关闭后旧回调也会拒绝写入；W1 的低层记录接口仍独立可用。

环境来源插件为 `aurora_world.environment`，要求显式启用 aurora_world，安装 extra 为 `aurora-world[environment]`，增加 config 和 httpx 包依赖。两个来源独立配置和停用；时间默认间隔 60 秒，天气默认 900 秒，地点标签及经纬度须在天气实例配置中给出。采样身份由启动会话与计数构成，重启只采集当前观察，不回放离线周期。天气失败是主循环仍可继续采样的不可用观察，区别于 source_status 的主循环失败；不增加事件总线或 agent 调度定义。

`WorldPosition(journal_id, sequence, record_id)` 表示已读取位置；`sequence=0` 时不含 record_id。日志变化、位置超前或锚点不一致均拒绝静默恢复。v2 日志以 next_sequence 和 pruned_through/pruned_record_id 保存序号及裁剪边界；旧版 v1 可读，下次变更升级，旧程序不能读取 v2。位置低于裁剪边界会报 CursorError，恰好位于边界时可凭正确身份继续读取；省略 after 则返回当前窗口。默认完整保留；环境时间保留最新 1 条，天气按采样时间保留一小时内最多 4 条，可配置保留数量与时长。仅仍保留的消息参与去重，其他来源不受环境策略影响；接纳不保证落盘。详见[设计中的接口与恢复规则](aurorabot-design-v0.2.3.md#77-直接交流与世界输入)。来源与 cadence 的其余能力按 [M4-W 计划](plan.md)交付：

| 能力 | 定义归属 | 实施边界 |
| --- | --- | --- |
| 世界输入记录、读取与变化观察 | `org.aurora.world` | M4.W1 已实现上述状态与 Python 接口；不承载全部直接对话，不要求记录绑定某个 run |
| 世界来源及其生命周期、配置 | `org.aurora.world`；第三方来源使用自己的命名空间 | W2.1–W2.3 已交付登记、绑定接纳、声明配置、后台托管与时间/天气来源，并接入默认装配 |
| MCP 客户端、世界来源桥与工具桥 | `org.aurora.adapters`；B1/B2/B4 定义见第 6.6 节 | 独立客户端、世界通知桥和工具桥已交付，不改变 world/agent 的定义归属 |
| cadence 配置、消费位置及转交关联 | `org.aurora.bot` | M4.W3 在 bot 包内提供可选插件；插件名与完整 ID 随实现登记，不建立独立 cadence 包 |
| 引导提交与执行 | 既有 `org.aurora.bot:operations/run/submit` 及 AgentRuntime | cadence 复用既有入口，不新增调度所有者，不向 world 命名空间搬入 agent 定义 |

来源消息身份、世界记录身份、guidance_id、run_id 和 execution_id 均为实例数据，不替代公共定义 ID。一条世界消息可进入已有运行；转交回执与消费位置不表示业务完成。直接交流和世界输入保留各自来源关联，避免同一输入经两条路径重复提交。M4.W4 将 live_workshop 改为正式 world/cadence 的消费者，替换其示例自有调度。

### 6.6 MCP 客户端、世界通知桥与工具桥（M4.B1/B2/B4 已实现）

安装 `aurora-adapters[mcp]`，显式启用 `aurora_config` 与 `aurora_adapters.mcp`。入口属于 `aurora.plugins`，名称与 Plugin.name 一致；发现不创建网络资源。基础 adapters 包仅依赖 core，MCP extra 引入 config、SDK 2.3.0、httpx2 和 tomli-w，不依赖 world、agent 或 bot。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.adapters:configs/mcp` | `config` | v2 servers 连接及工具选择声明；模板来自 aurora_adapters.mcp/config.toml |
| `org.aurora.adapters:state/mcp/config` | `state_key` | 全局非持久配置；文件位于 org.aurora.adapters/config.toml |
| `org.aurora.adapters:state/mcp/clients` | `state_key` | 非持久观察；location 为 owner 与 connection_id；error_location 仅含失败字段位置 |
| `org.aurora.adapters:handlers/mcp/configure` | `hook_handler` | config 阶段复制并选择连接声明 |
| `org.aurora.adapters:handlers/mcp/prepare` | `hook_handler` | 创建客户端并检查协议与所需能力 |
| `org.aurora.adapters:handlers/mcp/stop` | `hook_handler` | 封闭借用，取消并等待剩余消费者 |
| `org.aurora.adapters:handlers/mcp/clean` | `hook_handler` | 在依赖者清理后释放客户端、HTTP 资源及 stdio 进程树 |

`MCPClients(ctx, hooks).component()` 默认组件身份为 `aurora_adapters/mcp`，依赖 `aurora_config`；消费者显式依赖该组件。`connection(connection_id)` 是适配层异步借用上下文，SDK 对象不进入 ctx。观察只包含 phase、error、error_location、accepting、type、configured_protocol、negotiated_protocol、negotiation_attempts 和已知能力名称，不保留服务端描述或凭证。凭证注入参数为 resolve_env，仅在创建资源时调用；local 还要求宿主显式提供 workspace_root，cwd 默认该目录，相对路径基于它解析。negotiated_protocol 替代旧 protocol_version，无兼容别名及业务快照迁移；最多四条协商摘要只包含方法、HTTP 状态和数值 RPC 错误码。ready 表示准备成功，不代表持续联网健康检查；请求失败明确返回固定错误码，无自动重连或请求重放。

新增定义均非持久，无旧 ID/插件名替换，无快照迁移；不自动启用插件、改写用户文件或调整默认 bot 装配。工具桥定义随 B2 实现。

B4 通过 `aurora-adapters[mcp-world]` extra 增加 world/config 依赖。插件 `aurora_adapters.mcp.world` 要求显式启用 `aurora_adapters.mcp` 和 `aurora_world.configuration` 及其依赖；仅加载 MCP 客户端不导入 world。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.adapters:sources/mcp/resources` | `source` | 资源通知来源，登记至 org.aurora.world:registries/sources |
| `org.aurora.adapters:state/mcp/world` | `state_key` | 非持久桥接诊断；location 为 source_id |

来源配置使用既有 world 的 sources.config，不增加配置文件或第二个来源所有者。`mcp_world_component(ctx, hooks, clients)` 替代通用 configured_sources_component，注入共享客户端并依赖其 instance_id；来源工厂只接收固定身份的 emit，客户端借用与协议类型留在适配层。诊断包括 phase/error、close_error、tools_dirty、accepted/duplicates/discarded 和 identity_modes；world 的 sources 状态仍表示托管主循环的状态。

资源 URI 精确匹配；notification/resource 模式用独立本地观察身份，event 模式读取严格 `{message_id, payload}` 单文本资源，以连接、URI、message_id 组合成世界消息身份。消息身份不是公共 ID；相同身份异文拒绝，去重仍只覆盖 world 的保留窗口。只有成功 emit 后才表示 world 内存接纳，不承诺即时落盘。正常停止期间尚未接纳的缓冲或在途观察通过 discarded、固定错误码和日志明确报告，不伪装为已保存或自动重放。

工具插件 `aurora_adapters.mcp.tools` 要求显式启用 `aurora_adapters.mcp` 和 `aurora_agent.tools` 及其依赖；`aurora-adapters[mcp-tools]` 安装工具桥依赖，不引入 world/bot/CLI/API。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.adapters:components/mcp/tool` | `component` | MCP 工具执行组件，所有实例使用注入的 input/output 状态绑定 |
| `org.aurora.adapters:components/mcp/tool/execute` | `hook_handler` | 单次远程调用执行端口 |
| `org.aurora.adapters:handlers/mcp/tools/prepare` | `hook_handler` | 在 PREPARE 分页发现并原子登记工具 |
| `org.aurora.adapters:tools/mcp/<name>` | `tool` | 服务别名或 v2 自动名称派生的稳定 ID，登记到 org.aurora.agent:registries/tools |

工具选择位于 v2 servers.<服务名>.tools，include/exclude 选择远端名称，aliases 指定本地名称。默认通配发现全部工具，缺少别名时使用 v2 稳定自动名称；空 include 不登记工具。MCPTools.tool_ids 在准备完成后提供本宿主已登记身份，名称冲突在整批登记前拒绝。旧配置显式迁移保留原工具名称与公共 ID，没有旧工具的服务迁移为 include=[]，不扩大暴露范围、不覆盖已有 TOML。定义使用 ToolSpec，实例使用 ExecutionPlug，不把 SDK 类型引入 agent。消费者通过 `DefaultAssembly.components(depends_on=(bridge.instance_id,))` 或自身生命周期依赖保证发现先完成。工具集合只在新宿主 prepare 时生成；无旧 ID 或插件替换，无快照迁移。agent 的 ToolExecutionError 提供协议无关的安全失败码、消息和可选 JSON 内容。

B5.4 已登记可选产品插件 `aurora_adapters.mcp.bot`，requires 为 `aurora_adapters.mcp.tools` 与 `aurora_bot.assembly`，依赖须显式启用。安装 `aurora-adapters[mcp-bot]`，不强制安装 CLI/API；宿主分别安装并选择。

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.adapters:assemblies/mcp/default_bot` | `assembly` | 共享 MCPClients，完成工具发现后向 DefaultAssembly 提供增量；可选世界来源复用同一连接 |

预设模块 `aurora_adapters.mcp.preset` 只补缺失模板，宿主选择冲突时输出独立候选和差异。运行期新增工具实例采用工具 ID 的 local_path，已有显式选择保留原实例身份；不改写配置或快照。来源实例工厂通过 world 的 source_factories 注入，不修改公共来源定义。CLI/API 装配工厂均接收 workspace_root（CLI --root 解析值），提供给 stdio 路径解析。

## 7. aurora_api

### 7.1 传输契约与基础端点

下表除 endpoints 注册表已由 `aurora_api` 插件登记，其余仍为规划身份。当前实现直接提供本机 `POST /ctx/get`、`/ctx/list`、`/ctx/set`、`/ctx/delete` 与 `WS /ctx/watch`，绑定既有 core ctx 操作 ID，并接收宿主显式选择的产品端点。公开数据描述位于 [aurora_api.contract](../packages/aurora_api/src/aurora_api/contract.py)，不提供任意 operation 转发或全量登记表导出。

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
| `org.aurora.bot:endpoints/conversation` | `endpoint` | 已由 aurora_bot.assembly 登记；由 API 显式开放，复用既有 run/submit 与 run/cancel 操作 |

此 ID 属于 bot 命名空间，登记至 `org.aurora.api:registries/endpoints`。M3.6 提供 POST `/conversation/info`、`/conversation/submit`、`/conversation/query`、`/conversation/cancel`，回执关联 session_id、instance_id、request_id、guidance_id、sequence、run_id；查询区分接纳与运行终态。重复请求和重启边界见[设计第 10.2 节](aurorabot-design-v0.2.3.md#102-界面动作边界)。该路径不依赖 world/cadence；API 缺席时适用可选接收方约定，不阻断进程内运行。没有新增持久状态或改写既有 ID、配置和快照。

API 传输实际需要的 bot/core 事件时保留原事件类型 ID，可添加传输信封，不另建同义业务事件身份。

## 8. aurora_client

以下对象在 TS 客户端环境解析；本地状态不自动成为 Python ctx 状态。

当前 `@aurorabot/client` 导出 [CtxClient](../packages/aurora_client/src/ctx.ts)、[订阅与连接状态](../packages/aurora_client/src/subscriptions.ts)，以及生成的 [ctx 类型及 ID 常量](../packages/aurora_client/src/generated/ctx-contract.ts)；[JSON 描述](../packages/aurora_client/src/generated/ctx-contract.json) 与 TS 契约同源。客户端已实现六类 ctx 入口、关闭、断线重订阅与状态刷新，验收覆盖本机 Node。下表仍为规划身份，类与本地句柄不自动登记服务或状态 ID，生成文件本身不等于登记 `contracts/generated`。

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
| `org.aurora.tui:views/chat` | `view` | bot 工作台中的直接交流与运行观察 |
| `org.aurora.tui:views/config` | `view` | 配置界面 |
| `org.aurora.tui:views/ctx` | `view` | ctx 查看与操作 |
| `org.aurora.tui:actions/message/submit` | `ui_action` | 经 client 直接引导目标 bot；运行中保留当前 loop；M3.6 实现传输关联 |
| `org.aurora.tui:actions/run/cancel` | `ui_action` | 取消指定 instance_id/run_id 并等待收尾；不等同于关闭观察 |
| `org.aurora.tui:resources/keymap/default` | `resource` | 默认按键映射 |
| `org.aurora.tui:state/preferences` | `state_key` | 终端界面偏好 |

## 10. aurora_panel

| ID | kind | 用途 |
| --- | --- | --- |
| `org.aurora.panel:views/chat` | `view` | Web bot 工作台中的直接交流与运行观察 |
| `org.aurora.panel:views/config` | `view` | Web 配置界面 |
| `org.aurora.panel:views/ctx` | `view` | Web ctx 查看与操作 |
| `org.aurora.panel:actions/message/submit` | `ui_action` | 经 client 直接引导目标 bot；复用 M3.6 的传输关联 |
| `org.aurora.panel:actions/run/cancel` | `ui_action` | 取消指定 instance_id/run_id；浏览器断开不自动取消运行 |
| `org.aurora.panel:resources/theme/default` | `resource` | 默认界面主题 |
| `org.aurora.panel:state/preferences` | `state_key` | Web 界面偏好 |

第 9–10 节的视图与动作仍为待实现的规划身份。TUI 与 Panel 共享 client，各自处理输入、反馈和本地状态，不参与后端插件装配。首版是 bot 工作台，直接交流路径由 D10 确定；通过专用入口接入 run 操作，通用 ctx 写入不隐式启动业务。首版不引入多会话上下文隔离，世界输入和引导关联在 M4-W 接入后补充展示。

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

下表包含规划关系，是否已实现以各包条目的状态为准；执行包的实际登记关系见第 6 节。

| 声明方 | 关系 | 目标 |
| --- | --- | --- |
| 各 Python 逻辑注册表 | 目录登记 | `org.aurora.core:registries/registries`；自举按第 3.1 节处理 |
| 各插件配置声明 | `register_to` | `org.aurora.config:registries/configs`；同时声明非持久状态与模板 |
| bot run 命令 | `register_to` | `org.aurora.cli:registries/commands`；CLI 缺席时未连接并告警 |
| bot submit 命令 | 一条操作绑定 | `org.aurora.bot:operations/run/submit` |
| bot cancel 命令 | 一条操作绑定 | `org.aurora.bot:operations/run/cancel` |
| bot 命令与 CLI 接收方 | 可使用的描述 | `org.aurora.cli:schemas/command`；不要求导入 CLI 实现 |
| bot conversation 端点 | `register_to` | `org.aurora.api:registries/endpoints`；API 缺席时未连接并告警 |
| config configuration 端点 | `register_to` | `org.aurora.api:registries/endpoints`；API 缺席时未连接并告警 |
| bot conversation 端点 | 已实现操作绑定 | `org.aurora.bot:operations/run/submit` 与 `org.aurora.bot:operations/run/cancel`；复用现有操作 |
| world 来源 | 记录、来源装配、声明配置、后台托管与时间/天气来源已实现 | 世界记录由 world 提供；来源不直接决定 agent 运行 |
| cadence | M4-W 规划读取与提交 | 订阅选定世界记录，向目标实例的既有 AgentRuntime 提交引导 |
| ReAct 默认处理器 | `register_to` | `org.aurora.core:registries/hook_handlers` |
| AgentRuntime | 宿主入口 | `get_agent`、`execute`、`is_executing`；不引用 DefaultAssembly |
| control 组件 | 执行插槽 | 通过 ExecutionSlot 连接 ExecutionPlug，业务数据经 ctx 绑定交换 |
| 提示词构建处理器 | `slot` | `org.aurora.agent:react/prepare` |
| 模型调用处理器 | 注入服务 | `org.aurora.model_adapter:services/model_client` |
| LiteLLM 适配器 | `register_to` | `org.aurora.model_adapter:registries/adapters` |
| ctx 传输端点与 client | 共用动作身份和语义 | 第 3.2 节的 core ctx 操作 ID |
| API 传输的事件 | 事件类型引用 | 原 bot/core 事件 ID |
| TUI/Panel 的 ctx 交互 | 共享客户端入口 | `org.aurora.client:services/api_client` |
| TUI/Panel 的订阅 | 连接与订阅支持 | `org.aurora.client:services/event_stream` |

M3.6 的直接交流绑定已实现和验收；M4.W1 已登记世界记录状态，W2.1–W2.3 已提供来源登记、声明配置、后台托管及时间/天气来源，cadence 待后续实现。新记录状态不自动开放给 API；ID 引用不等于代码导入、已连接或默认对外暴露。旧配置和快照无需迁移；含世界记录的新快照恢复时必须显式启用 aurora_world，缺失定义不会被静默忽略。

## 14. 第三方声明示例

以下为扩展示例，不计入官方 ID 目录。

```yaml
id: dev.example.memory:handlers/inject_context
kind: hook_handler
register_to: org.aurora.core:registries/hook_handlers
slot: org.aurora.agent:react/prepare
```

```yaml
id: dev.example.models:adapters/private_gateway
kind: adapter
register_to: org.aurora.model_adapter:registries/adapters
```

示例只表达规划中的登记与连接关系，不是可直接运行的完整插件。按需补充提供者、加载入口和接口描述；schema 并非特殊连接的前置条件。接收方判断兼容，bot 在双方均提供 schema 且描述不同时于接收时告警。当前 priority 从小到大，同值保持连接顺序，before/after 未实现。内部 ctx 共享，所有状态修改仍经显式接口。

## 15. 目录维护

- 新公共定义确定命名空间、kind、实际用途及登记环境；接口描述按需要维护，不强制独立 schema ID。
- 用途、输入输出或连接变化时同步文档和实际维护的接口；名称保留不等于字段或行为已经冻结。
- 当前执行组件通过 component_entries 显式登记定义和端口，再建立实例连接；普通私有辅助函数无需登记。
- client 对同一 ctx 动作沿用现有身份，不为语言或传输差异创建同义操作。
- 兼容与迁移围绕实际稳定的公共边界处理，不强制所有局部连接建立版本体系。
- `aurora_playground` 正式纳入包设计后再补充，本版不预占公共 ID。

## 16. 版本修订记录

### 16.1 v0.2.3（2026-11-01）

- control、agent 与 bot 定义按包归属：control 使用 `org.aurora.control`，agent 使用 `org.aurora.agent`，bot 保留 `org.aurora.bot`。
- 插件发现分组为 `aurora.plugins`；入口为 `aurora_control` 与 `aurora_agent.model/react/tools/react_defaults`，运行时不提供旧名称别名。
- 更新模型适配器状态：LiteLLM、TOML profiles、模型配置与角色绑定均已实现。
- 新增 `org.aurora.config`：配置声明、结构校验与 TOML 模板由 `aurora_config` 提供，core 保留通用状态与持久化机制。
- 同步 AgentRuntime 的宿主入口、M2 完成状态与独立 harness 边界。
- 保留 v0.2.2 的全部规划身份；未实现的 API、client、TUI/Panel 与扩展定义仍按规划列出。

### 16.2 v0.2.2 原始修订记录（2026-10-29）

- 沿用 v0.2.1 全部公共 ID 与 kind，不新增、删除或重命名定义。
- 同步 core 统一哈希表、登记项与逻辑注册表关系，并补充自举和跨包目录登记说明。
- 同步可选宿主缺席时 warning 与未连接处理，不因 CLI/API 缺席阻断整个插件。
- 明确双方按需描述接口，由插槽方判断兼容；特殊连接可没有正式 schema。
- client 实现统一 ctx 访问入口与现有 ID 支持；HTTP/WS 是传输，TUI/Panel 不参与后端插件装配。
- 保留 bot 操作与端点规划，但移除界面动作必须调用它们的表述；提交与取消的具体机制不在本版决定。
- 保留运行时对象与绑定管理的讨论空间，仅确定需要恢复的数据落盘及界面数据不全量导出。
- 同步逐步断开的退出顺序，最终落盘由宿主保证，不批量增加生命周期处理器 ID。

