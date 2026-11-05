# 素材审核与发布排期 Agent

一个可离线运行、也可由 OpenAI 兼容模型驱动的 CLI Agent。它审核素材、查询时段并**只保存排期草稿**；它不会发布内容。

## 快速开始

要求 Python 3.10+，没有第三方运行时依赖。

```powershell
python -m unittest discover -s tests -v
python -m src.cli --request examples/inputs/normal.json --mode offline
```

默认草稿写入 `.runtime/drafts.json`（已被 Git 忽略）。每次 CLI 运行都会打印结构化 JSON，其中含 `trace`；如需保留输出：

```powershell
python -m src.cli --request examples/inputs/conflict.json --mode offline --output result.json
```

`--trace-output trace.json` 可将相同运行中的工具调用记录单独导出。

## 在线模型模式

复制 `.env.example` 的变量到当前 shell。CLI 不读取或输出密钥。

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-5.5"
python -m src.cli --request examples/inputs/conflict.json --mode openai
```

`OPENAI_BASE_URL` 默认为 `https://api.openai.com/v1`，因此也可指向实现 Responses API 的兼容服务。在线模式中模型每步只能选择白名单动作；本地策略层仍会阻止越权改期和发布。详见 [docs/02-solution.md](docs/02-solution.md)。

已提交两条真实模型运行记录：[`online_normal.json`](examples/outputs/online_normal.json) 展示可用时段后的保存草稿；[`online_conflict.json`](examples/outputs/online_conflict.json) 展示已占用时段后的待确认。两者的逐步工具记录位于 `examples/traces/`。

## 评审入口

- 需求与验收：[`docs/01-requirements.md`](docs/01-requirements.md)
- 设计与模型循环：[`docs/02-solution.md`](docs/02-solution.md)
- 测试/运行证据：[`docs/03-evaluation.md`](docs/03-evaluation.md)
- AI 使用说明：[`docs/04-ai-usage.md`](docs/04-ai-usage.md)
- 复盘：[`docs/05-retrospective.md`](docs/05-retrospective.md)
- 实际离线运行记录：[`examples/`](examples/)

## 项目结构

```text
src/       Agent、模型适配器和本地 Mock 工具
data/      合成素材、审核规则与排期初始数据
tests/     可执行单元/集成测试
examples/  输入、实际输出与 trace
docs/      交付说明
```

实际投入时间和已知限制记录在 [`docs/05-retrospective.md`](docs/05-retrospective.md)。
