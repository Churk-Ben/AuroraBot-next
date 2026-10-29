# 变更记录

## 2026-10-29

- `aurorabot-ai` 为统一安装发行包，依赖独立的 bot、CLI 和 API 包，间接安装 core 与模型适配层；Python 导入名与公共 ID 保持各包归属。
- `uv sync --all-packages` 与 `pnpm install` 安装工作区依赖，`pnpm check` 经 `scripts/check.ts` 执行 Python 格式、静态检查、行为测试及 TS 工作区入口加载检查。
- `scripts/` 首选 Node/TypeScript 脚本；检查入口使用 Node 原生类型擦除，最低 Node 版本为 22.6.0。
- 统一安装包仅提供依赖装配；命令行与服务入口随对应功能实现。
- core 提供不可变 `Id`、公开定义登记项与唯一总表；批量登记检查通过后统一写入，显式替换要求目标存在。短名仅在明确的命名空间与域中解析，歧义时报错。
- 宿主直接建立注册表目录与九个 core 分类注册表；resources 接收 resource、assembly、contract，并保留原 kind。
- 插件发现使用 `aurorabot.plugins` entry point group。入口指向无参数工厂，返回同名 `Plugin`；宿主只发现显式启用的入口，同名显式清单优先。必需插件须同时选中，缺失、入口歧义和导入失败明确报错。
- `register_plugins` 收集全部定义后原子登记；定义覆盖仅通过 `DefinitionRegistry.replace` 显式完成，不依赖发现顺序。
- 接收方通过 `rejection_reason` 评估声明，自行决定接口兼容性；登记与插槽关系分别产生 accepted/unconnected/rejected 诊断。缺席 CLI/API 时保留声明并 warning，其他资源仍可寻址；accepted 仅表示声明被接收，不表示实例已连接或执行。
- M0 验收覆盖 ID、原子登记、自举、插件发现、可选宿主诊断和工作区入口；后续 M1 实现 ctx、实例连接及生命周期。
