# 变更记录

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
