# 方案设计

## 调用流程

```text
模型选择下一动作 → 本地工具执行 → 结果写入可见状态 → 模型选择下一动作
       ↑                                                    ↓
       └──── 最大 8 步；阻断 / 待确认 / 保存结果时结束 ─────┘
```

动作白名单为 `read_material`、`check_rules`、`query_slots`、`save_draft`、`request_confirmation`、`block` 和 `finish`。每一次工具返回后，下一轮将包含已有的可见状态，因此模型能基于真实工具结果改变动作。比如 `conflict.json` 中，`query_slots` 返回 18:00 已占用、19:00 可用，下一动作变为 `request_confirmation`；而 `normal.json` 中查询结果可用，下一动作变为 `save_draft`。

执行骨架还会把当前阶段可选的 `allowed_actions` 传给模型，并在本地复核前置条件。这不会替模型伪造工具结果或最终决策理由；它避免模型跳过“读取 → 审核 → 查时段”等必要业务阶段。分支仍由模型观察工具结果后决定：真实 MiMo 记录中，时段可用时模型选择 `save_draft`，时段冲突且未确认时模型选择 `request_confirmation`。证据见 `examples/traces/online_normal.json` 与 `examples/traces/online_conflict.json`。

## 运行模式与取舍

`--mode openai` 通过标准库向 `POST {OPENAI_BASE_URL}/responses` 发起请求，要求在线决策服务只返回 `{"action":"...","reason":"..."}`。决策服务不直接调用本地函数：Agent 接收动作后调用工具，并把摘要传给下一轮。这使 Trace 可审计，并方便替换兼容服务。本项目为了零依赖离线评审，使用 HTTP 调用而非额外 SDK。

`--mode offline` 是确定性替身，覆盖相同的动作契约，目的是让测试和证据可重复。它仅用于流程和回归验证，不替代在线决策记录。

实际在线验证使用 `mimo-v2.6-flash`，通过小米 MiMo 的 OpenAI 兼容 Responses 接口运行；Base URL、模型名和密钥均从环境变量读取，密钥没有存入仓库。模型服务宣称兼容 OpenAI/Anthropic 协议，并给出 OpenAI 兼容 Base URL；本项目已用该配置产生上述两条实际 Trace。[MiMo-V2.6-Flash 官方说明](https://mimo.mi.com/models/en-US/mimo-v2.6-flash)

未引入额外编排框架：本题只有一个有上限、状态很小的工具循环，显式循环更容易审阅。替换 `DecisionActor` 即可接入其他兼容服务。

## 防护与失败策略

- 本地工具不存在“发布”函数。
- `save_draft` 前的守卫要求已查询时段；被占用的硬性时段须有 `confirm_alternative`，否则拒绝保存。
- 草稿以 `request_id` 作为幂等键，重复请求返回原 `draft_id`，不会新增记录。
- 保存工具返回失败时 Agent 必须继续观察该结果，再以 `save_failed` 返回。
- 模型 API 不可用、输出非 JSON 或越出动作白名单，返回 `MODEL_ERROR`，不继续执行工具。
- 即使模型动作在白名单内，生命周期前置条件（例如未审核不能保存）也在模型外验证；不安全动作返回 `MODEL_ERROR`，且不会执行相应工具。
