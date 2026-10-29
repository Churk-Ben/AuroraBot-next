# 变更记录

## 2026-10-29

- `aurorabot-ai` 为统一安装发行包，依赖独立的 bot、CLI 和 API 包，间接安装 core 与模型适配层；Python 导入名与公共 ID 保持各包归属。
- `uv sync --all-packages` 与 `pnpm install` 安装工作区依赖，`pnpm check` 经 `scripts/check.ts` 执行 Python 格式、静态检查、行为测试及 TS 工作区入口加载检查。
- `scripts/` 首选 Node/TypeScript 脚本；检查入口使用 Node 原生类型擦除，最低 Node 版本为 22.6.0。
- 统一安装包仅提供依赖装配；命令行与服务入口随对应功能实现。
- core 提供不可变 `Id`、公开定义登记项与唯一总表；批量登记检查通过后统一写入，显式替换要求目标存在。短名仅在明确的命名空间与域中解析，歧义时报错。
