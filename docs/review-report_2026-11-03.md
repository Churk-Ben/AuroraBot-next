# AuroraBot 设计一致性审查报告

日期：2026-11-03

审查基线：提交 `8b46dd2`。审查期间工作区已出现未提交的 MCP 通用接入改动，本报告不以这些改动为审查对象；涉及 MCP 的结论以基线代码为准，后续实现应重新核对。

参考材料：

- [设计文档 v0.2.3](aurorabot-design-v0.2.3.md)
- [公共 ID 目录 v0.2.3](aurorabot-id-catalog-v0.2.3.md)
- [里程碑与编码计划](plan.md)
- [MCP 通用接入设计草案](mcp_unified_access_design.md)
- [执行包拆包评估](aurora_agent_extraction_assessment.md)
- 当前 `packages/`、`apps/`、`tests/` 实现

审查方式：静态阅读、插件登记导出、定向与全量测试、Python 类型检查、生成契约检查。未修改实现，未调用真实模型或外部平台。

## 1. 结论

总体判断：**项目基本贯彻了设计思想，没有发现方向性跑偏。**

- `core` 仍然只是微内核，没有混入 bot、模型、MCP 或业务流程机制。
- `bot → agent → control → core` 的代码依赖方向成立；`agent` 没有反向依赖 `bot`、CLI、API 或 world。
- ID、实例、运行、调用、状态值的分层基本清楚；`ctx` 的深拷贝、整项替换、精确地址、订阅不回放等语义与设计一致。
- 生命周期、最终落盘、可选宿主缺席、按需 schema、接收方判断兼容性等原则都有实际代码和测试支撑。
- 文档对“已交付”和“规划中”的区分总体诚实，计划中明确列出了 B5、B3、cadence、Panel、远程认证等未完成项。

真正需要投入的不是重写架构，而是**边界治理**：

1. 少数“只读/追加”状态被通用 ctx 写接口暴露。
2. `DefaultAssembly` 仍承载了本应属于 agent/harness 的运行恢复与状态裁剪语义。
3. 世界记录、MCP 来源和对话上下文缺少长期运行的保留上限，快照与内存会随消息增长。
4. TUI 直接复刻了后端 `react_work` 的内部结构，绕过了按需契约。
5. 文档依赖表与实际依赖、公共 ID 目录与实际登记存在漂移。

## 2. 设计原则对照

| 设计原则 | 判断 | 主要依据 |
| --- | --- | --- |
| core 只做通用机制 | 良好 | `core` 仅登记、ctx、事件、连接、调用、生命周期、持久化；无业务导入 |
| bot 装配能力，不另造机制 | 部分 | 装配总体成立；`DefaultAssembly` 仍承载恢复、裁剪和第二激活路径 |
| 公开对象统一寻址 | 良好 | 实际登记 108 个定义均可在 ID 目录中找到；未发现代码独有的隐藏 ID |
| 接口按需明确 | 部分 | 核心边界清楚；TUI 复刻 `react_work` 内部字段，未进入生成契约 |
| 连接由提供插槽的一方判断 | 良好 | `HookSlot.accept` 可选，schema 不同但接受时仅告警 |
| 缺少接收方允许未连接 | 良好 | `inspect_admissions` 区分 accepted/unconnected/rejected 并告警 |
| 统一 ctx 访问语义 | 良好 | Python/CLI/TS client 共用既有 ctx 操作 ID；API 无任意 operation 转发 |
| 模型适配透明 | 良好 | 模型报文与 SDK 类型限制在 `aurora_model_adapter`；agent 只消费协议 |
| 共享状态与显式变更 | 良好 | 深拷贝、set 整项替换、失败无部分变更、订阅不回放 |
| 身份与实例分离 | 部分 | 执行身份清楚；MCP 把运行时 ctx/clients 写回注册定义，削弱了定义/实例分离 |
| 按连接与依赖逐步关闭 | 良好 | config→prepare→start→stop→clean；依赖正序启动、反序关闭；最终 flush 后才释放存储 |
| 单租户、单后端、多界面 | 良好 | API 只监听回环；TUI 偏好留本地；未引入多租户隔离 |
| 不提供任意远端 operation | 良好 | API 仅注册固定 ctx 动作与显式产品端点；测试覆盖 `/operations/invoke` 不存在 |
| 不热插拔工具集合 | 良好 | MCP 工具目录变化要求重建宿主，未在运行中增删工具 |

## 3. 做得好的地方

1. **依赖方向有测试和安装验收兜底。** `control` 只依赖 `core`；`agent` 只依赖 `core`、`control`、`model_adapter`；`bot` 不导入 `aurora_api`/`aurora_cli`；`adapters` 的 MCP 消费者按 extra 隔离。`tests/e2e/test_package_boundaries.py` 还验证了无 bot 环境下的 agent 往返。

2. **ctx 语义落实细致。** `Context` 的 get/set 都做深拷贝，set 整项替换，list 返回已赋值地址并排序，缺失 get 抛 `KeyError`，delete 缺失返回 `False`，同值写入也产生新修订，失败写入无部分变更。订阅只接收后续变化，不补发历史（`packages/aurora_core/src/aurora_core/ctx.py`）。

3. **生命周期与最终落盘顺序正确。** config、prepare、start 按依赖顺序执行；stop、clean 反序执行；`ContextPersistence.close()` 成功 flush 后才解除订阅；启动失败和停止失败都有保留资源、可重试的路径（`packages/aurora_core/src/aurora_core/lifecycle.py`、`persistence.py`）。

4. **执行契约干净。** control 的执行请求只携带 `run_id`、`execution_id`、`parent_execution_id`；业务状态通过 `StateBinding` 读写；ReAct 六阶段、Serial、Branch、While、Parallel 都在 control/agent，core 没有业务流程控制。

5. **公共 ID 与插件发现总体一致。** 本次导出实际登记的 108 个定义全部能在 ID 目录中找到；没有发现“代码已登记、文档完全没有”的 ID。插件 `requires` 只校验显式启用的依赖，不隐式加载。

6. **生成契约可重复检查。** `scripts/generate_ctx_contract.py` 合并 API、bot、config 的显式描述，生成 TS 类型和绑定；`--check` 本次返回 0，说明生成产物与后端描述一致。

## 4. 发现与建议

### F1. 世界记录通过通用 ctx 白名单开放了写操作

**严重度：高**

**证据：**

- `scripts/serve_bot.py:30-32` 在 `--world` 时把 `org.aurora.world:state/records` 放进 `--keys`。
- `packages/aurora_api/src/aurora_api/server.py:65`、`:94-102`、`:180-183` 对同一个 `--keys` 集合开放 get、list、set、delete。
- `apps/aurora_tui/src/ui/pages/status.ts:75-85` 会把该记录展示出来；`apps/aurora_tui/src/state/editor.ts:64-69` 允许对它执行整项替换或删除。
- 设计文档第 372 行明确写“宿主不能用通用 ctx 写入改写历史”，并规定世界记录追加、去重与裁剪应在一次提交中完成。

**为什么是偏离：** 世界记录是带 `journal_id`、单调 `next_sequence`、`pruned_through` 的追加语义日志。API 的 `--keys` 只有“键级”粒度，没有区分读键和写键；一个客户端可以提交一份结构合法但内容伪造的日志，或直接删除历史。`validate_records` 只能保证结构合法，不能证明写入者经过 `WorldRecords.append`。

**建议：**

- 把 API 的开放集合拆成 `read_keys` 与 `write_keys`（或 per-key actions 白名单），至少让 `RECORDS`、`SOURCE_STATUS`、`CLIENT_STATUS` 只读。
- TUI 状态页对只读地址禁用 F6/Ctrl+D，或由服务端返回可写标记。
- 补契约测试：对 `RECORDS` 的 set/delete 必须返回 403；只读语义在生成契约中也有体现。
- 如果短期内必须保持单白名单，至少在 `serve_bot.py --world` 的帮助文本和启动日志中明确“开放了世界记录写入”，不要把它描述成“只开放观察”。

### F2. TUI 直接复刻后端 `react_work` 内部结构，绕过按需契约

**严重度：高**

**证据：**

- `apps/aurora_tui/src/state/workbench.ts:17-21` 硬编码 `org.aurora.bot:state/messages`、`state/run`、`state/react_work`。
- 同文件 `:249-263`、`:298-347` 直接解释 `model_output`、`tool_calls`、`tool_current`、`tool_results`、`turn_id`、`execution_id`、`call_id` 等字段。
- 设计第 10.3 节要求跨语言实际使用的数据结构以后端维护的公开描述为来源，生成 TS 类型与 ID 常量；第 10.1 节要求 client 实现访问入口，而不是把后端对象/执行树复制到前端。

**为什么是偏离：** 这些 `react_work` 字段是 bot/agent 的工作状态布局，不是已生成的传输契约。后端一旦调整字段名或嵌套结构，TUI 不会在类型检查或契约检查中失败，只会在运行时静默少显示工具活动或运行状态。

**建议：**

- 把界面实际需要的状态键和视图 DTO 纳入生成契约，至少生成 `BOT` 状态 ID 常量和 `react_work` 的只读投影类型。
- 或者由后端提供一个稳定的 UI 投影（例如 `state/ui`），TUI 只消费投影，不解释内部工作地址。
- 为字段映射增加契约测试，避免后端字段变化只被人工发现。

### F3. `DefaultAssembly` 仍是跨职责上帝类，且存在第二套激活路径

**严重度：高**

**证据：**

- `packages/aurora_bot/src/aurora_bot/assembly.py:54` 的 `DefaultAssembly` 同时管理模型客户端、`ReActAgent`、`ReActDefaults`、配置、工具定义、工具实例、执行连接、`AgentRuntime`、`RunOperations`、接受/执行状态和最近请求。
- 同文件 `:280-293` 的 `_activate()` 直接调用 `agent.execute()`；`:274-278` 的 `activate()` 是绕过 `AgentRuntime` 的显式激活入口；`runtime.py:119` 需要专门兼容“显式激活正在执行”的情况。
- 同文件 `:295-318` 的 `_compact()` 直接读写 `agent.inbox`、`agent.pending`、`defaults.model.output_state`、`defaults.tools.output_state`，并在 `_activate` 的 `finally` 中无条件执行。
- 设计第 7.6 节写“`AgentRuntime` 管理提交、激活、等待和取消”；AGENTS.md 写“每个 agent 实例只有一个调度所有者”；拆包评估第 4.3 节明确建议把中断运行修正、pending 工具结果保留、inbox 裁剪提取为可复用的装配辅助。

**为什么是偏离：** `bot` 仍承载了 agent 的运行语义和状态保留策略。虽然显式激活与 runtime 路径通过 `AgentBusyError` 做了互斥，但“两个入口 + 兼容分支”会持续增加并发、取消和恢复的验证面积；harness 若复用 agent，只能复制这套逻辑。

**建议：**

- 把恢复修正、pending 工具结果保留、inbox/progress 裁剪、WORK 清理提取为 `aurora_agent` 的恢复/裁剪 helper；宿主只提供状态地址和保留策略。
- `DefaultAssembly.activate()` 改成 `runtime.activate()` + `handle.wait()` 的薄封装，或直接删除；`_compact` 的 inbox 写入改走受保护的 runtime 接口。
- `_compact` 不应在 `finally` 中覆盖原始异常或取消；清理失败应记录日志并附加 note，保留原始终态可观察性。
- 按职责拆出 `ModelResources`、`ToolOwnership`、`BotRuntimeHost`，让 `DefaultAssembly` 回到“选择与连接”的薄装配。

### F4. 世界记录、MCP 来源和对话上下文缺少长期运行上限

**严重度：高**

**证据：**

- `packages/aurora_world/src/aurora_world/records.py:174-327` 每次 append/read 都复制完整日志，日志整体保存在 `org.aurora.world:state/records`。
- `packages/aurora_core/src/aurora_core/persistence.py:79-114` 每 0.5 秒对完整 ctx 做快照并写入。
- `packages/aurora_adapters/src/aurora_adapters/mcp/world.py` 的 MCP 来源没有声明 `RecordRetention`；`packages/aurora_bot/src/aurora_bot/assembly.py` 的 `ReActDefaults` 也没有裁剪 `state/messages`。
- 设计第 5.3、7.7 节把保留策略交给应用，但默认 bot 没有给出可配置的上下文窗口或消息上限。

**为什么是偏离：** 设计允许“应用决定保留策略”，但默认产品路径没有策略，实际会表现为：

- 世界日志随 QQ/环境/MCP 消息线性增长，append 的深拷贝成本随历史长度上升。
- 每次自动落盘都要序列化全部世界记录和全部对话消息。
- 模型上下文无限增长，最终触发供应商上下文长度限制或显著增加调用成本。

这不是立刻崩溃的 bug，但会在长期运行时成为主要瓶颈。

**建议：**

- 为 MCP/外部来源增加默认 `RecordRetention`（可按数量或时间），并在配置模板中暴露。
- 为 bot 增加可配置的消息上下文窗口/裁剪策略，至少保留 system、最近 N 轮和未完成工具轮次。
- 评估把 world journal 放到 `StorageService` 的结构化存储中增量写入，ctx 只保留有界窗口；如果暂时不做，至少在文档和启动日志中说明“首版面向有限规模输入”。
- 为 append 的复杂度补性能基线，避免在未测量前做大规模存储重构。

### F5. MCP world/tools 把运行时绑定写回公共定义，失败/关闭无回滚

**严重度：中高**

**证据：**

- `packages/aurora_adapters/src/aurora_adapters/mcp/world.py:262-270` 的 `_WorldFactory` 是注册在 `SOURCES` 中的定义对象；`:283-294` 的 `mcp_world_component()` 直接把当前宿主的 `(ctx, clients)` 写入 `spec.factory.binding`，并拒绝第二次绑定。
- `packages/aurora_adapters/src/aurora_adapters/mcp/tools.py:182-235` 在 prepare 阶段把 `ToolSpec` 和持有 `MCPTools`/客户端的 `_Factory` 注册到全局 `TOOLS`；`:150-159` 的 `component()` 只连接 PREPARE，没有 CLEAN 或回滚。
- 设计第 6.1、7.1、7.3 节要求定义与实例分开管理，实例连接由装配显式建立；第 7.5 节要求启动失败清理已进入阶段的组件。

**为什么是偏离：** 公共登记项现在持有宿主级可变状态（Context、MCPClients、工具工厂）。同一个进程里第二次装配、启动失败后重试、或多宿主测试都会遇到“已经绑定所有者”“工具定义仍指向已关闭客户端”等问题。当前单宿主正常退出时不一定暴露，但会限制 harness、多实例和后续 B5 产品装配。

**建议：**

- 让 `mcp_world_component()` 创建带客户端绑定的独立来源工厂实例，或通过 `WorldSources` 的显式构造参数注入客户端，不要修改已注册的 `SourceSpec`。
- `MCPTools` 先构建临时目录，全部校验后原子登记；在 CLEAN 中撤销本次登记，或由 assembly 持有工具 spec 并负责释放。
- 增加“发现成功但 bot 准备失败”“同一进程第二次装配”“关闭后重新装配”的测试。

### F6. TUI 的 `RunGroup` 缺少实例身份，取消可能发到错误实例

**严重度：中高**

**证据：**

- `apps/aurora_tui/src/state/workbench.ts:42-51` 的 `RunGroup` 只有 `id`、`session`，没有 `instance_id`。
- 同文件 `:269-296` 的 `group()` 只按 `id + session` 查找；`:97-121` 的 `cancel()` 使用 `this.instance` 作为目标实例。
- `packages/aurora_client/src/conversation.ts` 与 bot 契约都要求 `session_id/instance_id/run_id`；`ConversationEndpoint` 支持多个 `instance_ids`。

**为什么是偏离：** 设计第 10.2 节要求停止作用于指定 `instance_id/run_id`。当界面从旧实例切到新实例时，旧运行分组仍留在 `groups` 中，其 `session` 可能相同，`cancel()` 会把旧 `run_id` 配上新 `this.instance`，得到 404 或错误取消结果。

**建议：**

- 在 `RunGroup` 中保存回执/`react_work` 给出的 `instance_id`；取消、查询、展示都使用该值。
- 实例切换时隔离或清理旧实例分组，不要只依赖 `session`。
- 增加“两个实例、旧分组仍在、切换后取消”的回归测试。

### F7. 文档写“远程 ctx 访问已实现”，实现只监听回环

**严重度：中**

**证据：**

- 设计第 446 行写“远程 ctx 访问与 M3.6 直接交流已实现”。
- 同文档第 561、566 行又写“浏览器与远程访问待补齐”“按浏览器和远程接入需要补齐认证、来源与数据范围”。
- `packages/aurora_api/src/aurora_api/server.py:82` 拒绝任何非 `127.0.0.1`/`localhost` Host；`:211` 只绑定 `127.0.0.1`。

**为什么是偏离：** 当前交付的是本机传输；TS client 可以配置任意 `http(s)` URL，只是客户端能力，不等于服务端已支持远程接入。第 446 行的表述会让读者误判认证、来源和数据范围已经就绪。

**建议：**

- 把第 446 行改为“本机 ctx 访问与 M3.6 直接交流已实现；远程监听与认证待 D08”。
- 若确实要宣称远程访问，需要同时实现外部监听、认证、Origin 策略、敏感字段边界和对应测试。

### F8. 浏览器/同源 Panel 路径尚未打通

**严重度：中**

**证据：**

- `packages/aurora_api/src/aurora_api/server.py:82` 只要请求带 `Origin` 就返回 403。
- `packages/aurora_client/src/transport.ts` 的 HTTP 请求只发送 `Content-Type`，没有 token/Authorization 选项。
- 设计第 494 行写“开发时可使用 Vite 代理 API，生产环境优先同源部署”。

**为什么是偏离：** 现代浏览器对 POST 通常携带 `Origin`，当前中间件会直接拒绝；如果依赖代理剥离 Origin，又需要未文档化的代理行为。Panel 即使同源部署，也缺少认证/CSRF 边界。

**建议：**

- 增加精确 Origin 白名单与 token/CSRF 机制，或明确要求可信同源代理并补充认证。
- 在开放 Panel 前用真实浏览器请求补测试，不要只用 Node 客户端验证。

### F9. 文档依赖表与实际 pyproject 漂移

**严重度：中**

**证据：**

- 设计第 3.1 节、第 11 节写 `aurora_model_adapter` 仅依赖 core；实际 `packages/aurora_model_adapter/pyproject.toml` 依赖 `aurora-config`，`configuration.py:7` 和 `plugin.py:3` 直接导入 config。
- 设计第 11 节写 `aurora_cli` 依赖 core、api；实际 `packages/aurora_cli/pyproject.toml` 还依赖 `aurora-config`、`aurora-logging`，`commander.py:9,15` 直接导入。
- ID 目录第 3 节把 `org.aurora.bot:registries/agents` 列为“已实现”，但 `aurora_bot/assembly.py` 的 `plugin()` 没有登记该注册表。

**为什么是偏离：** 依赖表是拆包与安装验收的依据。当前实现选择了“模型配置硬依赖 config”“CLI 内置 config/logging”，但没有同步设计；独立 harness 目标（core、model_adapter、control、agent）因此与文档不一致。

**建议：**

- 把模型 profiles/bindings 的配置声明拆到可选 `aurora_model_adapter.configuration`，或更新设计依赖表并补“无 config 的独立模型适配包”安装验收。
- 把 CLI 对 config/logging 的依赖写入设计表和安装矩阵；如果 CLI 必须内置配置，明确它是宿主基础设施而不是隐式插件。
- 修正 ID 目录：`bot:registries/agents` 标注为规划，或在 M4-A 实现时再登记。

### F10. CLI 无条件注入配置插件与配置组件

**严重度：中**

**证据：**

- `packages/aurora_cli/src/aurora_cli/commander.py:55-58` 即使 `--plugin`/`host.toml` 没有选择 `aurora_config`，也会执行 `plugins = (configuration_plugin(), *plugins)`。
- `packages/aurora_cli/src/aurora_cli/host.py:51` 无论装配是否声明配置，都追加 `configuration_component(...)`。

**为什么是偏离：** 设计第 6.4 节和 AGENTS.md 要求“安装包与启用插件分开；`requires` 只校验依赖插件已显式启用，不隐式加载依赖”。CLI 的隐式注入让 `--plugin` 不能完全决定启用集合，也使配置能力不再是显式装配项。

**建议：**

- 把配置服务定义为 CLI 宿主的显式 bootstrap 依赖，写入 `host.toml` 模板、默认插件列表和文档。
- 或者在未启用时保留声明并 warning，不要静默注入。
- 若确实需要 CLI 内置配置，同步更新设计依赖表，并补“CLI 无 config 包”的边界说明。

### F11. 配置阶段失败时配置编辑入口可能未关闭

**严重度：中**

**证据：**

- `packages/aurora_core/src/aurora_core/lifecycle.py:177-193` 的 `_shutdown()` 只对 `_attempted` 组件调用 `stop_accepting`；`_configured` 组件只参与 CLEAN。
- `packages/aurora_config/src/aurora_config/service.py:29-42` 把 `service.close` 作为唯一的 `stop_accepting`，没有 CLEAN handler。
- 若某个后续 CONFIG handler 失败，配置服务已 `configure()` 但尚未进入 prepare，`_attempted` 为空，`service.close()` 不会执行，`ConfigurationEndpoint.files` 仍保持可用。

**为什么是偏离：** 设计第 7.5 节要求启动失败清理已进入阶段的组件，包含部分配置失败的组件。配置端点应随失败收尾进入不可用状态。

**建议：**

- 对 `_configured` 组件也执行 `stop_accepting`，或把 `ConfigurationService.close` 注册为 CLEAN handler。
- 给 `Lifecycle` 增加“已进入阶段”的显式集合（configured/attempted/started），失败收尾时按阶段处理。
- 补“后续 config handler 失败”的测试，断言配置端点返回 503 或不再可用。

### F12. 生命周期实例 ID `"aurora_config"` 是跨包魔法字符串

**严重度：中低**

**证据：**

- `packages/aurora_world/src/aurora_world/configuration.py:80` 和 `packages/aurora_adapters/src/aurora_adapters/mcp/clients.py:174` 硬编码依赖实例 ID `"aurora_config"`。
- `packages/aurora_config/src/aurora_config/service.py:40` 也硬编码 `owner = "aurora_config"`。

**为什么是偏离：** 设计第 4.4、7.5 节要求实例身份和生命周期依赖显式表达。这个字符串没有公共常量、没有进入 registry、也不参与 admission；宿主换一个配置实例 ID 时，只会在拓扑排序时报“缺少依赖”。

**建议：**

- 在 core 或 config 包定义共享的生命周期实例 ID 常量，或由 `LifecycleComponent` 依赖对象显式传递。
- `configured_sources_component()` 和 `MCPClients.component()` 从调用参数接收配置组件 ID。
- 启动前校验依赖是否已登记/已装配，给出可诊断的配置错误。

### F13. TUI 订阅者抛错后不发送终态 status

**严重度：中**

**证据：**

- `packages/aurora_client/src/subscriptions.ts:228-236` 的 `observerFailed()` 直接把 `current` 设为 `failed`，但没有通过 `emit`/`setStatus` 发送 status 更新；随后 `finishAfterCleanup()` 移除该订阅。
- `apps/aurora_tui/src/state/workbench.ts:350-374` 只在收到 `status` 更新时改 `connection`/`ready`。

**为什么是偏离：** 订阅观察者抛错后，界面可能仍认为连接是 `connected`、`ready=true`，继续提交和查询，但已收不到事件。设计第 10.3 节要求界面可观察连接和刷新状态。

**建议：**

- `observerFailed()` 通过独立的 status channel 或延迟 `setStatus('failed', failure)` 发出终态，确保不会再次进入同一失败观察者。
- 补“ready 后观察者抛错”的测试，断言界面进入失败状态。

### F14. 客户端运行时校验与生成 schema 存在第二份手工实现

**严重度：中低**

**证据：**

- `packages/aurora_client/src/transport.ts` 的 `conversationResult`/`configurationResult` 手工实现身份长度、状态枚举、`revision` 的 64 位十六进制校验。
- `packages/aurora_client/src/generated/ctx-contract.json` 中 `ConfigurationDocument.revision` 只声明为 `string`，没有对应正则。
- 生成器只生成类型和绑定，不生成校验器。

**为什么是偏离：** 设计第 10.3 节要求以维护的后端描述为来源。手工校验与生成描述可能漂移：类型更新了，运行时校验没更新。

**建议：**

- 从生成的 JSON Schema 生成运行时校验器，或至少从生成产物读取长度、枚举和格式常量。
- 对新增字段和格式变化补契约测试。

### F15. 状态暴露只到“整键”粒度，缺少 location/字段投影

**严重度：中低**

**证据：**

- `packages/aurora_api/src/aurora_api/server.py:65-67` 的边界是“仅开放显式选择的完整状态键；同一键的全部 location 均开放”。
- `_filters` 只校验 location 是非空字符串键值对；`list`/`watch` 只按 key 过滤。
- TUI 状态页展示整份 `record.value`。

**为什么是偏离：** 设计第 5.5 节要求 client 获取“准备提供给界面的数据”，敏感配置和凭证不应因通用 ctx 接口自动暴露。整键白名单是本机已接受的边界，但如果某个键混合公开/敏感字段，字段级边界并未实现。

**建议：**

- 对需要开放的键增加 location/字段白名单或服务端投影 DTO。
- 不要把混合敏感度的聚合状态键直接加入 `--keys`。
- TUI 对展示值做额外裁剪和脱敏。

### F16. 其他工程卫生问题

**严重度：低到中**

- **Node 版本漂移：** `.node-version` 为 26.13，`package.json` 要求 `>=26.4 <27`，但当前环境 `node --version` 为 24.16；`tests/e2e/test_tui.py` 与 `test_tui_recovery.py` 因 `--experimental-ffi` 不支持而失败。建议在 `check` 中校验 Node 版本，并补 CI。
- **生产代码 `assert`：** 约 40 处源码使用 `assert` 表达不变量（如 `assembly.py`、`react.py`、`config/service.py`）。`python -O` 会移除，建议改为显式异常。
- **README 为空：** 根 `README.md` 长度为 0；按 AGENTS.md 修改前需用户确认。
- **无 CI：** 仓库没有 `.github` 工作流；Node/uv/Windows 组合的分层检查只能手工执行，容易出现本次的版本漂移假失败。
- **Panel/docsite/landing 为空骨架：** 只有 `package.json`/`.gitkeep`，没有构建、typecheck 或页面；设计已说明是规划，但检查入口容易让人误以为已交付。
- **405 等 HTTP 异常非 JSON：** `server.py` 只把 404 转成 JSON，其他 `web.HTTPException` 由 aiohttp 返回文本；TS client 会抛 `ProtocolError`，丢失状态和稳定错误码。建议统一错误信封。
- **`WorldSources.prepare()` 的边界：** 空来源集合下若 `prune()` 抛错，`except` 中的 `binding` 未赋值，会变成 `UnboundLocalError` 并覆盖原始异常。建议初始化失败绑定变量。
- **`Reference` 与 `WorldRecords` 职责：** `WorldRecords.append` 接受并执行 `retention`，`prune()` 是公开方法；建议明确 owner 校验，避免普通记录调用方绕过来源层裁剪。这是设计取舍问题，不是立即 bug。

## 5. 验证结果

本次审查执行了：

```powershell
uv run --locked pytest tests/unit tests/contract -q
# 601 passed

uv run --locked pytest -q
# 789 passed, 2 failed
# 失败均为 Node 24.16 不支持 --experimental-ffi：
# tests/e2e/test_tui.py
# tests/e2e/test_tui_recovery.py

pnpm test
# 97 passed

pnpm typecheck:python
# 0 errors, 0 warnings

uv run --locked python scripts/generate_ctx_contract.py --check
# 0
```

说明：

- 2 个 TUI e2e 失败是环境版本问题，不是业务回归；在 Node 26 下应通过，但当前检查没有提前拦截版本漂移。
- 未调用真实模型、真实 MCP 服务或外部平台。
- 未修改任何实现文件；本报告是唯一新增文件。

## 6. 建议优先级

1. **先处理 API 只读键 + 世界记录写保护。** 这是数据完整性问题，改动范围小，适合作为独立切片先做。
2. **再处理长期运行策略。** 世界记录/MCP 来源 retention、bot 消息窗口、快照成本；先加默认上限和配置项，再评估增量存储。
3. **抽 agent 恢复/裁剪 helper，收敛调度所有者。** 按拆包评估第 4.3 节推进，为 harness 复用做准备；同时修 `_compact` 覆盖异常的问题。
4. **把 TUI 需要的数据纳入生成契约。** 先解决 `react_work` 内部字段和 `RunGroup` 实例身份，再做性能基线。
5. **按计划推进 B5 → B3 → W3/W4。** B5 的 stdio/协议策略/产品装配是当前主线；B3 在扩展后补共享关闭矩阵。
6. **D08 认证/Origin 方案确定后再接 Panel。** 不要让 Panel 直接依赖“拒绝所有 Origin”的临时边界。
7. **补 CI 与版本校验。** 至少覆盖 Windows + Node 26 + uv + pnpm check，避免环境漂移再次制造假失败。
8. **同步文档依赖表与 ID 目录。** model_adapter→config、CLI→config/logging、bot:registries/agents 三处应尽快对齐。

## 7. 附注

- 用户已确认 `docs/opencode_like_mcp_config.md` 中的两个 token 为测试用途并已删除，因此本报告不把它列为待处理风险。仍建议不要把任何凭证样例提交进仓库；如果该文件保留，至少使用占位符或环境变量引用。
- 本报告以 `8b46dd2` 为基线；审查期间工作区出现的未提交 MCP 通用接入改动，应由对应实现任务单独验收，不能把本报告的 MCP 结论直接套用到那些改动上。
- 设计文档中的规划内容不等于已实现能力；本报告区分了“未交付”与“实现偏离”，未把计划内缺口误判为回归。
