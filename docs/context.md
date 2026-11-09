# 上下文与运行

核对日期：2026-11-09。本页描述当前代码，预算单位是字符或字节，不代表供应商 token。安装助手仅启用普通 ReAct 和终端工具，未启用本页的主动行为。

## 主推理模型的每次输入

按顺序发送：system_prompt、临时 business_context（启用时）、保留的 user / assistant / tool 历史；另附当前已连接工具的全部定义。工具往返中的 assistant 调用、返回及必要的 reasoning_content / thinking_blocks 保留。

临时业务视图不写入消息历史。但 cadence 引导包含当时的 business 快照，会作为 user 消息持久化，所以历史引导与最新视图可能重复。工具结果也会随保留历史重复发送，MCP 当前整体保留工具结果对象，不自动去重 content 与 structuredContent。

业务视图包含近期事件、保留的环境观察、未归档笔记和最近行动证据，按启用类别分配字符预算，优先最新材料。abridged 表示正文截短，omitted 只计当前候选中因预算省略的条目；不是完整归档，也不表示事项已完成。

实现：[ReActDefaults](../packages/aurora_agent/src/aurora_agent/react_defaults.py)、[业务视图](../packages/aurora_bot/src/aurora_bot/context_view.py)。

## 输入预算与历史

Bot 的 input_budget 开启后对完整应用层模型请求限制 JSON 文本字符，并限制内嵌文件合计 10 MiB。system、临时视图、工具定义保留；超过预算时从请求中省略较早的完整交流段，至少保留最新交流。当前交流加固定输入仍超限时抛错，不拆断工具调用关系。

它不生成摘要，不压缩工具正文，不删除持久历史。max_iterations 限制一次运行的迭代次数，不限制跨运行历史。供应商传输还可能增加协议包装，字符预算不能替代真实 token 统计。

| 配置 | 包模板默认值 | 安装助手 |
| --- | --- | --- |
| context_view.enabled | true | false |
| context_view.max_chars | 12000 | 未使用 |
| input_budget.enabled | false | true |
| input_budget.max_chars | 128000 | 48000 |
| max_iterations | 8 | 12 |

既有用户 TOML 不因模板变化而更新。实现：[ModelInputBudget](../packages/aurora_agent/src/aurora_agent/input_budget.py)。

## cadence 决策

启用 aurora_bot.cadence 后，省略 decision 表时按原样转交世界记录；显式配置 decision 后使用 choice 模型判断。

决策输入包含观察时间、Bot 是否忙碌与 run_id、上次引导时间、业务视图、判断指令和 observe / attend_events / review_work 三个选项。不携带主模型整段对话或工具定义。决策视图预算为 max_chars 减 2048，应用层完整 ChoiceRequest 再检查 max_chars。

```toml
[decision]
model_role = "cadence"
active_seconds = 5.0
idle_seconds = 180.0
half_life_seconds = 60.0
jitter_ratio = 0.2
timeout_seconds = 15.0
max_chars = 12000
```

model_role 必须绑定 choice 适配器；聊天模型适配器不能直接替代。节律受 ctx 活动刺激并随静默衰减，在窗口内随机判断，静默时仍会检查。内部反馈和被动时间刺激逐次衰减，世界事件和环境变化可重新激活。

observe 只更新观察位置，不推进事件投递位置；相同未投递事件、未归档笔记和证据可能在下次请求再次出现。Bot 忙碌也可接受补充引导。当前没有按材料哈希跳过相同请求的机制，累计消耗取决于单次输入和调用频率。

观察、投递、接纳、运行完成和业务完成是不同状态。改变 cadence 模式应使用独立数据目录，不自动转换既有 checkpoint；错误会暂停自动转交，不靠重启或清空状态掩盖不确定副作用。

实现：[cadence](../packages/aurora_bot/src/aurora_bot/cadence/forwarder.py)、[节律](../packages/aurora_bot/src/aurora_bot/cadence/rhythm.py)。

## 世界、笔记与证据

世界事件原文持久归档，ctx 只保留近期窗口；环境按来源保留有界观察。world_read_event 按 record_id 分页读取原文，读取不表示消费或处理。QQ 图片事件中的有效图片引用可由 cadence 转为模型图片输入，仍由主模型处理，不自动下载或另开视觉模型。

notes.enabled 提供 notes_write / notes_read / notes_list，笔记按实例隔离并随快照保存。未归档笔记可进入业务视图，记录和引用不证明外部动作成功。

actions.enabled 提供工具调用证据和 actions_read 分页查询。completed / failed 表示工具返回结果，unknown 需要核实，不能视作未执行或要求重试。证据缺失也不能证明动作未发生。

## 计划唤醒与自身控制

self_control.enabled 提供 wake_schedule / wake_list / wake_cancel、bot_status、bot_autonomy 与 bot_finish。唤醒只向既有运行所有者提交引导，不创建第二个调度所有者；计划到期不等于业务动作完成。

bot_finish 正常结束当前运行，不暂停 cadence。bot_autonomy(paused=true) 暂停自动引导，包括计划唤醒，直接交流仍可用。恢复后按当前事实判断，不自动重放未完成的外部动作。

本次示例和文档整理没有修改上述上下文机制；工具结果压缩、去重与精确 token 用量统计仍需独立实现。
