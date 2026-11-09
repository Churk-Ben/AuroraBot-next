# 开发与验证

核对日期：2026-11-09。首次使用走[安装助手](../examples/START.md)，本页供维护者使用。

## 环境与检查

Python 使用 uv workspace，版本以各包 pyproject.toml 为准。Node / pnpm 以根 package.json 为准；pnpm 会按声明准备项目 Node 运行时，通过 pnpm exec 使用，系统全局 Node 不随之修改。

```powershell
uv sync --locked --all-packages
pnpm install --frozen-lockfile
pnpm exec uv run --locked aurora check
pnpm exec uv run --locked aurora check --full
```

默认检查包含格式、lint、Python / TypeScript 类型与快速边界测试；--test 跳过静态检查，--full 增加包内单测、前端、原生终端和耗时集成；--coverage 也使用完整测试范围。

按影响范围先验证。涉及生命周期、跨包契约或配置行为时再完成完整检查。纯文档只需检查链接、内容与差异。普通回归使用假模型或本机模拟传输，不调用真实供应商。

```powershell
uv run --locked pytest tests/e2e/test_onboarding.py tests/e2e/test_package_boundaries.py -q
uv build --all-packages --wheel --out-dir build/wheels
```

依赖或分发内容变化时，在干净环境安装 wheel，确认 control 无需 agent / 模型，agent 无需 bot / CLI / API；工作区导入不能替代验收。

## 测试与夹具

包内 unit / contract 位于 packages 下；跨包契约在 tests/contract，真实进程及跨包集成在 tests/e2e。tests/fixtures/runtime_apps 保留五组离线回归应用，供持久化、取消、包边界与常驻宿主测试使用，不再承担用户教学入口。

用户示例仅为 examples/onboarding。它复用 MCP 产品装配、CLI 宿主、模型工具执行和现有界面，不复制 ReAct 调度。初始化不启动模型或 MCP；普通验收通过假模型与本机 stdio 覆盖配置、工具回填和历史恢复。固定版本 terminal MCP 可单独检查目录与工具调用，不需真实模型。

不要通过删除有效断言或放宽容错让迁移测试通过。运行夹具需要的配置资源随夹具一起保留；修正入口后原有验收语义不变。

## 查询定义与插件

插件发现只登记定义，适合核对实际公共 ID，不会创建客户端或后台任务：

```powershell
uv run --locked aurora --data-dir build/onboarding id list
```

上面的目录应已由助手 --init 初始化。完整静态目录见[公共 ID 目录](aurorabot-id-catalog-v0.2.3.md)；MCP 动态工具只会在准备连接和读取目录后出现。公开接口以契约文件和测试为准，不照搬历史设计中的拟议 schema。

## 文档与提交

当前入口集中在 [INDEX.md](INDEX.md)，START.md 保持为首次启动短指南。配置、操作、上下文与架构分别维护，旧计划和讨论保留归档标记；变更与验收统一写入 CHAGELOG.md。

按项目 AGENTS.md 使用中文注释、docstring 与提交说明，小步提交，在功能分支验证后通过 PR 合并。README.md 和 AGENTS.md 的修改遵守用户确认规则；不改写用户数据来适配示例或测试。
