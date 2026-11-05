# 验证结果

执行命令（在仓库根目录）：

```powershell
python -m unittest discover -s tests -v
python -m src.cli --request examples/inputs/normal.json --mode offline
```

本次离线运行的可审计输入、完整输出和 Trace 位于 `examples/inputs/`、`examples/outputs/` 与 `examples/traces/`；测试命令的实际输出保存于 `examples/test-results.txt`。其中：

| 场景 | 输出文件 | 关键实际结果 |
| --- | --- | --- |
| 正常排期 | `normal.json` | 19:00 可用，保存 `draft-001` |
| 信息不足 | `missing_info.json` | 缺 `caption`，审核阻断，未查询时段 |
| 规则风险 | `rule_risk.json` | 禁词违规，审核阻断 |
| 时段冲突 | `conflict.json` | 18:00 占用，建议 19:00，`pending_confirmation=true` |
| 重复提交 | `duplicate_first.json` / `duplicate_second.json` | 第二次为 `duplicate`，同一个草稿 ID |
| 保存失败 | `save_failure.json` | 返回 `simulated_storage_unavailable` |

## 真实模型动态决策证据

在线模型为 `mimo-v2.6-flash`，通过 OpenAI 兼容 Responses API 调用。以下文件是实际模型运行输出，不含 API Key：

| 不同工具结果 | 实际输出 | 实际 Trace | 观察到的下一动作 |
| --- | --- | --- | --- |
| `query_slots` 返回 19:00 可用 | `examples/outputs/online_normal.json` | `examples/traces/online_normal.json` | 模型选择 `save_draft`，工具返回 `saved` |
| `query_slots` 返回 18:00 被占用且有替代时段 | `examples/outputs/online_conflict.json` | `examples/traces/online_conflict.json` | 模型选择 `request_confirmation`，未保存草稿 |

`tests/test_agent.py` 还断言了步数上限、绝不发布、替代时段需确认以及草稿数为 1。

## 失败与限制

素材、规则、日程和失败注入均为合成的本地 JSON；它们证明业务流程，而非第三方内容系统的可靠性。离线模式只验证流程；在线 Trace 证明本次模型调用在两个关键分支上的决策，不代表对所有模型输出的充分评估。模型偶尔产生非 JSON 时会安全失败为 `MODEL_ERROR`。
