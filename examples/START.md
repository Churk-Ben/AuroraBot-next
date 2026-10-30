# 启动示例

所有命令均在仓库根目录执行。需要 Python 3.12+ 和 `uv`；首次运行先安装 Python 工作区：

```powershell
uv sync --all-packages
```

这些示例只运行 Python，无需启动前端，也无需模型密钥或联网调用服务。

| 示例 | 入口 | 演示内容 |
| --- | --- | --- |
| 持久化计数器 | [core_counter/main.py](core_counter/main.py) | core 插件声明、实例连接、ctx 订阅、退出落盘与重启恢复 |
| 控制组件运转 | [control_flow/main.py](control_flow/main.py) | 串行、条件循环、分支、并行、地址握手与 ctx 状态观察 |
| 假模型调用 | [model_call/main.py](model_call/main.py) | 模型输入、流式文本、完整响应、部分输出保留和客户端关闭 |

## 持久化计数器

```powershell
uv run python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount 2
uv run python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount 3
```

使用全新的数据目录时，两次分别输出：

```text
visits: 2
visits: 5
```

`--data-dir` 为必填参数；`--name` 默认是 `default`，`--amount` 默认是 `1`，可以为负数。同一数据目录下，同名计数器持续累加，不同名称分别保存：

```powershell
uv run python examples/core_counter/main.py --data-dir build/counter-demo --name visits --amount -1
uv run python examples/core_counter/main.py --data-dir build/counter-demo --name another --amount 1
```

程序每次执行一个增量后退出。业务源码只依赖 `aurora_core`，适合从最小宿主开始阅读；它演示 core 的通用调用接口，计数增量及结果通过函数参数和返回值传递。

## 控制组件运转

```powershell
uv run python examples/control_flow/main.py --data-dir build/control-flow-demo
```

默认循环 3 次，每步等待 0.2 秒。装配结构如下：

```text
Serial root
├─ 初始化计数为 0
├─ While loop：计数小于目标次数
│  └─ Serial body
│     ├─ 计数加 1
│     └─ Branch parity
│        ├─ odd：记录奇数分支
│        └─ even：记录偶数分支
├─ Parallel parallel：并发上限 2
│  ├─ double：计算两倍值
│  └─ square：计算平方
└─ 汇总结果
```

输出包含本次运行 ID、`[控制]` 状态转移和 `[状态]` 业务写入。你会看到奇数、偶数、奇数三次分支；两项计算都进入 `running` 后，陆续写入各自结果。默认参数的最后输出为：

```text
结果: {"count": 3, "double": 6, "square": 9}
快照: build\control-flow-demo\framework\ctx.json
```

路径分隔符随系统变化。可调整运行速度和循环次数：

```powershell
uv run python examples/control_flow/main.py --data-dir build/control-flow-demo --steps 4 --delay 0.5
```

这次结果是 `{"count": 4, "double": 8, "square": 16}`。`--steps` 必须为正整数；`--delay` 是非负秒数，设为 `0` 可以快速执行。每次启动创建新的运行 ID，计数从 0 开始。示例收尾时只保留最近一次运行的一条结果，中间值和历史结果由示例清理，程序不续跑历史调用。

最终快照中这条记录的 `value` 为：

```json
{"status": "completed", "result": {"count": 4, "double": 8, "square": 16}}
```

controller 在 ctx 中只保留在途状态，每次调用先通知终态、再删除本次状态，不累计调用树。运行期间的自动快照可能包含在途状态，正常收尾后会清理；示例启动时也会清理恢复出的控制状态。业务数据保留多久由应用决定，此示例选择只保留最新结果。

想观察取消，可以把每步等待调长，然后在终端按一次 `Ctrl+C`：

```powershell
uv run python examples/control_flow/main.py --data-dir build/control-flow-demo --steps 20 --delay 2
```

正在执行的控制调用会通知 `cancelled` 并清理本次控制状态；并行计算已启动时也会完成取消清理。最终快照保留一条 `{"status": "cancelled"}` 结果，程序以退出码 `130` 结束。执行失败时同样只保留一条 `{"status": "failed"}`，异常继续报告给终端。

阅读源码时，可先看 `assemble()`：业务执行函数包装成 `ExecutionPlug`，通过 `ExecutionSlot.connect()` 建立连接。握手结果中的 `plug.states` 和 `slot_states` 提供 ctx 地址；调用时仅传递运行和执行身份，业务数据由组件自行读写 ctx。`observe()` 订阅 ctx 变化以展示过程，`run()` 负责宿主生命周期与落盘。示例使用局部代码约定，没有独立 schema。

## 假模型调用

```powershell
uv run python examples/model_call/main.py --data-dir build/model-call-demo --text 你好
```

串行装配执行“准备输入 → ModelCall → 读取结果”。假模型根据输入确定性地返回三段文本，默认每段等待 0.2 秒，最终输出：

```text
假模型收到：你好。
状态: completed
结束原因: stop
```

`ModelCall` 从 ctx 读取请求，在同一个输出地址累计文本和完整工具请求；执行插头只接收运行与调用身份。响应流由调用组件关闭，客户端由宿主停止阶段关闭。每次示例退出只保留最新输出，不保存输入或片段历史。completed 表示这次模型请求完成；模型可因 stop、tool_calls、length 或 content_filter 结束，后续业务行为由装配决定。

显式使用完整响应接口，或观察部分文本后的失败：

```powershell
uv run python examples/model_call/main.py --data-dir build/model-call-demo --no-stream
uv run python examples/model_call/main.py --data-dir build/model-call-demo --fail
```

`--fail` 在流式输出“假模型收到：你好”后以退出码 `1` 结束；快照中的同一条输出保留文本并标记 `failed`。完整响应接口在成功返回之前不会提供部分文本。

观察取消时可以使用 `--delay 2`，收到第一段文本后按一次 `Ctrl+C`；已收到的文本仍保存在快照中，状态为 `cancelled`，退出码为 `130`。`--delay 0` 可快速运行。此示例使用假模型，不调用真实服务，也不执行工具。

## 阅读与改装组件装配

控制和模型示例中的组件定义、实例与执行身份分别管理：

| 名称 | 示例中的含义 |
| --- | --- |
| definition_id | 组件类或局部执行函数的定义；例如 Serial.definition_id 为 `org.aurora.bot:handlers/control/serial` |
| instance_id | 同一定义下的具体实例；示例显式命名 root、body 等，省略则生成 UUID |
| run_id | 每次启动的业务运行身份，父子调用共享 |
| execution_id | 每次调用独立生成，循环再次调用同一实例时也会变化 |
| reference | `definition_id.instance_id` 展示引用，不用它创建 Id |

可从 `assemble()` 中的以下调用顺序阅读；这些片段需要示例中已经创建的 ctx、hooks、registry、client 与状态定义，不是独立脚本：

1. `component_entries(definition_id, execute, execute, provider=...)` 为局部业务组件生成定义和执行插头登记项，装配负责登记。
2. `ExecutionPlug(definition_id, execute, instance_id="worker", states=...)` 包装业务函数，提供约定的 ctx 地址。
3. `ExecutionSlot(Serial.definition_id, hooks, instance_id="root")` 创建根串行组件的插槽；`Serial(ctx, slot)` 和 `slot.connect(plug)` 完成实例装配。
4. `ModelCall(ctx, client, instance_id="model", request_state=..., output_state=...)` 使用同一套身份与执行协议，向串行组件接入其 `.plug`。

各组件通过自己的 `/execute` 端口连接，有子组件的控制器暴露自己的 `/children` 端口。`StateBinding` 仅在显式 location 上加入 run_id，不自动加入 definition_id 或 instance_id；多实例是否共享业务地址由装配决定。共享 ModelCall 输出地址时须串行调用，传入同一客户端也不代表它支持任意并发。

查看当前内置插件的定义目录：

```powershell
uv run aurora --plugin aurora_bot.control --plugin aurora_bot.model --plugin aurora_model_adapter id list
```

该命令只登记所选插件并列出 ID、kind 和 provider，不启动示例或模型服务，不需要数据目录。局部示例组件在示例装配中登记，不在这份启动前目录里。完整已实现/规划状态见 [公共 ID 目录](../docs/aurorabot-id-catalog-v0.2.2.md)。

## 数据与常用操作

各示例分别使用自己的数据目录，不要让它们共用目录，也不要同时启动多个进程访问同一目录。快照恢复需要对应示例的状态定义。

- 完整状态快照位于 `<data-dir>/framework/ctx.json`，可用编辑器查看。
- 想从空状态开始，换一个新的 `--data-dir`，例如 `build/control-flow-demo-2`。
- `build/` 是 Git 忽略的本地运行目录。

查看全部参数：

```powershell
uv run python examples/core_counter/main.py --help
uv run python examples/control_flow/main.py --help
uv run python examples/model_call/main.py --help
```
