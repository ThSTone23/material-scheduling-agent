# 验证结果

执行命令（在仓库根目录）：

```powershell
python -m unittest discover -s tests -v
python -m src.cli --request examples/inputs/normal.json --mode offline
```

本次离线运行的可审计输入、完整输出和 Trace 位于 `examples/inputs/`、`examples/outputs/` 与 `examples/traces/`。其中：

| 场景 | 输出文件 | 关键实际结果 |
| --- | --- | --- |
| 正常排期 | `normal.json` | 19:00 可用，保存 `draft-001` |
| 信息不足 | `missing_info.json` | 缺 `caption`，审核阻断，未查询时段 |
| 规则风险 | `rule_risk.json` | 禁词违规，审核阻断 |
| 时段冲突 | `conflict.json` | 18:00 占用，建议 19:00，`pending_confirmation=true` |
| 重复提交 | `duplicate_first.json` / `duplicate_second.json` | 第二次为 `duplicate`，同一个草稿 ID |
| 保存失败 | `save_failure.json` | 返回 `simulated_storage_unavailable` |

`tests/test_agent.py` 还断言了步数上限、绝不发布、替代时段需确认以及草稿数为 1。

## 失败与限制

素材、规则、日程和失败注入均为合成的本地 JSON；它们证明业务流程，而非第三方内容系统的可靠性。离线模式只验证流程。在线模型未在本仓库嵌入密钥或实际 API 输出，评审者可配置环境变量自行运行；模型偶尔产生非 JSON 时会安全失败为 `MODEL_ERROR`。
