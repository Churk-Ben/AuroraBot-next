## 编码规范

- 以**中文**为项目的主要注释, 提交和docstring语言.
- 遵循小步提交的规范, 不在暂存区留存大量未提交更改. 提交时, 使用谷歌风格的提交信息, 以动词开头, 说明本次提交的目的.
- 不编写过程解释性解释, 一切改动造成的变化不描述过去状态.
- 与用户交互的过程中, 如要更改README.md或AGENTS.md, 需要获得用户的确认.
  - README.md文件一般是稳定的, 不要轻易改动他.
  - 你可以捕捉用户希望你遵循的规范, 并主动向用户确认是否记录到AGENTS.md中, 以便后续遵循.
- 如果你有任何忍耐不住想要记录的文本信息, 请使用[变更文档](docs/CHAGELOG.md), 你可以随意修改它, 但是请不要在此外的任何地方记录类似的文本了.

## 项目结构

```text
.
├── packages/
│   ├── aurora_core/           # 微内核
│   ├── aurora_model_adapter/  # 模型协议与适配
│   ├── aurora_bot/            # 默认装配与插件
│   ├── aurora_cli/            # 命令行交互
│   ├── aurora_api/            # HTTP / WS 传输
│   └── aurora_client/         # TS 共享 ctx 访问与连接
├── apps/
│   ├── aurora_tui/            # OpenTUI 终端界面
│   ├── aurora_panel/          # Vue Web 界面
│   ├── docsite/               # 文档站
│   └── landing/               # 落地页
├── docs/                     # 设计与公共 ID 文档
├── scripts/                  # 开发与按需生成脚本
└── tests/
    ├── unit/
    ├── contract/
    └── e2e/
```
