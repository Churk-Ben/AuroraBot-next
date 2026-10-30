# 变更记录

## 2026-10-30

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
    return command_plugin(__name__, {
        "hello": {
            "help": "打招呼",
            "arguments": [{"name": "name"}],
            "executor": execute,
        }
    })
```

- 验收通过完整 aurora check：190 项 Python 测试、9 项工具链测试，Pyright basic 无错误。覆盖命令包独立新增与移除、外部入口显式启用、同步/异步执行器、自定义退出码、运行期状态恢复、重复 ID 和无效绑定拒绝；安装后的 CLI wheel 在独立环境中完成命令发现与 ctx 调用。

- CLI 分派在选择输出流后显式检查 None；无标准输出的环境须提供 output 文本流，各命令接收非空 TextIO。

- about 与 help 的表格使用 Rich 内置 box.SIMPLE，隐藏外框、保留表头分隔线，不设置隔行变暗。

- about 与 help 直接使用 Rich Table、Text 和 Console，表格展示无需项目级封装；插件帮助内容按字面量渲染。

- CLI 表格采用 Rich Table 原生默认边框、表头和行间样式；banner 使用原生标题，单元格保持字面量文本，重定向输出与文本渲染沿用 Rich 的终端处理。

- CLI 按职责组织为 main（进程入口）、commander（发现和分派）、parsing（参数转换）、declarations（声明接收）、host（运行期装配）与 commands/<name>（命令行为）。内置命令显式汇总，业务操作继续引用 core 公共 ID；旧项目仅提供目录组织和用户可见效果参考。
- help、ctx 和 donk 命令组在未选叶子命令时展示本级帮助；顶层 --help 包含已接收的扩展命令。帮助与项目工具命令不创建 ctx 或存储，长选项要求完整名称。常见错误输出简洁提示，--debug 显示完整异常。
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
- `examples/core_counter.py` 是仅依赖 core 的独立计数器应用，包含显式插件装配、装饰器声明、实例连接、操作调用、ctx 订阅、JSON 快照与重启恢复。运行方式：`uv run python examples/core_counter.py --data-dir build/counter-demo --name visits --amount 1`；同一目录和名称重复执行会继续累计，业务状态按名称区分。
- M1.5 验收通过 141 项 Python 测试、5 项工具链测试及完整 `pnpm check`。本次 core wheel 在仅安装 aurora-core 的独立环境中完成两次运行与状态恢复；示例自行管理启动和收尾，通用生命周期按 M1.6 实现。
- M1.6 提供 `Lifecycle`、`LifecycleComponent` 与 `install_lifecycle_slots`，沿用 prepare/start/stop 三个公共插槽。组件以宿主内唯一的实例标识显式声明依赖，缺失依赖、重复标识和依赖环在启动前拒绝；依赖先 prepare/start，依赖者先 stop，同级遵循显式装配顺序。
- 生命周期先恢复完整 ctx，再执行全部 prepare 和全部 start。启动失败或取消时清理已经尝试 prepare 的组件，包含部分初始化的当前组件；同时发生的启动与收尾错误通过异常组保留。恢复失败不执行最终写入，源快照保持原样。
- `Lifecycle.run` 跟踪宿主接收的调用；停止时拒绝新调用，执行组件的 `stop_accepting`，等待在途调用，超时后请求取消并等待清理。组件自行创建的任务由其 stop 处理器收束。默认超时为 10 秒，分别用于各个异步处理器及在途工作的等待、取消阶段；同步阻塞代码不被抢占。
- 组件 stop 成功后断开涉及该实例的连接；停止或取消收束失败保留尚未停止的依赖、ctx 和存储供重试，成功的 stop 处理器不重复执行。取消 stop 的等待者不会取消宿主收尾，可再次调用 stop 等待结果；收尾失败明确抛出并记录日志。
- 宿主在组件停止后独立执行持久化 close，确保最后的 ctx 写入落盘，再释放连接、存储与 ctx。禁用可选 stop 处理器不取消最终落盘；落盘失败时保留内存和存储，重试成功后才完成关闭。
- `examples/core_counter.py` 通过生命周期恢复状态、prepare 装配调用与订阅、run 执行业务、stop 取消订阅及最终落盘。运行命令和按名称累计语义保持稳定。
- M1.6 验收通过 158 项 Python 测试、5 项工具链测试及完整 `pnpm check`，Pyright basic 无错误。覆盖依赖顺序、部分启动失败、取消与超时、停止失败重试、最终写入恢复、可选处理器禁用、落盘失败重试和损坏快照保护；后续进入 M1.7 CLI 基础入口，再执行 M1.8 微内核集成验收。
