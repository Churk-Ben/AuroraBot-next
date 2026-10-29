# 变更记录

## 2026-10-29

- `aurorabot-ai` 为统一安装发行包，依赖独立的 bot、CLI 和 API 包，间接安装 core 与模型适配层；Python 导入名与公共 ID 保持各包归属。
- `uv sync --all-packages` 安装工作区及开发依赖，`uv run python scripts/check.py` 执行 Python 格式、静态检查和行为测试。
- 统一安装包仅提供依赖装配；命令行与服务入口随对应功能实现。
