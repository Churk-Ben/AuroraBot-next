# AuroraBot 初期设计文档 v0.2.3

版本：v0.2.3
设计版本日期：2026-10-29；执行包拆分、M2 验收与文档基线对齐：2026-11-01。

状态：架构基线与当前实现说明；M2 已完成，M3 尚未开始。规划部分不代表已交付。

配套附件：[公共 ID 目录](aurorabot-id-catalog-v0.2.3.md)。保留规划身份并列出当前组件定义；名称存在不表示行为或字段已经冻结。

执行能力由三个平级包分担：`aurora_control` 提供执行契约与四种控制组合，`aurora_agent` 提供 ReAct、模型调用、工具执行与运行调度，`aurora_bot` 负责默认装配、资源和产品入口。五条可运行示例见 [启动指南](../examples/START.md)，执行定义见 [公共 ID 目录第 6 节](aurorabot-id-catalog-v0.2.3.md#6-控制agent-与-bot-定义已实现)，独立 harness 的边界与后续工作见 [拆包评估](aurora_agent_extraction_assessment.md)。本文其余规划部分保留设计语境，当前验收范围见 [变更记录](CHAGELOG.md)。

## 1. 项目概述

AuroraBot 是一个以 ctx/hook 为总线、以 entrypoint 为插件发现入口、以命名空间 ID 为统一寻址方式的 bot 框架。Python 侧提供运行环境与能力装配，TypeScript 侧提供共享客户端、TUI、WebUI、文档站与落地页。

总体架构采用微内核与插件装配：`aurora_core` 提供共享 ctx、对象登记与寻址、连接及最小调用机制；`aurora_control` 提供执行契约和控制组合；`aurora_agent` 提供 ReAct、模型调用、工具执行与运行调度；`aurora_bot` 装配默认产品；模型适配层提供统一模型服务；CLI 提供命令交互，API 为客户端连接后端提供传输支持。

公开资源、操作、插槽和扩展项使用稳定 ID 相互引用。命名空间组织归属与名称，组件通过显式连接组合；接口和 schema 随实际协作需要逐步明确，不要求先建立完整契约体系才能运行。

### 1.1 服务场景

AuroraBot 面向个人单租户场景。一个唯一的 bot 后端提供共享运行环境，TUI、Panel 通过 client 与该后端的 ctx 交互。系统不引入多租户运行隔离或多租户记忆隔离。

会话、运行和 agent 标识用于组织业务数据与执行状态，不表示租户或插件访问权限边界。界面的本地视图状态不必全部进入后端 ctx。

插件通常在后端进程内通过 ctx、服务和插头／插槽介入系统。TUI、Panel 是交互界面，不承担插件发现、装配或执行树扩展职责。HTTP/WS 是客户端与后端之间的传输实现。

## 2. 设计原则

1. **core 只做通用机制。** 提供 ID 登记与寻址、共享 ctx、订阅、连接、生命周期及最小调用机制；具体业务和流程控制由插件实现。
2. **bot 装配能力，不另造机制。** bot 包可以包含默认插件实现，但装配职责保持薄，不将业务机制下沉到 core。
3. **公开对象统一寻址。** 跨组件引用使用稳定 ID；参与 bot 执行连接的组件及其端口显式登记，不要求每个私有辅助函数或运行时对象都有公共 ID。
4. **接口按需明确。** 双方通常描述各自接口，由接收方判断兼容性；少量特殊连接可以依赖双方约定和运行时行为，不强制独立 schema 或公共 schema ID。
5. **连接由提供插槽的一方判断。** 接口不完全相同不等于不能连接；core 不以 schema 相等作为全局接入条件。
6. **缺少接收方时允许未连接。** 未安装或未启用 CLI/API 等宿主时，保留相关声明并告警，不因可选入口缺席而阻断其他能力运行。
7. **统一 ctx 访问语义。** 插件通过进程内接口访问 ctx；TUI、Panel 通过 client 的对应接口访问同一个 ctx，实际状态操作由 core 完成。
8. **模型适配透明。** bot 使用统一 ModelClient，不直接依赖 LiteLLM 或具体模型 SDK。
9. **共享状态与显式变更。** ctx 以内存为工作区；所有状态修改经过显式接口，需要恢复的数据异步落盘，正常退出前完成最后写入。
10. **身份与实例分离。** 公共 ID 标识定义，实例标识定位具体对象；命名空间不构成内部 ctx 访问隔离边界。
11. **按连接与依赖逐步关闭。** 停止新工作，让工作组件收尾并逐步断开，ctx 与存储留到最后完成落盘。

## 3. 包与职责

### 3.1 Python 侧

| 包 | 职责 | 边界 |
| --- | --- | --- |
| `aurora_core` | 内存 ID 登记表、共享 ctx 与持久化基础、事件订阅、插槽连接、最小调用及生命周期 | 不实现 bot、模型、工具或具体流程控制业务；不承担 TOML 加载与配置 schema 策略 |
| `aurora_config` | 配置声明、结构及关联校验、TOML 模板处理与 config 阶段服务 | 基于 core；不承担模型、agent 或业务流程 |
| `aurora_cli` | 启动前 ctx 预配置、命令发现、argv 解析、命令交互 | 不重复实现 ctx 或 bot 业务语义；缺席不影响无 CLI 的装配 |
| `aurora_control` | 执行身份、状态绑定、连接契约与四种控制组合 | 仅依赖 core，不依赖 agent 或模型 |
| `aurora_agent` | ReAct、模型调用、工具执行、默认阶段与运行调度 | 不依赖 bot、CLI 或 API；资源与地址由宿主提供 |
| `aurora_bot` | 默认配置与 TOML 模板、产品装配、资源所有权、运行操作及命令 | 不硬依赖 CLI/API 实现，不直接依赖具体模型 SDK；不复制 agent 的执行机制 |
| `aurora_api` | client 与后端 ctx 交互所需的 HTTP/WS 传输、端点、事件信封及实际需要的契约导出 | 不作为插件接入总线，不预设任意 operation 的远端分发器 |
| `aurora_model_adapter` | ModelClient、能力声明、适配器发现、LiteLLM 与非标接口适配 | 不依赖 bot，不向上层暴露 SDK 类型 |
| `aurora_logging` | 宿主与库共用的日志级别、控制台输出、回溯与文件落盘配置 | 不依赖业务包，不参与 ctx 或插件登记 |
| `aurora_world` | 世界输入与共享环境状态；当前为独立插件骨架 | 不依赖 bot 执行体系；世界变化通过 ctx 与 cadence 联系 |

代码依赖方向为 `core ← config` 与 `core ← control ← agent ← bot`；`model_adapter` 只依赖 core 并被 agent 与 bot 使用。`aurora_harness` 是后续独立项目，目标集合为 core、config、model_adapter、control 与 agent；bot 的配置、默认装配、运行操作和命令不进入 harness 的必需依赖。当前拆包边界与验收记录见 [拆包评估](aurora_agent_extraction_assessment.md)。

### 3.2 TypeScript 侧与静态应用

| 包或应用 | 职责 | 边界 |
| --- | --- | --- |
| `aurora_client` | ctx 访问接口及对应 ID 入口、连接、传输、订阅和所需生成类型 | 复用 core 的 ctx 语义；不重建后端插件系统 |
| `aurora_tui` | 使用 OpenTUI 构建终端对话、配置、ctx 查看与操作 | 通过 client 交互，保留终端界面行为 |
| `aurora_panel` | 使用 Vue 生态构建 Web 对话、配置、ctx 查看与操作 | 通过 client 交互，保留 Web 界面行为 |
| `docsite` | 文档页面、导航与公共 ID 参考 | 独立静态构建，不参与后端装配 |
| `landing` | 项目介绍、导航与品牌资源 | 独立静态构建，不参与后端装配 |

以下 TS 包与静态应用尚未全部建立，保留为设计边界；当前仓库已有 `aurora_client` 骨架以及 `apps/aurora_tui`、`apps/aurora_panel`、`apps/docsite`、`apps/landing` 的入口，业务实现随 M3、M4 推进。

“bot 包保持薄”约束装配职责。默认能力可以作为插件与装配代码同包发布，或以后拆分；命名空间归属不要求与物理代码目录一一对应。

## 4. 命名空间与统一 ID

### 4.1 格式与解释

```text
<namespace>:<domain>/<local_path>
```

`namespace` 标识公开定义归属，`domain` 组织功能，`local_path` 定位对象，可包含多级 `/`。

| 示例 ID | 含义 |
| --- | --- |
| `org.aurora.cli:commands/help` | help 命令入口 |
| `org.aurora.bot:prompts/soul` | soul 提示词资源 |
| `org.aurora.agent:react/prepare` | ReAct prepare 插槽 |

命名空间使用点分隔；域和路径段使用小写 `snake_case`，段内允许数字。不得包含空段、空格、前后斜杠、`.` 或 `..` 路径段。跨组件引用使用完整 ID；交互短名只能在明确上下文中解析，歧义时报错。

ID 不自动映射为文件路径、导入路径、HTTP URL、执行顺序或组件父子关系。`kind` 由登记信息声明，不从路径前缀推断。

### 4.2 命名空间与解析环境

| 包或应用 | 命名空间 | 定义所在环境 |
| --- | --- | --- |
| `aurora_core` | `org.aurora.core` | Python 运行时 |
| `aurora_config` | `org.aurora.config` | Python 运行时 |
| `aurora_cli` | `org.aurora.cli` | Python 运行时 |
| `aurora_control` | `org.aurora.control` | Python 运行时 |
| `aurora_agent` | `org.aurora.agent` | Python 运行时 |
| `aurora_bot` | `org.aurora.bot` | Python 运行时 |
| `aurora_api` | `org.aurora.api` | Python 运行时 |
| `aurora_model_adapter` | `org.aurora.model_adapter` | Python 运行时 |
| `aurora_logging`、`aurora_world` | `org.aurora.logging`、`org.aurora.world` | Python 运行时；当前未登记公共定义 |
| `aurora_client` | `org.aurora.client` | TS 客户端 |
| `aurora_tui` | `org.aurora.tui` | TUI 本地 |
| `aurora_panel` | `org.aurora.panel` | WebUI 本地 |
| `docsite` | `org.aurora.docsite` | 文档构建环境 |
| `landing` | `org.aurora.landing` | 落地页构建环境 |

第三方使用自己的命名空间。`org.aurora.*` 由官方维护；名称表达归属，不构成身份认证或 ctx 访问授权。代码移动不要求 ID 随之变化。

定义所在环境和引用所在环境可以不同。client 可以实现携带既有 ctx 操作 ID 的访问入口，不需要将后端 Python 对象装入 TS 注册表。静态资源和本地视图也不会自动进入 Python 的 ID 表。

### 4.3 对象类型

| kind | 语义 |
| --- | --- |
| `registry` | 接收一类或多类登记项，提供对应接入规则 |
| `operation` | 可调用能力，输入输出按实际需要描述 |
| `component` | 组件定义，指向类或局部执行函数；实例及其端口连接另行创建 |
| `hook_slot` | 组件提供的接入位置，负责判断接入兼容性 |
| `hook_handler` | 可接入插槽的处理实现，即插头 |
| `resource` | 可加载的数据或内容 |
| `service` | 可绑定、注入和管理的服务定义 |
| `schema` | 需要显式维护的数据描述与校验定义 |
| `state_key` | ctx 状态项定义，不建立内部访问隔离 |
| `event` | 可发布、订阅的事件类型定义 |
| `config` | 配置声明，关联非持久状态、结构校验与 TOML 模板 |
| `command`、`adapter`、`assembly`、`endpoint` | 由对应接收方解释的扩展类型 |
| 视图、界面动作、页面、生成契约 | 由本地应用或构建环境解释的类型 |

可寻址不意味着可执行。登记项可以指向函数、插槽对象、资源、服务描述、工厂等，不统一转换为 callable。对象可以附带 schema，也可以通过语言类型、函数签名或双方约定描述接口。

### 4.4 定义与实例

公共 ID 标识定义；同一定义创建的多个对象通过实例标识区分，不以业务数据改变定义身份。执行组件当前使用以下身份：

| 字段 | 用途 |
| --- | --- |
| `definition_id` | 完整 `Id`，组件定义登记为 `component` |
| `instance_id` | 实例身份，默认 UUID，可显式指定非空字符串；同一组件反复取得 plug 保持身份 |
| `run_id` | 一次业务运行，父子调用共享 |
| `execution_id` | 单次调用，每次子调用生成新身份并记录 parent_execution_id |
| `reference` | `definition_id.instance_id` 展示引用；不作为新的 `Id` 解析 |

bot 的 `component_entries` 显式声明组件及其 `/execute` 插头，有子组件时声明 `/children` 插槽。这是插件的命名约定，core 不从路径推断 kind 或运行时父子关系。同一插槽的子 instance_id 唯一；生命周期宿主内的 LifecycleComponent instance_id 也须唯一。

ctx 地址由状态项 ID 和显式业务定位组成。`StateBinding` 在给定 location 上加入 run_id，不自动加入定义或实例身份；需要实例隔离的组件必须在地址约定中表达。控制状态额外使用定义、实例、运行和调用四个字段。地址不建立多租户隔离或并发写保护。

### 4.5 唯一性、覆盖与版本

同一环境、同一登记作用域内，一个完整 ID 对应一个公开定义，不通过改变 kind 复用同一 ID。覆盖、实现选择和替换通过显式装配表达，避免依赖加载顺序。

多个不同 ID 的处理器接入同一插槽是正常扩展；同一定义的多个实例使用实例标识区分。

需要稳定维护的公共接口记录契约版本，包版本与契约版本分别管理。兼容判断由接收方结合接口和实际实现完成，不要求所有局部连接先建立独立版本契约。重命名与不兼容变更显式说明，不做静默猜测。

## 5. ctx、共享状态与存储

### 5.1 运行时数据中心

ctx 是 bot 运行时数据的集散中心，以内存为工作区。所有命名空间均通过显式接口读取和修改共享状态，不按命名空间分配读写权限。

命名空间组织定义、数据归属与目录；跨命名空间修改遵守同样的状态接口和变化通知规则。

### 5.2 统一访问接口

core 提供读取、写入、删除、枚举、订阅和取消订阅等轻量原语。Python 插件使用进程内接口，CLI 使用对应入口，TUI/Panel 使用 client 提供的对应接口。各语言实现共享访问语义，不要求 Python 插件依赖 TS 包。

client 实现 ctx 操作相关的访问入口与 ID 支持，沿用已有 `org.aurora.core:operations/ctx/...` 身份，不为同一动作创建一套同义 ID。后端实际操作、状态变更和通知仍由 core 完成。

所有状态修改经过显式接口，执行实际配置的校验、变化通知及持久化安排。当前读写使用深复制，set 整项替换；外部原地修改读出值或写入参数不能改变内部状态。

list 返回已赋值的精确地址并排序；缺失 get 抛 KeyError，已登记状态项的缺失地址 delete 返回 False。每次成功 set 都通知，即使值相同；失败写入无部分变更。订阅接收后续变化，不回放历史。ctx 限宿主线程访问，同线程单次修改有序，读改写组合不是事务。不为每种局部请求强制创建独立 schema。

### 5.3 自动持久化与运行时对象

需要恢复的数据在运行期间异步自动落盘。正常退出前完成待写入数据及停止过程中最后变更的落盘，再释放相关内存。

当前持久化保存 persistent 状态，并要求严格 JSON 数据；Context.set 本身只执行已配置的状态校验，不保证值一定能落盘。运行时服务对象、连接、函数与任务由装配持有，不进入 ctx。凭证通过运行期参数注入。模型配置与角色绑定使用 `aurora_config` 的非持久配置状态与 `org.aurora.model_adapter:state/config`、`state/bindings`，启动时重建客户端；不建立独立的运行时对象管理器或完整状态分类系统。

ContextPersistence 默认每 0.5 秒合并写入，临时文件写完后替换正式快照；宿主先恢复，再执行 config 阶段，之后 configure 与 prepare/start。异步写入不承诺崩溃零丢失，正常退出由宿主保证最终 flush。业务保留策略由应用决定；controller 清理终态调用，示例清理中间值及历史结果，core 不裁剪完整快照。

配置由 `aurora_config` 声明与加载：插件通过 `ConfigSpec`、`ConfigSchema`、`ConfigTemplate` 与 `config_entries` 声明配置及对应的非持久状态。宿主在恢复业务状态后执行 config 阶段，完成全部文件与关联校验并原子注入 ctx，再执行 prepare/start。TOML 是配置的持久来源，只复制缺失的用户文件，不覆盖已有内容；运行期凭证单独解析，不进入模板、ctx、快照或日志。

### 5.4 命名空间目录与结构化存储

core 的 StorageService 接收宿主显式传入的数据根，提供 `framework/ctx.json` 快照、`framework/structured.sqlite3` JSON KV 存储及插件命名空间目录。存储对象由装配持有，不新增独立公共 ID。

插件可以在分配目录中自主维护数据库，负责模型、索引、事务、连接和迁移。框架不接管数据库内部结构，也不要求数据库内容全部保存为 ctx 内存镜像。

### 5.5 内部共享与客户端数据

内部 ctx 跨命名空间共享。manifest 可以声明数据与能力依赖，但不构成内部访问许可流程。初期不提供同进程恶意插件隔离。

client 获取准备提供给界面的数据，不将整个 Python ctx 无差别序列化。敏感配置和连接凭证不因通用 ctx 接口自动暴露；订阅与错误信息同样遵循实际的数据提供规则。对外访问控制不改变内部共享模型。

本版只确定上述边界，不提前选定完整状态标签、凭证管理或授权系统。监听与认证方式、需要提供的数据范围在实现外部连接时具体确定。

## 6. ID 登记与插件发现

### 6.1 统一内存登记表

core 在当前 Python 运行环境的登记作用域内维护统一哈希表：

```python
definitions: dict[Id, RegistryEntry]
```

`RegistryEntry` 称为“登记项”，描述一个 ID 对应的公开定义，并指向实际对象或加载入口。它与 ctx 中的状态值、某次事件、具体运行实例分开管理。

| 信息 | 用途 |
| --- | --- |
| `id`、`kind` | 定位定义并说明类型 |
| 对象引用或加载入口 | 指向处理器、插槽、资源、服务描述、工厂等实际内容 |
| 提供者信息 | 说明来源及归属 |
| `register_to`、`slot` 等关系 | 按对象需要记录接收方与连接目标 |
| 可选接口描述 | 输入输出、schema 引用、语言类型或其他必要描述 |

上表是概念结构，不冻结字段序列化格式，也不为登记项新增公共 ID。总表中的存在不意味着目标接收方已经存在、连接已经建立或对象正在运行。

commands、hook_slots、resources 等逻辑注册表可以基于总表提供分类索引或视图，并执行各自接入逻辑，不要求各自重复维护完整对象存储。

### 6.2 注册表自举与登记关系

宿主直接创建统一登记表、注册表目录及所需基础定义，随后登记其他对象。自举不要求先通过尚未建立的目录发现自身。

| 注册表 | 登记关系 |
| --- | --- |
| `org.aurora.core:registries/registries` | 由宿主直接引导建立；自身描述是否在目录中列出属于实现选择 |
| core 其余逻辑注册表 | 登记到上述注册表目录 |
| CLI commands、模型 adapters、bot tools/agents/mcp_servers、API endpoints、config 配置声明 | 对应提供方存在时登记到上述目录 |
| TS 本地与静态构建目录 | 在各自环境管理，不自动登记到 Python core |

通用 resources 注册表可以接收 resource、assembly、contract 等已约定类型。登记项保留自己的 kind，由接收方按需要选择加载与校验方式；不因进入 resources 就改成另一种身份。prompt、theme、keymap 等具体内容可附带必要描述，不强制建立完整子类型系统。

### 6.3 声明与可选宿主

声明可以包含 `id`、`kind`、`register_to`、`slot`、`operation`、可选 schema、依赖和排序信息。单个 `operation` 表达一个调用目标；一个端点绑定多个操作时，由端点自身描述各条传输绑定，不要求所有类型共享一个复杂通用字段结构。

```yaml
id: dev.example.memory:handlers/inject_context
kind: hook_handler
register_to: org.aurora.core:registries/hook_handlers
slot: org.aurora.agent:react/prepare
```

此示例只表达关系，ReAct 目标插槽仍为规划入口；不要求特殊连接补齐所有元数据。正式公共接口可以声明双方的输入输出；具体兼容性由插槽提供方判断。

未安装或未启用 CLI/API 时，指向其注册表的声明保留为未连接并输出 warning，不因这些入口缺席而拒绝加载整个插件。插件提供的其他能力仍可使用；未连接声明不会自行产生调用。接收方后来是否可动态启用属于热插拔议题，本版不作要求。

“未连接”不同于已成功建立连接。实际需要调用的目标若缺失，由调用入口或控制组件报告无法执行；不把未连接入口当成可用入口。

### 6.4 发现与装配

1. 宿主建立 core 总表、目录、ctx 及必要基础能力。
2. 读取显式装配清单，并按配置发现 `aurora.plugins` 入口点。
3. 收集定义和连接声明，登记 ID，检查重复身份等基础问题。
4. 已存在的接收方处理登记与连接，按需要判断接口兼容性；缺席的接收方记录 warning 与未连接状态。
5. 选择组件实例、资源与服务，形成当前装配。
6. 执行 config 阶段校验并注入配置，再执行生命周期 prepare/start，工作结束后按依赖逐步停止。

entry point 的 group、名称和导入路径只承担发现职责。实现只检查实际需要的规则，不以“缺少独立契约文件”为理由拒绝可以运行的特殊连接。

## 7. hook、插头与插槽

### 7.1 连接模型

`hook_handler` 表达可接入的处理能力，即插头；`hook_slot` 表达组件预留的接入位置，即插槽；`assembly` 表达组件选择、实例连接及资源和服务绑定。

组件可以同时提供插头与插槽。公共处理器与公共插槽分别拥有 ID，通过显式关系连接；运行时实例连接还应能区分各组件实例，不从 ID 路径或同名关系推导。

control 的 ExecutionPlug/ExecutionSlot 在连接时交换双方 StateBinding 与可选 schema。业务输入输出由实例自行读写 ctx；执行请求仅携带 run_id、execution_id 与父调用身份，返回值不承载业务结果。调用方等待执行来判断结束，订阅 ctx 变化或事件来观察更新；组件可按实际需要订阅变化触发工作，但不默认所有写入都是执行入口。core 的通用调用接口仍可处理普通函数参数与返回值。

### 7.2 接口描述与兼容判断

提供插头和插槽的双方通常各自描述输入输出，已有 schema 时可引用。插槽提供方决定自己能接收什么、是否适配以及怎样执行，core 提供登记、连接和最小调用支持。

| 情况 | 处理方向 |
| --- | --- |
| 双方描述一致 | 接收方按自身规则连接 |
| 描述不同但可兼容 | 允许连接；ExecutionSlot 在双方均提供 schema 且描述不同时输出 warning |
| 无法静态确认兼容 | 接收方可允许尝试并告警，由运行时检验实际行为 |
| 少量特殊连接没有正式 schema | 可以依赖签名、类型、双方约定和实际运行，不强制补契约 |
| 接收方明确无法处理 | 可以拒绝该连接，并说明原因，不将其伪装为成功连接 |

兼容性不等于 schema 文本相等，也不要求 core 建立通用兼容证明系统。双方确实需要适配时，由实际组件完成，不承诺框架自动转换任意数据。

`org.aurora.core:schemas/hook_slot` 保留为可使用的描述入口，不是每个连接必须提供的独立 schema。可复用、第三方实现或跨语言边界出现实际需要时，再提炼并稳定相应描述。

### 7.3 树形装配与控制组件

整体采用类似插排的树形组件组合，从根入口进入，由组件调用连接的子组件。顺序、并行、选择、循环由相应插件实现；core 不实现 ReAct 或通用流程控制业务。

前序遍历可以帮助理解普通顺序组合，不能统一决定所有控制组件的行为。控制组件自行决定子调用、ctx 更新和终止，公共 ID、发现顺序、表格行序均不决定执行顺序。调用结构、共享服务和生命周期依赖分别表达，不要求所有关系构成严格树。

当前 `aurora_control` 插件提供 Controller 基类与四类控制组件：

| 组件 | 行为 |
| --- | --- |
| Serial | 按连接优先级逐个等待，失败或取消停止后续调用 |
| Branch | 选择一个子 instance_id；None 跳过，未知实例报错 |
| While | 前置条件、唯一循环体、显式正整数 max_iterations；达到上限且条件仍真时失败 |
| Parallel | 显式正整数 concurrency 限制异步并发；失败或取消时取消其他任务并等待收尾 |

循环体需要多步骤时接入 Serial；Controller 基类不独立执行。每次调用的控制状态按定义、实例、运行和调用定位，终态通知后删除，不累计历史或调用树。根调用可交给 Lifecycle.run，控制子任务在该调用内收束。

当前代码装配显式登记组件类或局部执行函数，再建立实例连接；普通辅助函数无需登记。默认 bot 通过 DefaultAssembly 和 TOML 配置选择模型、工具与状态地址，不提供完整装配语言或任意执行图。

### 7.4 排序与运行控制

连接和执行依赖由实际装配表达，不从隐藏的 ctx 读写自动推导。当前排序为 priority 从小到大，同值保持连接顺序；before/after 尚未实现。

并行访问共享 ctx 不自动解决写入冲突。取消、超时、错误、结果汇总和追踪按组件实际需要实现，不要求先完成覆盖所有场景的调用契约体系。

### 7.5 生命周期与逐步断开

core 定义 config → prepare → start → stop → clean 五个生命周期插槽。各阶段整体推进：所有 config 完成后才进入 prepare，所有 prepare 完成后才进入 start。config 由配置服务加载和校验，prepare 创建资源，start 开放入口。正常退出按以下顺序执行：

1. 停止接收新的工作。
2. 让在途工作完成或按组件约定停止，逐步结束工作组件。
3. 全部 stop 完成后执行 clean，关闭组件资源、解除连接并完成最后状态写入。
4. 在存储仍可用时完成最终落盘。
5. 关闭存储并释放剩余资源与内存。

关闭顺序依据实际依赖确定，不机械地要求所有资源统一按反向表格顺序关闭。最终落盘是宿主应保证的收尾步骤，不完全依赖某个可禁用 stop handler 的优先级，也不要求每个内置收尾动作拥有公共 ID。

生命周期按显式依赖执行 config/prepare/start，按反向依赖执行 stop/clean；启动失败清理已进入阶段的组件，包含部分配置或准备失败的组件。成功的 stop/clean 处理器不在重试时重复执行。Lifecycle.run 跟踪根调用，组件自行创建的任务由所有者收束。停止或最终落盘失败报告错误并保留可重试资源，不能假报正常退出；新增 HTTP 客户端和工具任务时再验证其取消与关闭边界。

### 7.6 默认 ReAct 与扩展

aurora_agent 提供 ReActAgent 和 prepare、infer、act、observe、finish、error 六个阶段插槽。ReActDefaults 将上下文构建、ModelCall、响应解释、ToolExecutor 与观察接纳显式连接到工作阶段；finish/error 可不连接处理器。ModelCall 的组件定义为 `org.aurora.agent:handlers/model_call`。

ReActAgent 负责一次激活内的迭代、决策和终止，循环上限为正整数；控制组合只负责外层调用结构。AgentRuntime 管理提交、激活、等待和取消，通过宿主提供的 agent 获取、执行和占用查询接入；运行句柄仅存在于进程内。默认装配在启动后绑定 runtime；恢复出的中断运行标记为 failed，不自动续跑。

引导采用实例级 inbox、progress 和 runtime 地址，宿主通过 StateBinding 与 InstanceStateBinding 提供。默认过程在推理前接纳引导，在结束前检查待处理输入。工具、多模型选择与聚合、agent 通信及 MCP 由 bot 插件提供，模型执行使用注入的 ModelClient；core 不增加对应业务机制。

## 8. 模型适配与绑定

`aurora_model_adapter` 提供 ModelClient/ModelFactory 协议、JSON 请求/响应/流式片段、能力声明、ResponseBuffer 与确定性 FakeModel。插件登记 adapters 注册表、model_client 服务与四个模型 schema。LiteLLM 适配器已实现并按需启用；FakeModel 无需网络或密钥，没有独立 adapter ID。

装配选择适配器、连接配置和逻辑模型角色，创建服务实例并注入组件。同一服务定义可以绑定多个实例，不通过修改公共服务 ID 区分具体模型。模型 profiles、角色 bindings 与默认 bot 配置使用包内 TOML 模板；用户文件位于 `<data-dir>/config/<命名空间>/`，只复制缺失文件并保留用户内容。凭证只保存环境变量名称，运行期解析且不写入 ctx。

ModelClient 提供异步 complete、通过 async with 消费的 stream，以及 aclose。ModelFactory 异步接收 ModelConfig 和单独的 api_key 参数；工厂加载与角色绑定恢复已接入默认装配。能力包含 streaming、tool_calls，能力不足明确拒绝，不自动降级。SDK 类型不上泄，不增加独立工厂 schema ID。

模型数据使用 TypedDict 表达普通 JSON。文本按 text chunk 增量输出；工具名称与 JSON 对象参数由适配层组装成完整 ToolCall 后输出，bot 不接收半截 JSON。ResponseBuffer 只保存累计结果，要求唯一且最后的 finish，缺失结束片段明确失败。结束原因区分 stop、tool_calls、length、content_filter，不将模型响应结束等同于对话完成。

`aurora_agent.model` 的 ModelCall 从约定 ctx 地址读取请求，在同一输出地址更新 status、execution_id、text、tool_calls、finish_reason。失败或取消保留已收到的部分文本并标记 failed/cancelled，错误继续传播，不保存片段历史。完整响应接口在返回前不提供部分文本。

单次响应流由调用组件关闭；共享客户端由创建它的装配在所有调用结束后关闭。同一输出地址须串行调用，组件不保证共享客户端任意并发安全。ModelCall 的 completed 只表示该模型请求完成，工具执行与下一轮推理由后续装配实现。连接配置与绑定恢复沿用 TOML 和状态地址，不增加独立配置／秘密／对象管理子系统。

## 9. CLI、API 与事件传输

CLI 将 argv 转为对应接口使用或操作调用，不重复实现 ctx 与 bot 行为。bot 可以在自己的命名空间声明命令、端点等入口，引用 CLI/API 的公开注册目标；这不要求导入或安装它们的实现。

当前 CLI 提供 ctx 读写、观察、`id list`、`run` 和 bot 的 `run submit` / `run activate` / `run cancel`。`run` 启动选定装配后等待取消；提交类命令在本次进程内完成一次提交、等待运行收尾并输出流式 JSON，然后退出。运行中的外部输入与界面关联仍待 M3 的 D10 决策，本版不提供常驻提交通道。

API 为 client 提供后端连接和 ctx 访问所需传输，不作为插件扩展总线。API 可以提供明确需要的额外端点，但不预设统一的任意 operation 远端调用系统，也不要求先经过 CLI 描述才能实现 ctx 传输。

URL、HTTP 方法和 WS 消息由具体端点实现描述，不从 ID 自动推导。一个端点可以提供多条绑定，按实际需要说明各自的传输入口和处理目标；不强制为每个端点新增正式 schema ID。

core 的事件机制负责进程内发布订阅，ctx 变化订阅属于 ctx 接口；client 封装界面需要的订阅与连接管理，API 承担事件传输。沿用原事件类型 ID，传输层可以补充请求关联、来源和序号等信息，不另建同义业务事件身份。

不因存在 WS 就要求新增一组通用订阅 operation。订阅标识、取消、连接断开与重连行为在实现实际客户端需求时明确，本版不承诺事件历史补发或断线零丢失。

## 10. client 与界面

### 10.1 共享 ctx interface

| 使用方 | 接口实现 | 实际数据操作位置 |
| --- | --- | --- |
| Python 插件 | 进程内 ctx 接口 | core |
| CLI | 命令映射至对应接口 | core 或实际业务组件 |
| TUI、Panel | client 的 ctx 接口 | 通过传输到后端 core |

统一 interface 表示共享访问语义，不表示 Python 与 TS 必须导入同一份代码。client 实现对应 ctx ID 的访问入口、参数传递、结果接收和订阅；不将后端 callable、服务对象或插件执行树复制到前端。

### 10.2 界面动作边界

TUI 使用 OpenTUI，Panel 使用 Vue 生态；两者通过 client 交互，各自维护本地视图、动作、主题、键位与偏好。

消息提交、取消等界面动作保留既有公共 ID，但本版不决定它们如何与 bot 执行发生联系。特别是不预设“写入某个 ctx 输入项就触发运行”，也不要求通过 bot operation 或 conversation 端点发起。相关机制属于后续 bot 设计讨论。

既有 bot send/cancel operation 和 conversation 端点保留为规划定义，不表示它们是 TUI/Panel 必经入口；界面动作与它们之间没有本版强制建立的绑定。该决策记为 D10，最迟在 M3.6 界面动作联通前完成；当前 bot 的 `run submit/activate/cancel` 是进程内运行入口，不构成界面提交协议。

### 10.3 按需生成

跨语言实际使用的数据结构以维护的后端公开描述为来源，可以从 Python 类型、Pydantic、OpenAPI 或 WS 描述生成 TS 类型与 ID 常量。只导出需要且可传输的部分，不要求将全部 Python 登记项导出给客户端，也不强制每个局部接口加入生成链路。

当前本机 ctx 协议由 [aurora_api.contract](../packages/aurora_api/src/aurora_api/contract.py) 描述，通过 `uv run --locked python scripts/generate_ctx_contract.py` 生成 client 的 JSON 描述与 TS 类型、绑定常量；增加 `--check` 可只读检查产物。生成不启动宿主，不导出业务配置或模型 SDK 类型。M3.5 的共享 CtxClient 已复用这些绑定提供访问与订阅；重连先订阅再重新读取状态，刷新期间有界缓存变化，界面可观察连接及刷新状态。多次 HTTP 读取不构成原子快照，客户端不重放 HTTP 动作，也不将本地关闭解释为取消 agent。

开发时可使用 Vite 代理 API，生产环境优先同源部署。认证与外部访问配置随实际连接方案确定。同源安排不代替访问控制。docsite 与 landing 独立构建。

## 11. 依赖方向与目录

代码依赖和 ID 引用分别表达：引用一个接收方的公开 ID 不要求导入它的实现；缺少接收方按未连接告警规则处理。显式使用某个 Python 协议类型时，才建立对应代码依赖。

| 使用方 | 代码依赖方向 | ID 引用与连接 |
| --- | --- | --- |
| `aurora_core` | 通用基础依赖 | 不依赖业务包；维护当前后端总表 |
| `aurora_config` | core | 提供配置声明、校验、模板与 config 阶段服务 |
| `aurora_model_adapter` | core | 提供适配器和 ModelClient 定义 |
| `aurora_control` | core | 提供执行契约、控制组合与控制状态 |
| `aurora_agent` | core、control、model_adapter | 提供 ReAct、模型调用、工具执行与运行调度 |
| `aurora_bot` | core、control、agent、model_adapter | 可声明面向 CLI/API 的入口，不硬依赖其实现 |
| `aurora_cli` | core、api | 接收已启用的命令声明，不导入 bot 插件实现 |
| `aurora_api` | core；按实际需要复用 CLI 公开适配描述 | 提供 client 传输；不强制经过 CLI，不导入 bot 插件实现 |
| `aurora_logging`、`aurora_world` | core；按实际需要 | 当前分别提供日志配置与世界插件骨架，未登记业务定义 |
| `aurora_client` | TS 传输与所需生成类型 | 实现统一 ctx 接口和既有 ctx ID 入口 |
| `aurora_tui`、`aurora_panel` | client | 使用 ctx interface，不参与后端插件装配 |
| `docsite`、`landing` | 各自构建依赖 | 独立解析页面和资源 |

Monorepo 使用 Python `uv workspace` 与 TypeScript `pnpm workspace`，Python 包采用 src-layout。

| 路径 | 内容 |
| --- | --- |
| `packages/aurora_core/` | 微内核 |
| `packages/aurora_config/` | 配置声明、校验与 TOML 加载 |
| `packages/aurora_control/` | 执行契约与控制组合 |
| `packages/aurora_agent/` | ReAct、模型调用、工具执行与运行调度 |
| `packages/aurora_model_adapter/` | 模型适配 |
| `packages/aurora_bot/` | 默认装配、配置与产品入口 |
| `packages/aurora_cli/` | CLI |
| `packages/aurora_api/` | 后端传输 |
| `packages/aurora_logging/` | 日志配置 |
| `packages/aurora_world/` | 世界输入与共享环境状态骨架 |
| `packages/aurora_client/` | TS 共享 ctx 访问与连接 |
| `apps/aurora_tui/`、`apps/aurora_panel/` | 终端与 Web 界面 |
| `apps/docsite/`、`apps/landing/` | 静态应用 |
| `scripts/` | 开发与按需生成脚本 |
| `tests/unit/`、`tests/contract/`、`tests/e2e/` | 按实际行为与边界组织验证 |

## 12. 初期非目标

- 不设计多租户运行或记忆隔离，不按插件命名空间授权内部 ctx。
- 不实现插件热插拔或进程级恶意插件沙箱。
- 不为所有对象强制创建独立 schema、契约版本或公共 ID。
- 不建立任意后端 operation 的通用远端分发体系。
- 不将 TUI/Panel 设计成后端插件宿主。
- 不提前实现完整状态分类、凭证管理、兼容证明或退出协调框架。
- 不要求初期完整 MCP、所有界面功能对齐或复杂多发行版管理。
- `aurora_playground` 继续保留为后续包扩展：消费指定实例与输入输出接口，装配输入、输出插头；本版不增加包依赖或正式 ID。

## 13. 初期里程碑

| 阶段 | 交付范围与需要明确的最小行为 |
| --- | --- |
| M0 骨架 | Monorepo、ID 格式、统一登记项与总表、自举、逻辑注册表、未连接告警；按需接口描述的表达方式 |
| M1 微内核可用 | 显式 ctx 操作及其当前用例所需行为、变化订阅、异步落盘、逐步关闭与最终落盘、插槽连接与调用、CLI 基础入口 |
| M2 最小 bot | 默认装配、控制组件、单模型 ReAct、ModelClient、LiteLLM、TOML 配置与绑定恢复、基本工具路径、运行提交与取消 |
| M3 client、API 与 TUI | ctx interface、HTTP/WS 传输、实际订阅和重连行为、需要的生成类型、界面数据范围与连接访问控制、OpenTUI 界面 |
| M4 能力扩展 | 多模型、agent 通信、MCP、Vue Panel、文档站与落地页 |

各阶段记录已经实现的可观察行为，避免同一接口出现互相矛盾的实现；不以冻结所有规划契约作为启动下一阶段的前置任务。消息提交与取消等 bot 交互机制另行讨论，本表不替代该设计。

当前 M0、M1、M2 已完成；M2.8 于 2026-10-31 通过整体验收（默认装配、模型协议与适配、ReAct 工具循环、公共运行操作、CLI 观察及关闭恢复）。M3 尚未开始，D08、D09、D10 仍待决策；M4 未进入实现。附件区分当前定义与规划身份，不表示所有对象均已加载或对外提供。

## 14. 后续讨论

1. **界面动作关联（D10）。** send 的返回与等待、忙碌与重复提交、取消竞态、遗留运行处理，以及界面动作通过何种机制关联运行；M3.6 前完成。
2. **client 连接（D08、D09）。** 对外数据与访问边界、传输订阅、信封、断线重连、慢消费者和重新获取状态策略。
3. **独立 harness。** 复用 core、model_adapter、control 与 agent，定义自己的装配、配置、资源与恢复策略、交互入口和发布边界；不复制 bot 的默认配置或 CLI 命令。
4. **世界与 cadence。** `aurora_world` 作为并行接入根生命周期的插件维护世界状态；cadence 订阅选定地址并把引导写入 agent 的 inbox。完整唤醒工具与子代理仍属后续切片。
5. **公共接口维护。** 从实际边界提炼必要的 schema、兼容与迁移规则，不预设通用证明系统，不以规划 ID 证明接口已经冻结。

## 15. 变更记录

### 15.1 v0.2.3

- 执行能力拆分为平级的 `aurora_control` 与 `aurora_agent`：control 承载执行契约和四种控制组合，agent 承载 ReAct、模型调用、工具执行、默认阶段与运行调度；`aurora_bot` 保留配置、默认装配、资源所有权和产品入口。
- 公共 ID 与插件入口按包归属：control 使用 `org.aurora.control`，agent 使用 `org.aurora.agent`；发现分组为 `aurora.plugins`，运行时不提供旧导入路径、旧插件名或旧 ID 别名。
- AgentRuntime 通过宿主提供的 agent 获取、执行与占用查询连接，不再访问 `DefaultAssembly` 私有成员；运行句柄仍只存在于进程内。
- 补充 M2 已完成状态：LiteLLM 适配、TOML 模型 profiles 与角色绑定、基本工具往返、CLI `run submit/activate/cancel`、取消与重启恢复均已验收；M3 与 D10 尚未开始。
- 配置声明、结构校验、TOML 模板与 config 阶段服务归属 `aurora_config`；core 保留通用状态、持久化与生命周期机制。
- 明确独立 harness 的目标集合为 core、model_adapter、control 与 agent，并记录拆包边界、测试与后续工作。
- 同步包职责、命名空间、依赖方向、目录与里程碑；补充 `aurora_logging`、`aurora_world` 的当前边界。

### 15.2 v0.2.2

- core 明确维护 `Id → RegistryEntry` 内存哈希表；逻辑注册表可基于总表提供视图与接入行为，定义、实例、状态值分别管理。
- 明确可选 CLI/API 接收方缺席时保留未连接声明并告警，不因此阻断整个插件加载。
- 接口由双方按需描述，兼容性由提供插槽的一方判断；允许描述不同但兼容或缺少正式 schema 的特殊连接。
- 取消每个对象必须有正式契约的暗示；不因复核意见批量新增公共 schema、订阅 operation 或内置 handler ID。
- 明确 client 实现统一 ctx 访问入口和对应 ID 支持；插件走进程内接口，TUI/Panel 通过 client 交互，HTTP/WS 只承担传输。
- 保留既有 bot operation 与端点 ID，但移除界面动作必须调用它们的预设；消息提交与取消机制留待后续讨论。
- 状态与运行时对象管理保持待讨论，只确认需要恢复的数据落盘、运行时连接不直接落盘以及界面数据不全量导出。
- 明确类似插排逐步断开的退出顺序，最后写入完成后落盘，再释放存储和剩余资源。
- 同步依赖说明、里程碑和配套目录，沿用既有公共 ID 与 kind。

### 15.3 v0.2.1

- 明确个人单租户、唯一 bot 后端、多客户端与内部共享 ctx。
- 明确内存工作区、显式变更、异步持久化和正常退出收尾。
- 移除内部命名空间授权前提，补充目录与插件数据库边界。
- 明确插头／插槽、树形装配和插件流程控制；TUI 使用 OpenTUI，Panel 使用 Vue 生态。

### 15.4 v0.2

- 在 ctx/hook、插件发现和包边界基础上加入统一命名空间 ID。
- 区分定义与实例、插槽与处理器、命令／端点与操作。
- 完整公共 ID 表独立保存为附件。
