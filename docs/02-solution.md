# 方案设计

## 调用流程

```text
模型选择下一动作 → 本地工具执行 → 结果写入可见状态 → 模型选择下一动作
       ↑                                                    ↓
       └──── 最大 8 步；阻断 / 待确认 / 保存结果时结束 ─────┘
```

动作白名单为 `read_material`、`check_rules`、`query_slots`、`save_draft`、`request_confirmation`、`block` 和 `finish`。每一次工具返回后，下一轮将包含已有的可见状态，因此模型能基于真实工具结果改变动作。比如 `conflict.json` 中，`query_slots` 返回 18:00 已占用、19:00 可用，下一动作变为 `request_confirmation`；而 `normal.json` 中查询结果可用，下一动作变为 `save_draft`。

## 模式和取舍

`--mode openai` 通过标准库向 `POST {OPENAI_BASE_URL}/responses` 发起 Responses API 请求，要求模型只返回 `{"action":"...","reason":"..."}`。模型并不直接调用本地函数：Agent 收到动作后调用工具，并把摘要传给下一轮。这使 Trace 可审计并方便替换 API 服务。官方 Python SDK 也将 Responses API 作为主要文本接口；本项目为了零依赖离线评审，使用等价 HTTP 调用。[官方 Python API 文档](https://developers.openai.com/api/reference/python)

`--mode offline` 是确定性替身，覆盖相同的动作契约，目的是让测试和证据可重复。它不能证明真实模型会作出同等判断，也不应被称为真实 LLM ReAct 的效果证据。

没有引入 LangGraph 等编排框架：本题只有一个有上限、状态很小的工具循环，显式循环更容易审阅。框架不是能力边界；替换 `DecisionActor` 即可接入框架或其他模型。

## 防护与失败策略

- 本地工具不存在“发布”函数。
- `save_draft` 前的守卫要求已查询时段；被占用的硬性时段须有 `confirm_alternative`，否则拒绝保存。
- 草稿以 `request_id` 作为幂等键，重复请求返回原 `draft_id`，不会新增记录。
- 保存工具返回失败时 Agent 必须继续观察该结果，再以 `save_failed` 返回。
- 模型 API 不可用、输出非 JSON 或越出动作白名单，返回 `MODEL_ERROR`，不继续执行工具。
- 即使模型动作在白名单内，生命周期前置条件（例如未审核不能保存）也在模型外验证；不安全动作返回 `MODEL_ERROR`，且不会执行相应工具。
