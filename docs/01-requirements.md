# 需求与成功标准

## 用户、目标与边界

内容团队输入素材 ID 和希望发布时间。Agent 要读取合成素材，审核元数据及规则，查询已有排期，并保存**草稿**。范围不含真实发布、UI、线上部署和多 Agent。

“发布时间要求”在本实现中一律视作硬要求。请求时段冲突，Agent 可以提出最早可用替代时段，但在 `confirm_alternative: true` 前不得保存替代时段。任何结果中的 `published` 永远是 `false`。

## 成功标准与对应实现

| 验收点 | 证据 |
| --- | --- |
| 正常排期 | `examples/outputs/normal.json`，状态 `draft_saved` |
| 信息不足 | `examples/outputs/missing_info.json`，缺 `caption` 后阻断 |
| 规则风险 | `examples/outputs/rule_risk.json`，命中禁词后阻断 |
| 时段冲突 | `examples/outputs/conflict.json`，建议 19:00 且待确认 |
| 重复提交 | `examples/outputs/duplicate_second.json`，状态 `duplicate` |
| 保存失败 | `examples/outputs/save_failure.json`，明确 `failed` |

每个输出都带有步骤、工具参数、返回摘要、后续动作和决策依据的 `trace`。最大步数默认为 8，可由 CLI 的 `--max-steps` 修改；达到上限返回 `incomplete`。
