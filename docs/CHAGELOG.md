# 变更记录

## 2026-10-30

### 主动 bot、ReActAgent 与外围环境的设计决策

- 设计以 bot 为中心：外围环境提供感知、执行、持久化与调度条件，尊重 bot 对关注对象、目标推进和行动的选择。没有新用户消息时，bot 仍可推进目标或主动行动；回复消息是可选择的行动，一次激活允许不采取行动就正常结束。
- bot 实例长期存在；一次激活包含可能多次推理与工具执行的 ReAct loop；一次模型或工具调用属于激活内部。激活结束不销毁 bot 的身份、目标及需要保留的状态。安排下一次唤醒、子代理等能力通过工具提供，具体工具随相应切片实现。
- 再次触发表达可能需要重新规划的引导。空闲时启动一次激活；运行中接纳新信息并在后续观察、推理节点调整计划，保留当前运行及已有执行结果。引导不隐含强制取消、重启或创建并发 loop；同一次激活保留 run_id，子调用各自拥有 execution_id。
- world 是独立接入根生命周期的插件，与 bot 执行体系并行工作。world 的插槽接入客观世界的信息来源，例如外部消息、MCP 推送或模拟环境；world 维护相关 ctx 空间，不直接提供供 cadence 接入的执行插槽。
- cadence 订阅选定的 world ctx 地址，按自身策略筛选变化、准备引导并触发连接的 ReActAgent。不同 cadence 可以关注同一世界的不同范围；world 的信息维护不依赖某个 bot 是否关注。world 与 cadence 的联系通过 ctx 数据和订阅表达。
- cadence 提供执行插槽，ReActAgent 提供执行插头；连接握手交换 ctx 地址与可选 schema，执行只传递运行和调用身份。每个 agent 实例由一个调度所有者串行管理激活；运行中通过持续输入接纳引导。ReActAgent 的执行入口等待本次激活收束，调用完成由等待确定。
- 持续输入采用 inbox、progress、runtime 三类地址角色：cadence 写入带标识与顺序的引导；ReActAgent 记录已纳入上下文的位置及当前运行状态。progress 表达已接纳，不代表已完成对应要求。inbox 与消费位置按 agent 实例定位，跨激活保留；单次推理、动作等数据可沿用按 run_id 定位的绑定。保留与裁剪策略由装配明确，不由 core 自动推断。
- ReActAgent 在推理前接纳引导，在结束前检查待处理输入；调度所有者在执行返回后复查输入，覆盖结束边界上的变化。ctx 订阅仅通知后续变更，没有历史回放承诺；需要逐条处理的世界消息应保存可读取的记录，消费方维护位置，不能仅依赖不断覆盖的最新值或瞬时事件。
- 接口草案：org.aurora.bot:handlers/react_agent 为 component，其 /execute 为 hook_handler；沿用 org.aurora.bot:react/{prepare,infer,act,observe,finish,error} 六个 hook_slot。prepare 在每次推理前准备上下文与引导，infer 形成行动或结束决定，act 执行工具，observe 接纳结果，finish 收束本次激活且允许无输出，error 处理失败。阶段连接属于具体 agent 实例，执行顺序由 bot 组件负责。
- 实施顺序：先交付可再次激活、运行中接纳引导的 ReActAgent 最小组件与离线行为验收，再接入基本工具往返、默认装配与恢复、真实模型和 CLI 整体验收。world、cadence 的完整插件、唤醒工具与子代理属于后续切片；阶段入口和持续输入先以显式进程内装配验证。达到本切片验收不代表整个 M2 完成。

### 实现与验证记录

- 模型适配插件登记 state/config 与 state/bindings：前者按名称保存 adapter/model 和可选 base_url/credential，后者将逻辑角色映射到配置名称。credential 只保存运行期凭证引用；api_key 与未知字段拒绝写入。resolve_model 只解析 adapters 注册表中的工厂，不从配置导入模块、不缓存客户端；同一定义可以创建独立实例。
- ToolSpec 可显式提供异步 ToolFactory。工厂接收 ctx、宿主 storage、分配的 instance_id、input/output 地址及工具 JSON 配置，返回 ToolInstance(plug, aclose)。工厂返回前的失败或取消由工厂释放部分资源；成功返回后的资源由装配负责关闭。工具沿用装配分配的身份和工作地址，共享 storage 仍由宿主关闭。

- examples/react_agent/main.py 使用正式 ReActAgent、ReActDefaults、ModelCall 和 ToolExecutor，显式装配本地加法工具与 FakeModel。运行 `uv run python examples/react_agent/main.py --data-dir build/react-demo --guide "保留当前计算进度"` 可观察工具往返和流式期间引导；`--tool-error` 演示失败观察，`--tool-delay 0.2 --timeout 0.01` 演示超时，`--text "无需行动"` 演示无行动结束。同一数据目录重复运行保留上下文与消费位置，Ctrl+C 保存取消状态和待接纳工具结果；示例清理已消费 inbox 与中间值，只保留最近模型输出和恢复所需工具批次。
- 本切片完整 uv run aurora check 通过：339 项 Python 测试、9 项工具链测试及格式、lint、Python/TypeScript 类型和工作区入口检查；4 项新增真实进程测试验证正常/失败/超时工具往返、引导、重启恢复与 SIGINT 后结果接纳。CLI 显式启用 aurora_bot.react、aurora_bot.model、aurora_bot.tools、aurora_bot.react_defaults 可枚举新增组件与端口。真实模型连接未验证；正式默认装配资源、模型工厂与绑定恢复、cadence/world 以及 CLI 对话仍待后续切片，M2 尚未整体完成。

- aurora_bot.react_defaults 提供 ReActDefaults，将 build_prompt、ModelCall、interpret_response、ToolExecutor 与 record_observation 显式连接到 ReActAgent 的 prepare/infer/act/observe 阶段。三个默认处理器以 component 及 /execute 插头登记；模型和工具继续使用各自的组件定义。默认连接要求工作阶段为空，连接失败撤销本次新增连接；客户端仍由宿主持有并关闭。
- 默认上下文以实例级 ReActContext 保存 messages、guidance_sequence 和 pending，消息与引导位置整项提交。prepare 按序接纳输入并准备模型可见工具清单；工具失败观察仍进入下一轮推理。模型文本仅保留为内部上下文，不自动发送给用户；无工具且 stop 可正常结束，length/content_filter 或不一致的结束原因明确失败。
- 工具请求与其全部结果成组回填。中断后的 pending 在下一次激活时接纳已保存结果，其余结果标为 interrupted；不复用其他 turn_id 的输出，不自动重跑动作，也不假定中断时没有副作用。完成的工具结果在 after_call 扩展失败时仍保留，后续工具不继续执行。上下文、inbox 和恢复所需工具记录的裁剪由装配明确。
- 10 项默认阶段测试覆盖成功/失败工具观察、流式期间引导、无行动结束、prepare 去重、取消后的结果接纳、旧批次隔离与不完整模型响应；工具测试共 15 项。完整检查结果与离线示例见下条。

- 工具失败策略：未知工具、参数错误、工具执行异常和超时均作为结构化观察交回 bot，由模型决定后续行动；取消继续传播并等待清理。基础执行器不自动重试动作，扩展处理器故障和装配错误仍明确失败。
- aurora_bot.tools 提供 tools 注册表、ToolSpec 和 ToolExecutor。ToolSpec 将模型可见的名称、描述及参数 schema 关联到组件定义，装配显式连接工具实例；模型只看到已连接工具，同一执行器拒绝重复模型名称。工具以 ExecutionPlug 接入，通过 input 读取完整 ToolCall，在 output 写入 JSON 结果；临时工作地址由执行器清理，持久业务数据另存。
- 工具参数使用 jsonschema 的 Draft 2020-12 校验与本地 referencing Registry，不获取外部 schema；format 仅为注释。批次按 turn_id 关联推理，调用 id 在批次内唯一；按顺序执行并逐个保存结果，before_call 可通过 ToolRejected 拒绝动作，after_call 观察已保存结果。超时覆盖前置处理和工具执行，以及后置处理；同步阻塞和忽略取消的插件不承诺强制抢占。
- 工具批次保留 completed/failed/cancelled 状态与逐项结果；批次 completed 表示处理结束，各项仍可为失败。取消保留已完成结果、标记当前取消及后续未执行项，不消费旧输出。14 项工具测试覆盖连接、参数、结果隔离、拒绝、失败、超时、取消、临时值清理和本地 schema 引用；Ruff 与 Python 类型检查通过。

- aurora_bot.react 插件提供 ReActAgent component、/execute 插头与六个 react 阶段插槽。调用通过显式连接执行，保持同一激活的 run_id，各阶段子调用生成独立 execution_id。prepare/infer 必须连接；infer 经 decision 地址明确选择 act、continue 或 finish；act 要求 act/observe 连接，finish 可无处理器、无对外输出。组件不持有后台任务，不订阅 world；宿主通过 Lifecycle.run 管理根调用。
- inbox、progress、runtime 使用实例级地址；引导包含跨激活严格递增的 sequence、唯一 id 和 payload。prepare 读取 batch 快照并将其纳入可保留的上下文，成功后推进消费位置；失败不确认该批输入，处理器按引导 id 避免重试重复。新输入在下一次 prepare 接纳，finish 开始后的输入保留为 pending，由调度所有者在返回后复查。batch/decision 按运行定位并在收尾时删除，runtime 保留最近激活的 completed/cancelled/failed 状态；其他上下文、模型输出和输入裁剪由装配负责。
- 同一 ReActAgent 实例的重入执行明确拒绝，不改动在途运行；取消传播并等待当前处理器收尾。循环上限、缺少阶段、无效决策与异常输入明确失败；error 处理器失败时同时保留执行和错误处理异常。既有 ModelCall 可直接连接 infer 插槽，由后续阶段处理器将模型结果解释为控制决定。
- 本切片新增 18 项组件行为测试与 3 项离线集成测试。真实宿主、FakeModel、ModelCall 和测试内本地加法工具完成工具往返、流式期间引导、无行动结束、上下文与消费进度恢复、模型/工具失败及资源关闭验证；本地工具仅为测试装配，通用工具组件、默认 ReAct 处理器、正式装配、cadence/world 与真实供应商适配仍待后续实现，不承诺重启透明续跑。
- 完整 uv run aurora check 通过：310 项 Python 测试、9 项工具链测试及格式、lint、Python/TypeScript 类型和工作区入口检查。uv run aurora --plugin aurora_bot.react id list 可列出组件与六个阶段插槽；本切片未连接真实模型。

- bot 的 InstanceStateBinding 使用装配显式指定的固定地址，跨 run_id 共享实例状态；StateBinding 继续按 run_id 定位单次运行数据。ExecutionSlot 可通过 slot_id 指定具名阶段端口，execution_slot_entry 声明接收 ExecutionPlug 的插槽；握手、组件身份校验和调用语义沿用现有执行接口。

- 项目服务端口使用 10270–10279 段；本机 ctx API 默认监听 127.0.0.1:10270，serve 的 --port 可显式覆盖。`uv run aurora -d build/ctx-demo serve` 启动常驻宿主，Ctrl+C 关闭连接、取消订阅并完成状态落盘；可在 serve 前通过 --plugin、--assembly 和 --config 选择业务装配及初始配置。
- CLI 通过 `--connect http://127.0.0.1:10270` 执行 ctx get/list/set/delete/watch，连接模式不构造本地 ctx 或存储，不接受 --data-dir、--plugin、--assembly、--config。默认开放 org.aurora.cli:state/config 的全部业务地址；serve 的 --keys 接收完整状态 ID 的 JSON 数组，显式替换开放列表。该切片服务本机 CLI，拒绝浏览器 Origin 与非本机 Host；浏览器接入、远程部署认证及 TS client 尚待实现。
- HTTP 使用 POST /ctx/get、/ctx/list、/ctx/set、/ctx/delete，参数为 key、location 与 set 的 value，成功响应为 result 信封；错误使用稳定 code/message，不回传校验器内部信息。WS /ctx/watch 接收 key/location 筛选对象，ready 确认订阅后发送保留 org.aurora.core:events/ctx/changed 身份的事件；revision 属于当前宿主 ctx，不承诺连续编号或历史补发。关闭连接即取消订阅，断线显式失败；每连接队列上限 256，溢出报告 slow_consumer 并关闭，重连后需重新读取状态。
- 多终端体验：先启动 serve；第二个终端执行 `uv run aurora --connect http://127.0.0.1:10270 ctx watch`；第三个终端执行 `uv run aurora --connect http://127.0.0.1:10270 ctx set org.aurora.cli:state/config '{"count":1}'`。watch 输出 JSON 变更；ctx get/list 可通过同一连接参数读取运行中宿主的状态。
- HTTP/WS 契约与真实 CLI 进程覆盖读写、精确地址过滤、并行订阅、断线释放、队列溢出、访问拒绝、错误脱敏及 Ctrl+C 后恢复；全量 289 项 Python 测试、Ruff 检查与格式检查、Pyright 类型检查通过。

- aurora_logging 提供显式 configure_logging 入口：root logger 统一接收业务包的标准库日志，RichHandler 输出至 stderr，UTF-8 文件按大小轮转。默认文件级别为 DEBUG、终端级别为 INFO，每个文件 10 MiB，保留 5 份备份；重复配置关闭并替换本包处理器，保留外部处理器，导入包不创建文件或配置日志。日志目录由单进程独占。
- CLI 在插件发现前配置终端日志，在宿主命令参数验证通过后写入 data_dir/logs/aurora.log，覆盖装配工厂和 prepare/start/stop。--level/-l 设置终端日志等级，支持 DEBUG、INFO、WARNING、ERROR、CRITICAL，忽略大小写，默认 INFO；DEBUG 显示完整异常栈，文件始终以独立的 DEBUG 级别保留完整异常栈。帮助、版本及参数错误不创建数据目录，插件发现期间仅输出终端日志。core、bot 与模型适配包直接使用标准库 logging，无需依赖 aurora_logging。
- 日志传播、独立级别、中文与异常落盘、轮转保留、重复配置、配置失败、CLI 输出及生命周期日志验证通过；全量 269 项 Python 测试、Ruff 检查与格式检查、Pyright 类型检查通过。

- 计划、M2 交接、设计文档、公共 ID 目录与示例指南以 4eb4d6e 为实现基线：M0/M1/M2.1 完成，控制与模型组件可用，默认装配、真实适配、对话运行和 ReAct 工具循环仍待实现。文档列出组件定义、实例与调用身份、ctx 数据握手、临时状态清理、模型流与客户端关闭责任，以及当前插件入口和启动命令；公共 ID 目录逐段区分已实现定义与规划入口。
- 文档核对通过 34 个本地链接与 24 项模型/bot 已实现 ID、kind 对照，所列插件目录命令可执行；模型协议、组件身份、控制、ModelCall 和两个相关示例共 45 项测试通过。本轮仅修改文档，未重新运行完整 aurora check。

- 控制组件采用统一层级定义：org.aurora.bot:handlers/control 及其 serial、branch、while、parallel 子路径登记为 component，各定义的 /execute 为执行插头，/children 为子组件插槽。component 登记项指向组件类或局部执行函数，提供者由装配显式声明；component_entries 负责生成本插件约定的端口声明，core 仍按完整 ID 与显式 kind 寻址。
- ExecutionPlug 与 ExecutionSlot 显式携带 definition_id，连接使用双方实际端口 ID，并校验执行插头的定义归属；控制器须匹配自身的插槽定义。同一插槽内的子实例标识唯一，避免分支选择歧义。组件定义、执行入口和插槽共用路径层级，不从路径推导运行时父子关系。
- 实例标识默认使用 UUID，可显式指定非空字符串；展示引用采用 definition_id.instance_id，内部保留独立字段，不将复合展示字符串交给 Id 解析。组件多次取得插头保留同一个实例身份，每次子调用继续使用独立 execution_id。控制状态按定义、实例、运行和调用定位，终态后清理；运行期实例不会因恢复快照而自动重建。
- ModelCall 的组件身份为 org.aurora.bot:handlers/model_call，执行入口为其 /execute；aurora_bot.model 插件可通过显式清单或同名 entry point 启用。示例显式登记局部业务组件与提供者，通过 ctx 地址握手交换数据，并使用各组件自己的执行入口。
- 装配使用 ExecutionSlot(Serial.definition_id, hooks, instance_id="root") 与 ExecutionPlug(definition_id, execute, instance_id="worker")，省略 instance_id 时自动分配身份；ModelCall(ctx, client, ...) 采用相同规则。本轮完整 aurora check 通过 256 项 Python 测试、9 项工具链测试及格式/lint/类型检查；安装后的 CLI 能通过两个 bot entry point 展示组件与端口目录。

- bot 的 ModelCall 组件通过连接约定的 ctx 地址读取 ModelRequest，在单一输出位置更新文本、完整工具请求、结束原因和调用状态。取消或失败保留已收到的文本并标记 cancelled/failed，错误继续传播；只关闭单次响应流，ModelClient 由创建它的宿主关闭。同一输出地址须串行调用，业务数据保留策略由装配负责。
- examples/model_call/main.py 提供准备输入、假模型推理和结果读取的串行装配，支持流式/完整响应、模拟失败和 Ctrl+C；退出后快照只保留最近一次输出。模型数据使用 Python TypedDict 表达普通 JSON，地址内容可按局部约定或 StateKey 校验器约定；不新增全局契约匹配机制、模型片段历史或 controller 调用历史。

- model_adapter 提供普通 JSON 数据形式的消息、工具定义、完整工具请求、模型请求/响应与流式片段，以及 ModelClient/ModelFactory 协议。complete 返回完整响应；stream 通过 async with 消费文本增量、完整工具请求及唯一结束片段，缺失结束片段明确失败。结束原因区分 stop、tool_calls、length 和 content_filter，不将响应结束等同于业务完成。
- 调用方拥有单次响应流，提前结束、失败、超时或取消均通过上下文收尾；宿主在全部调用结束后关闭 ModelClient。能力不足明确拒绝，不自动降级；配置描述与运行期 api_key 分开，公共数据不包含 SDK 类型。FakeModel 以可配置响应脚本离线验证上述边界，工厂可创建相互独立的实例。
- aurora_model_adapter 插件沿用目录中的 adapters 注册表、model_client 服务及四个模型 schema 身份，可由显式清单或同名 entry point 启用；此切片不包含真实供应商适配、默认绑定恢复或对话提交机制。

- Controller 的 ctx 状态仅覆盖在途调用；完成、失败或取消时通知唯一终态，随后删除本次地址，不累计子调用历史。清理按实例、运行和执行身份精确定位，其他在途调用不受影响；需要历史的订阅者自行收集。业务数据的保留策略由应用负责，core 仍保存完整 ctx 快照。
- control_flow 示例恢复时清理没有在途任务对应的控制状态，收尾时清理中间值和历史结果，仅保存最近一次运行的 completed/result、cancelled 或 failed 记录。循环 100 次的单元用例验证在途控制状态数量有界，连续启动与真实 SIGINT 用例验证最终快照只有一条运行结果。

- 示例按应用放在 examples/core_counter/ 与 examples/control_flow/，入口均为 main.py；examples/START.md 提供安装、启动、参数、预期输出、取消和数据目录说明。控制示例通过循环计数、奇偶分支、并行计算与结果汇总展示四类控制组件，打印真实 ctx 通知；每次启动创建独立运行，结束或取消后由宿主保存快照。

- aurora_bot.control 提供内置控制插件，可通过显式 Plugin 清单或同名 aurorabot.plugins 入口启用。Serial、Branch、While、Parallel 组件复用 core 的实例连接和单次调用，可相互嵌套；core 不承担业务流程控制。
- 控制连接在握手时交换双方的 ctx 地址描述和可选 schema，由插槽实例的 accept 判断兼容性；描述不同但被接收时记录 warning，无 schema 时允许使用代码约定。执行请求仅携带 run_id、execution_id 和父调用标识，业务输入输出由各组件自行读取和更新 ctx，不通过执行参数或返回值传递。
- StateBinding 将实例业务位置按 run_id 定位；同一运行的重复调用可更新同一位置，需要调用历史的组件自行增加 execution_id 定位。地址不构成写权限边界，也不保证共享业务状态的并发安全。每次子调用生成独立 execution_id，控制完成由等待调用确定，ctx 变化订阅用于观察状态。
- Serial 按 priority 和连接顺序依次等待，失败或取消终止后续调用；Branch 从 ctx 读取条件并选择一个子实例，None 跳过，未知实例报错；While 先判断条件，执行唯一循环体，达到显式上限且仍需继续时失败；Parallel 按显式并发上限运行，失败或取消时取消其他任务并等待清理，再传播异常。
- 当前控制插件登记 org.aurora.bot:control/children（hook_slot）、org.aurora.bot:handlers/control/execute（hook_handler）和 org.aurora.bot:state/control（state_key）。在途控制状态按实例、运行和调用定位，提供父调用标识及选择或迭代信息；终态通知后删除，不保留调用历史。每次根调用使用新的 ExecutionRequest，不提供重复请求去重或崩溃续跑。
- 根执行可交给 Lifecycle.run 管理；控制组件没有脱离根调用的后台任务，正常关闭完成任务清理与最终状态写入后由宿主持久化。离线用例覆盖地址握手、兼容与拒绝、四类控制行为、嵌套、并发限制、父/子取消、组合结果恢复以及宿主关闭后的清理写入恢复。此切片不包含 ModelClient、ReAct 默认装配或 CLI 对话入口。

- id/list（亦可写作 id list）按完整 ID 排序展示当前定义总表的 ID、kind 与 provider，包含 core 自举、CLI 内置定义及已启用插件声明。命令身份为 org.aurora.cli:commands/id/list，通过命令包自动发现；无需数据目录，不构造 ctx 或启动装配，因此不包含 prepare/start 阶段动态登记的定义。

- 命令可通过 passthrough 的非空帮助文本显式启用参数透传。无自身参数的命令原样接收全部参数，包括 --help；有自身参数的命令只将首个 -- 及后续内容交给执行器，其前参数继续严格解析。执行器或 operation 接收名为 passthrough 的 list[str]，保留顺序、空字符串、含空格参数及分隔符，由命令决定下游转发方式，不拼接 shell 字符串。
- 未声明透传的命令仍拒绝未知参数；透传命令禁止再声明同名 passthrough 参数。check 仅提供既有初筛选项，不启用透传；定位失败项时使用对应工具的精准命令。
- 顶层命令和参数作为整体保留原始 argv，避免消耗叶子命令的 --。core 单次调用包装器的路由参数使用仅限位置参数，允许业务参数使用 target、registry、identity 等名称。

- M1.8 微内核集成验收完成，M1「微内核可用」达到出口条件；下一里程碑为 M2「最小 bot」。验收使用真实组件、JSON 快照、SQLite 存储和 CLI 进程，故障注入仅位于测试夹具。
- tests/e2e/test_m1_shutdown.py 在磁盘 I/O 阻塞时接收 20 个并发调用，并启动关闭：拒绝新工作、等待全部在途写入、执行组件最后写入、保存最新完整快照、关闭存储、关闭 ctx。测试记录实际顺序，检查连续 22 次状态通知，重开后验证全部业务地址与结构化数据。
- tests/e2e/test_m1_cli_process.py 通过已安装入口元数据发现测试插件，在真实 CLI 进程中运行 ctx/watch 并触发 SIGINT；变化按序输出，停止阶段最后写入，进程返回 130，下一进程读取到最终值。组件停止失败和最终落盘失败均返回 1；落盘故障保留上一份正式快照。
- M1 关闭异常覆盖同时包含部分启动清理、禁用可选停止处理器、在途取消、落盘失败保留内存与重试、损坏快照保护；既有生命周期与持久化测试和本轮整体场景共同验证这些边界。
- 本次 aurora-core wheel 在仅安装该包的独立虚拟环境中执行计数器两次，输出 2 和 5；确认 CLI、bot、模型适配和 API 均不可导入，验证 core 外应用无需业务包即可恢复状态。
- M1.8 验收包含 196 项 Python 测试、9 项工具链测试、Pyright basic 及格式/lint/TypeScript/工作区入口检查。ctx 并发语义仍为同一宿主线程内的显式操作；数据目录由单宿主独占，CLI watch 观察当前进程，快照不承诺异常断电时零数据丢失。

- aurora -v/--version 输出已安装 aurora-cli 发行包的版本并立即退出，不发现插件、不创建运行期宿主或存储；版本来源为发行包元数据。

- commands/ 的直接子包通过无参数 plugin() 工厂返回 core Plugin，CLI 按包名排序自动发现并统一登记；下划线开头的内部包不参与发现。包入口仅声明元数据和函数引用，文件、连接及任务在执行或生命周期阶段创建。发现范围为内置命令包，外部 entry point 仍需 --plugin 显式启用。
- 命令必须且只能绑定 operation 完整 ID 或 executor callable。operation 默认要求运行期宿主，返回值以 JSON 输出；executor 默认不启动宿主，接收 CommandContext 与解析后的命名参数，可同步或异步执行，自行输出并返回 None 或 0–255 的整数退出码。CommandContext 提供 root、output、registry 与已接收命令目录。
- executor 通过 runtime=true 声明需要 core 状态操作和生命周期，通过 assembly_argument 指定由宿主消费的 id 类型装配参数。所有执行绑定复用最小调用机制；重复 ID 在执行前拒绝，不完整或不兼容声明不进入可执行命令目录。
- about、check、donk、help、ctx 与 run 各自在包内提供执行绑定和运行需求；commander 按声明选择运行环境，host 只负责装配与生命周期，执行层无需具体命令 ID 白名单。空命令与分组帮助由 CLI 展示基础设施提供，即使 help 命令包缺席仍可查看目录。
- 自包含命令示例：在 packages/aurora_cli/src/aurora_cli/commands/hello/__init__.py 中定义以下内容，即可通过 uv run aurora hello Aurora 执行，无需修改中央分派或登记列表：

```python
from aurora_cli.declarations import CommandContext, command_plugin


def execute(context: CommandContext, name: str) -> int:
    print(f"你好，{name}", file=context.output)
    return 0


def plugin():
    return command_plugin(
        __name__,
        {
            "hello": {
                "help": "打招呼",
                "arguments": [{"name": "name"}],
                "executor": execute,
            }
        },
    )
```

- 验收通过完整 aurora check：190 项 Python 测试、9 项工具链测试，Pyright basic 无错误。覆盖命令包独立新增与移除、外部入口显式启用、同步/异步执行器、自定义退出码、运行期状态恢复、重复 ID 和无效绑定拒绝；安装后的 CLI wheel 在独立环境中完成命令发现与 ctx 调用。

- CLI 分派在选择输出流后显式检查 None；无标准输出的环境须提供 output 文本流，各命令接收非空 TextIO。

- about 与 help 的表格使用 Rich 内置 box.SIMPLE，隐藏外框、保留表头分隔线，不设置隔行变暗。

- about 与 help 直接使用 Rich Table、Text 和 Console，表格展示无需项目级封装；插件帮助内容按字面量渲染。

- CLI 表格采用 Rich Table 原生默认边框、表头和行间样式；banner 使用原生标题，单元格保持字面量文本，重定向输出与文本渲染沿用 Rich 的终端处理。

- CLI 按职责组织为 main（进程入口）、commander（发现和分派）、parsing（参数转换）、declarations（声明接收）、host（运行期装配）与 commands/<name>（命令行为）。内置命令显式汇总，业务操作继续引用 core 公共 ID；旧项目仅提供目录组织和用户可见效果参考。
- help、ctx 和 donk 命令组在未选叶子命令时展示本级帮助；顶层 --help 包含已接收的扩展命令。帮助与项目工具命令不创建 ctx 或存储，长选项要求完整名称。常见错误输出简洁提示，--level DEBUG 显示完整异常。
- about 展示项目标志、介绍、系统与 Python 信息、项目/安装版本、可获得的 Git 提交及链接。--root 指定项目根目录，默认为当前目录；about、donk 和 check 不要求 --data-dir。
- utils.table 使用 Rich 提供中文、多行单元格、边框和终端宽度处理；单元格内容按字面量显示。print_table 面向终端，render_table 返回无 ANSI 控制码的文本，banner 位于表头之上。ctx 的结果及 watch 事件继续输出 JSON。
- donk show 列出根包与全部 Python 工作区成员版本；major/minor/patch 暂按统一版本策略更新这些包的 project.version、内部 >=/== 版本约束，并执行 uv lock。版本不一致、非正式三段版本及不支持的内部约束拒绝升级；文件编辑保留 TOML 注释，写入或锁文件更新失败恢复原始项目文件与 uv.lock。该策略封装于 donk 命令，后续拆分子仓库时可独立调整。
- check 复用 scripts/check.ts；无选项运行完整前后端检查，--lint 选择格式/lint/类型与入口检查，--test 选择 Vitest/Pytest，--coverage 为 Python 测试生成覆盖率并使用 pyproject.toml 的最低阈值。覆盖率阈值采用 20%，可在 tool.coverage.report 中调整。
- --fix 显式启用 Ruff 修复与格式写入，前端格式交给 pnpm format；--unsafe-fixes 需同时指定 --fix，--check 在修复时保持格式预览。测试专用模式拒绝修复选项，检查过程汇总各项失败并返回非零状态。Python 子进程包装在中断时等待工具结束，再将控制权交还文件回滚流程。
- 新增 org.aurora.cli:commands/about、commands/check 与 commands/donk/{show,major,minor,patch} 命令身份；命令参数描述支持仅用于命名选项的 flag 类型。Rich 与 TOML Kit 为 CLI 依赖，pytest-cov 为开发依赖，uv.lock 固定安装版本。
- 使用示例：uv run aurora about；uv run aurora donk show；uv run aurora check --test --coverage。版本变更可通过 uv run aurora --root <项目根目录> donk patch 执行。版本升级验证仅操作临时工作区，当前仓库版本保持 0.1.0。
- 本轮验收包含 182 项 Python 测试、9 项工具链测试、Pyright basic 与完整 aurora check；覆盖率命令、真实 uv.lock 版本更新、锁文件失败回滚、中文表格、项目命令无宿主副作用及原有 CLI 场景均通过。

- M1.7 提供 `aurora` 与 `python -m aurora_cli` 入口。`help`、`ctx` 和 `--help` 展示帮助；状态命令支持 `ctx get/set/delete/list/watch` 或 `ctx/get` 等路径，跨命名空间命令使用完整 ID，短名上下文由 `--namespace` 指定，歧义明确报错。全局选项放在命令之前，运行期命令须显式提供 `--data-dir`。
- CLI 命令表接收普通映射声明：`help` 描述用途，`operation` 引用完整操作 ID，`arguments` 描述参数。参数支持 `name`、`type`、`option`、`required`，类型包括 string、integer、json、id、location；位置参数必填，可选命名参数省略时保留目标函数默认值。接收方拒绝不支持的声明并告警，业务插件无需导入 CLI 类型。
- get/set/delete/list 通过既有 core operation 执行，结果输出 JSON；set 值使用严格 JSON，拒绝重复字段及非有限数。`--location` 使用字符串键值对 JSON，list/watch 省略时不筛选位置，空对象表示全局地址。watch 输出后续变更的逐行 JSON，取消或输出失败时释放订阅。
- `--plugin NAME` 显式启用已安装的 `aurorabot.plugins` 入口，可重复指定。`run ASSEMBLY_ID` 启动选定装配；其他命令通过 `--assembly ASSEMBLY_ID` 在同一宿主中启动组件。首版装配目标是同步工厂，以关键字接收 registry、ctx、hooks、storage，返回 LifecycleComponent 可迭代对象；工厂负责连接，资源初始化与任务启动放在 prepare/start。
- `Lifecycle.start(configure=...)` 在完整快照恢复后、所有组件 prepare 前应用宿主配置。CLI 的 `--config JSON` 将对象整项写入 `org.aurora.cli:state/config`；省略时保留恢复值。配置失败进入启动清理路径，组件不会开始 prepare。
- run/watch 等待至取消，Ctrl+C 通过生命周期停止组件并完成最终落盘；正常退出码为 0，参数解析错误为 2，运行或收尾失败为 1，正常处理中断为 130。CLI 操作当前进程的宿主，数据目录由该宿主独占；watch 不监听其他进程的快照文件。
- 示例：`uv run aurora --data-dir build/cli-demo ctx set org.aurora.cli:state/config '{"name":"demo"}'`，随后执行 `uv run aurora --data-dir build/cli-demo ctx get org.aurora.cli:state/config` 可读取恢复值；`uv run aurora help` 查看命令目录。
- M1.7 验收通过 172 项 Python 测试、5 项工具链测试及完整 `pnpm check`，Pyright basic 无错误。覆盖跨进程状态恢复、地址过滤、参数拒绝、扩展命令调用、watch 取消和输出故障、启动预配置及 stop 最后写入。本次 wheel 在仅安装 aurora-core 与 aurora-cli 的独立环境中完成控制台入口写入与恢复；下一步为 M1.8 微内核集成验收。

## 2026-10-29

- `aurorabot-ai` 为统一安装发行包，依赖独立的 bot、CLI 和 API 包，间接安装 core 与模型适配层；Python 导入名与公共 ID 保持各包归属。
- `uv sync --all-packages` 与 `pnpm install --frozen-lockfile` 安装工作区依赖，`pnpm check` 经 `scripts/check.ts` 汇总格式、lint、类型检查、Vitest、Python 检查与 TS 工作区入口加载检查。
- `scripts/` 首选 Node/TypeScript 脚本；运行环境为 Node `>=24.15.0 <25`，`.node-version` 指定 24.22.0；检查入口兼容 pnpm 的 JS 启动器和原生可执行文件。
- 统一安装包仅提供依赖装配；命令行与服务入口随对应功能实现。
- core 提供不可变 `Id`、公开定义登记项与唯一总表；批量登记检查通过后统一写入，显式替换要求目标存在。短名仅在明确的命名空间与域中解析，歧义时报错。
- 宿主直接建立注册表目录与九个 core 分类注册表；resources 接收 resource、assembly、contract，并保留原 kind。
- 插件发现使用 `aurorabot.plugins` entry point group。入口指向无参数工厂，返回同名 `Plugin`；宿主只发现显式启用的入口，同名显式清单优先。必需插件须同时选中，缺失、入口歧义和导入失败明确报错。
- `register_plugins` 收集全部定义后原子登记；定义覆盖仅通过 `DefinitionRegistry.replace` 显式完成，不依赖发现顺序。
- 接收方通过 `rejection_reason` 评估声明，自行决定接口兼容性；登记与插槽关系分别产生 accepted/unconnected/rejected 诊断。缺席 CLI/API 时保留声明并 warning，其他资源仍可寻址；accepted 仅表示声明被接收，不表示实例已连接或执行。
- M0 验收覆盖 ID、原子登记、自举、插件发现、可选宿主诊断和工作区入口；后续 M1 实现 ctx、实例连接及生命周期。
- `tooling/*` 纳入 pnpm workspace，共享配置保留 Vben MIT 授权信息；工具版本通过 catalog 与锁文件管理。TypeScript 采用 6.0 系列以符合 ESLint 解析器的支持范围。
- `pnpm format` 写入 Prettier 格式，`pnpm format:check` 只检查；Markdown 单独维护，Python 虚拟环境、构建产物与缓存不参与前端检查。
- `pnpm lint` 依次执行 Oxlint、ESLint、Stylelint；`pnpm typecheck` 检查根配置、TS 脚本、共享 client 和工具配置包。应用具备源码后应添加自身 tsconfig 和 typecheck 脚本。
- `pnpm test` 执行 Vitest；Web 应用采用 happy-dom，client、TUI、脚本和工具配置采用 Node 测试环境。样式入口覆盖 CSS、SCSS、Vue 的有效输入及未知属性拒绝行为；当前无应用样式文件时允许空匹配。
- 工具链验收通过 5 项 Vitest 测试、37 项 Python 测试、格式/lint/类型检查及冻结锁文件安装。
- 进程内 `EventBus` 提供同步订阅、按类型过滤、取消和关闭；监听器接收独立载荷副本。重入发布按 FIFO 派发，监听器异常记录后继续通知；不保存历史或隐式创建异步任务。
- ctx 采用整项替换，读写与校验均使用独立深拷贝；状态定义通过 `StateKey` 提供可选同步校验器。状态数据须支持独立深拷贝，运行时服务由装配持有引用。
- 状态地址由公共状态 ID 与排序后的业务定位字段组成，精确匹配且无隐式回退；get 缺失抛出 KeyError，delete 缺失返回 False，list 返回已赋值地址并按 ID 与定位排序。list/subscribe 的 location=None 不过滤，空字典选择全局地址。
- 每次成功 set（含同值写入）与实际 delete 产生一个递增修订和变化通知；校验失败不提交，监听器失败不撤销提交。ctx 原语限宿主线程同步执行，跨线程访问明确拒绝，读改写组合不构成事务。
- `install_context` 显式绑定现有六个 ctx 操作 ID 与变化事件；订阅取消和关闭幂等。持久化及运行时资源关闭顺序由后续宿主生命周期接入。
- `aurora_core` 导出 `Id`、`operation`、`hook_handler` 与 `entry_from`；装饰器只附加声明，保留原函数、签名、协程及绑定方法语义。`entry_from` 显式转换登记项，提供者由装配指定；同一函数仅允许一个公共声明，ID 格式复用 `Id` 校验。
- 六个 ctx 操作通过 `@operation` 声明身份；hook handler 通过显式 slot 引用接收方，装饰器不注册、不执行、不判断接口兼容。
- M1.1–M1.2 与函数声明装饰器验收通过 67 项 Python 测试、5 项工具链测试及完整 `pnpm check`。
- Python 使用 Pyright `basic` 模式；配置统一位于 `pyproject.toml` 的 `[tool.pyright]`，覆盖五个包的源码与 `tests/`，按 Python 3.12 和工作区 `.venv` 解析类型及依赖。
- `pnpm typecheck:python` 单独执行 Python 类型检查；`pnpm typecheck` 汇总 Python 与 TypeScript，`pnpm check` 包含两者。Pyright 通过 pnpm catalog 与锁文件固定版本，测试中的非法输入仅使用注明原因的局部诊断忽略。
- ctx 默认将全部状态数据纳入快照，包含完整状态 ID、业务定位与值；函数、注册表和订阅回调不属于状态快照。JSON 数据支持 null、布尔、整数、有限浮点数、字符串、列表及字符串键字典，不可表示的数据明确报错，不静默省略。
- `Context.snapshot()` 在宿主线程复制全部状态；`restore()` 仅在首次写入前执行一次，按当前状态定义完整校验后原子提交，不重放历史事件。缺失定义、重复地址、损坏文件或不支持的格式版本会拒绝恢复并保留源文件。
- `JsonSnapshotStore` 使用版本 1 的 JSON 格式；同目录临时文件写入并 fsync 后，经文件替换提交正式快照。写入失败保留上一份正式快照并清理临时文件；文件由单宿主独占，不承诺进程崩溃或断电时零数据丢失。
- `ContextPersistence.start()` 先恢复再订阅变更，默认以 0.5 秒间隔合并自动落盘，I/O 在后台线程执行。`flush()` 串行保存并继续处理写入期间的新修订；取消调用仍等待在途 I/O 结束，防止旧快照覆盖后续写入。
- 自动落盘失败通过日志与 `last_error` 报告并重试；显式 flush/close 失败向调用方抛出。宿主停止写入来源后调用持久化 close，成功落盘后才释放订阅，最后关闭 ctx；最终落盘失败保留内存及再次 close 的重试能力。
- M1.3 验收通过 97 项 Python 测试、5 项工具链测试及完整 `pnpm check`；命名空间存储目录和宿主生命周期接入继续按后续任务实现。
- M1.4 的数据目录和结构化存储由 core 提供，根目录由宿主显式传入。`DataDirectories` 分配 `namespaces/ns-<namespace>`，保留点分名称并避开 Windows 保留文件名；命名空间与公共 ID 共用语法，分配时拒绝路径重定向或根目录外路径。
- 宿主级文件使用 `framework/ctx.json` 与 `framework/structured.sqlite3`。`StorageService.snapshot_store()` 接入完整 ctx 快照，`directory(namespace)` 提供插件自有文件和数据库目录；不增加存储服务公共 ID，也不从状态 ID 推导文件名。
- `StorageService` 提供按命名空间和字符串键组织的 get/set/delete/keys，值采用严格 JSON 编解码；单次写入或删除以 SQLite 事务提交，失败回滚，缺失读取抛出 KeyError，键按字典序枚举。接口限创建线程同步调用，跨命名空间访问不构成授权检查。
- 存储服务实例由宿主持有，close 幂等释放框架数据库连接；插件自行负责其数据库结构、事务、迁移和连接关闭。结构化数据与插件数据库不强制镜像到 ctx，完整 JSON 快照仅包含 ctx 状态数据。
- M1.4 验收通过 124 项 Python 测试、5 项工具链测试及完整 `pnpm check`，包含路径约束、Windows 保留名称、SQL 回滚、关闭后重开和三类存储组合恢复。
- M1.5 提供 `HookSlot` 与 `HookConnections`。连接显式指定插槽/处理器公共 ID 和各自实例标识，由插槽接收方判断兼容；缺失、重复、声明插槽不符或被拒绝时不建立连接。运行时方法通过 target 显式绑定，公共定义身份不随实例变化。
- `for_slot` 按 priority 从小到大返回连接，同级保持显式 connect 顺序。定义替换不改变既有连接；断开后拒绝新调用，在途工作由拥有它的组件等待或取消。顺序、并行和循环控制由调用方实现，首版不提供 before/after 排序字段。
- `invoke_operation` 仅接受已登记且可调用的 operation；`HookConnections.invoke` 调用一条有效连接。同步函数在宿主线程运行，异步结果直接等待，错误保留原异常类型并补充 hook 实例信息；协程取消向处理器传播，调用方可使用 asyncio.timeout，不能抢占同步阻塞代码。
- `examples/core_counter/main.py` 是仅依赖 core 的独立计数器应用，包含显式插件装配、装饰器声明、实例连接、操作调用、ctx 订阅、JSON 快照与重启恢复。运行方式：`uv run python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount 1`；同一目录和名称重复执行会继续累计，业务状态按名称区分。
- M1.5 验收通过 141 项 Python 测试、5 项工具链测试及完整 `pnpm check`。本次 core wheel 在仅安装 aurora-core 的独立环境中完成两次运行与状态恢复；示例自行管理启动和收尾，通用生命周期按 M1.6 实现。
- M1.6 提供 `Lifecycle`、`LifecycleComponent` 与 `install_lifecycle_slots`，沿用 prepare/start/stop 三个公共插槽。组件以宿主内唯一的实例标识显式声明依赖，缺失依赖、重复标识和依赖环在启动前拒绝；依赖先 prepare/start，依赖者先 stop，同级遵循显式装配顺序。
- 生命周期先恢复完整 ctx，再执行全部 prepare 和全部 start。启动失败或取消时清理已经尝试 prepare 的组件，包含部分初始化的当前组件；同时发生的启动与收尾错误通过异常组保留。恢复失败不执行最终写入，源快照保持原样。
- `Lifecycle.run` 跟踪宿主接收的调用；停止时拒绝新调用，执行组件的 `stop_accepting`，等待在途调用，超时后请求取消并等待清理。组件自行创建的任务由其 stop 处理器收束。默认超时为 10 秒，分别用于各个异步处理器及在途工作的等待、取消阶段；同步阻塞代码不被抢占。
- 组件 stop 成功后断开涉及该实例的连接；停止或取消收束失败保留尚未停止的依赖、ctx 和存储供重试，成功的 stop 处理器不重复执行。取消 stop 的等待者不会取消宿主收尾，可再次调用 stop 等待结果；收尾失败明确抛出并记录日志。
- 宿主在组件停止后独立执行持久化 close，确保最后的 ctx 写入落盘，再释放连接、存储与 ctx。禁用可选 stop 处理器不取消最终落盘；落盘失败时保留内存和存储，重试成功后才完成关闭。
- `examples/core_counter/main.py` 通过生命周期恢复状态、prepare 装配调用与订阅、run 执行业务、stop 取消订阅及最终落盘。运行命令和按名称累计语义保持稳定。
- M1.6 验收通过 158 项 Python 测试、5 项工具链测试及完整 `pnpm check`，Pyright basic 无错误。覆盖依赖顺序、部分启动失败、取消与超时、停止失败重试、最终写入恢复、可选处理器禁用、落盘失败重试和损坏快照保护；后续进入 M1.7 CLI 基础入口，再执行 M1.8 微内核集成验收。
