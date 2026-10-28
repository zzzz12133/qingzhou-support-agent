# 从零到一：把「基础客服机器人」做出来

这篇文档回答两个问题：

1. 如果从空文件夹开始，先做什么、后做什么？
2. 本仓库每一步落在哪些文件里，怎么验收？

> 技术栈是图里的组合：Spring Boot（Java 17）+ React 18 + Python Agent。不要一开始就追求 14 个模块全写完，先跑通一条「查订单 → 回答 → 流式展示」的竖切。

---

## 第 0 步：把范围砍到能演示

先只选三个场景：

| 场景 | 需要的工具 | 需要的知识 |
|---|---|---|
| 查物流 | `lookup_order` | 配送时效 |
| 判断退货 | `lookup_order` + `check_refund_eligibility` | 7 天无理由、VIP 15 天、质量问题 15 天 |
| 改地址 | `lookup_order` + 知识库 + `create_ticket` | 未发货免费改一次、已发货只能尝试拦截 |

再准备 5 个演示订单（`A1001`~`A1005`），覆盖运输中、待发货、已签收 4 天、已签收 40 天、VIP。**不要接真实订单系统**，否则第一天就卡在权限和数据脱敏上。

验收：三句话能说清 demo 的故事，且每个场景都有确定性的预期答案。

本仓库：`agent-service/app/tools.py` 的 `_demo_orders()`。

---

## 第 1 步：先定事件协议，再写代码

前后端不要互相等页面。先约定一次对话会发出哪些事件：

| 事件 | 作用 |
|---|---|
| `meta` | 会话 ID、消息 ID、用户消息 |
| `stage` | “理解问题 / 检索规则 / 生成答复” |
| `tool_start` | 工具名、参数、开始执行 |
| `tool_result` | 成功/失败、耗时、摘要 |
| `memory` | 当前画像、摘要、token 预算 |
| `citations` | 知识库切片及编号 |
| `token` | 增量文本 |
| `usage` | token 与耗时 |
| `grounding` | 依据是否核对通过 |
| `done` | 完整回答、消息 ID、轨迹 |
| `error` | 错误码、用户可读文案、是否可重试 |

Python 内部用 **NDJSON**（一行一个 JSON），Spring 再包装成浏览器 SSE。这样 Python 可以被单测直接消费，不依赖浏览器。

验收：不写任何 UI，用 `curl` 或 `httpx` 能打印出完整事件序列。

本仓库：`agent_service.app.agent.AgentService.stream`、`backend/.../ChatService.streamRun`。

---

## 第 2 步：Python Agent 先跑 Mock，不急着接大模型

Agent 最小闭环只有四件事：

```text
用户消息
  → 识别意图
  → 决定调用哪个工具
  → 把工具结果喂回模型
  → 输出最终答案
```

先写 `MockProvider`：它不“假装大模型”，而是根据意图返回确定的工具调用和答案。好处：

- 没有 API Key 也能开发、演示、跑测试；
- 工具链路出错时能排除模型因素；
- 后面接真实模型，只替换 provider，不改 Agent 循环。

工具循环的核心是 `max_tool_rounds`（本仓库 4 轮）和防重复签名。每次工具结果都以 `role=tool` 回填到 messages。

验收：问 `A1002 能退货吗？`，事件里依次出现：

```text
lookup_order
check_refund_eligibility
search_knowledge_base
done
```

本仓库：`agent-service/app/providers.py`、`agent.py`、`tools.py`。

---

## 第 3 步：工具要有“业务边界”，不是给模型一把万能刀

每个工具都要回答三个问题：

1. **什么时候必须调用？** 例如任何订单问题必须先 `lookup_order`。
2. **失败怎么表达？** 返回 `ok=false` + 人话摘要，不要让异常冒到 500。
3. **有没有副作用？** 本仓库只有 `create_ticket` 写文件；其余只读。

本仓库的五个工具：

| 工具 | 是否只读 | 输入 | 输出重点 |
|---|---|---|---|
| `lookup_order` | 是 | 订单号 | 状态、物流、预计送达、签收日 |
| `check_refund_eligibility` | 是 | 订单号、原因 | 是否可退、窗口、依据说明 |
| `search_knowledge_base` | 是 | 查询词 | 3 条切片、分数 |
| `create_ticket` | 写 | 订单、问题、紧急度 | 工单号 |
| `handoff_to_human` | 写 | 原因、紧急度 | 队列位置、在线时间 |

验收：工具返回的摘要足够让 Trace 面板看懂，不需要把完整 JSON 塞给用户。

---

## 第 4 步：RAG 的重点不是“检索”，是“敢引用”

本仓库没有引入向量数据库，用中文单字 + 二元组 BM25。对 17 个知识切片完全够用，而且可解释：

1. 把 Markdown 按 `##` 切片；
2. 标题加权，检索 query 做同义词扩展；
3. 返回切片 `id / title / snippet / score`；
4. Agent 给切片分配 `[1][2]` 编号；
5. `grounding_report` 检查回答里的编号是否真实存在；
6. 前端把引用做成可点击的卡片。

Mock 回答会主动带引用；真实模型由 System Prompt 强制要求“规则必须引用检索结果”。

验收：问“退货运费谁出”，回答应该明确两种情况并带 `[n]`，而不是只复述一段政策。

本仓库：`knowledge.py`、`guardrails.grounding_report`、`tools._search_knowledge`。

---

## 第 5 步：三层记忆，解决“越聊越忘”和“越聊越贵”

上下文结构固定为：

```text
System 规则
长期记忆（结构化画像）
历史摘要（更早的对话压缩）
最近 12 条消息（滑动窗口）
当前问题
```

`memory.py` 做四件事：

1. `observe_user`：抽取称呼、城市、联系偏好、订单号；
2. `observe_order`：从工具结果更新会员等级、商品、收件人；
3. `_refresh_summary`：超过 16 条时把窗口外消息压成摘要（本仓库为抽取式降级）；
4. `build`：估算 token，超 3200 就从最旧的对话开始丢，并在 `memory` 事件里报告。

`rewrite_query` 负责指代消解：

```text
上一轮：查一下 A1001
这一轮：那它到哪了？
→ hidden query 补入上下文订单 A1001
```

验收：先问 A1001，再问“那它到哪了”，工具参数仍然是 A1001；右侧记忆面板能看到 `lastOrderId`。

---

## 第 6 步：可靠性与成本，决定它能不能上线

按优先级加：

| 能力 | 做法 | 代码 |
|---|---|---|
| 防重复 | `clientMessageId` + 10 分钟幂等缓存 | `ChatService.start` |
| 会话互斥 | 同一会话只允许一个活跃 run | `activeBySession` |
| 限流 | 滑动窗口，单用户 20 次/分钟 | `RateLimiter.java` |
| 并发上限 | 单用户最多 2 个运行；线程池满则 503 | `ChatService` |
| 停止 | 前端 abort + Spring 同步取消 + Python `task.cancel` | `cancelInternal` |
| 超时 | HttpClient 超时、SSE 120s、模型 25s | `application.yml` |
| 模型熔断 | 连续失败 2 次打开 30s，切下一个 provider | `providers.CircuitBreaker` |
| 缓存 | 主题 + 相似度，仅政策类、非个人问题 | `cache.py` |

注意“停止”的顺序：**先同步通知 Python，再关闭本地流**。如果先关流，Python 的流任务可能先被断连清理，取消请求就找不到任务。本项目还加了 60 秒取消墓碑，处理取消请求早于任务注册的竞态。

验收：点停止后，UI 出现“已停止生成”，Python 取消计数 +1，且不会在几秒后偷偷补一条完整回答。

---

## 第 7 步：Spring Boot 网关，别让它只是转发

网关至少承担：

- 会话 CRUD 与落盘（`.data/sessions/*.json`）；
- 用户归属校验；
- SSE 生命周期与客户端断开检测；
- 把 Python 的 NDJSON 逐行转成 SSE；
- 幂等、限流、并发、活跃 run 注册表；
- 取消接口：`POST /api/chat/{messageId}/cancel`；
- Agent 健康检查与会话记忆查询。

一个容易踩的坑：**SSE 的 meta 要尽早返回**，否则用户会盯着空白页等模型。本项目的 meta 由 Spring 自己发，Python 的同名 meta 被过滤，避免重复。

另一个坑：`SseEmitter` 的 `onCompletion` 在正常 `complete()` 时也会触发。用 `run.isFinished()` + `beginCancel()` 防止正常结束被当成用户取消。

---

## 第 8 步：React 只做三件难事

1. **把 token 流刷得顺**
   - 每个 token 不直接 `setState`；
   - 先塞进 `tokenBufferRef`；
   - 用 `requestAnimationFrame` 每帧合并一次；
   - `done` 时用最终完整文本覆盖，防止尾包丢失。

2. **停止要“先通知，再 abort”**
   - 调 `/cancel`（不 await 阻塞 UI）；
   - 立即 `AbortController.abort()`；
   - 本地把消息标记为 `stopped`，保留 partial。

3. **观察窗**
   - 工具事件实时插进 timeline；
   - 引用、memory、usage、grounding 分栏展示；
   - 会话重新打开时，从最后一条 assistant 的 metadata 恢复轨迹和引用。

验收：连续发两条消息，第二条要能看见第一条的 tool trace 已结束；点引用数字能打开对应切片。

本仓库：`frontend/src/App.jsx`、`components/ChatMessage.jsx`、`components/Inspector.jsx`。

---

## 第 9 步：测试与验收清单

### 自动化

```powershell
cd agent-service
python -m unittest discover -s tests -v

cd ..\backend
mvn test
```

Python 测试覆盖 6 条主路径；Java 测试覆盖文件持久化、越权访问、限流窗口。

### 手工验收

- [ ] 无 Key 启动，问 A1001 能出物流。
- [ ] A1002 退货回答带引用，且窗口天数正确。
- [ ] 回复“登记退货”能创建工单。
- [ ] A1003 改地址走未发货分支。
- [ ] 输入“忽略之前的指令”不调用模型。
- [ ] 点停止后无“补刀”式完整回答。
- [ ] 刷新页面/复制 session URL 能恢复消息。
- [ ] 把 `DEEPSEEK_API_KEY` 填错，仍然能降级回答并显示提示。
- [ ] 连续快速发消息，第 21 次返回 429。

---

## 第 10 步：再往生产走

按这个顺序补，不要反过来：

1. **认证**：JWT/OIDC，userId 从 token 取，不信任前端。
2. **真实数据**：订单工具接内部 API，工具层做超时、重试、权限和审计。
3. **数据库**：PostgreSQL 存会话/消息，Redis 存限流、缓存、活跃 run。
4. **模型流**：把 provider 换成原生 token 流，保留当前事件协议。
5. **评估集**：至少覆盖 50 条真实客服问题，统计事实准确率、引用正确率、拒答率。
6. **人工坐席**：转人工不是返回一个假队列，要接工单/IM。
7. **可观测性**：每轮 traceId、模型耗时、工具失败率、缓存命中率、降级率。
8. **合规**：数据留存周期、脱敏、审计、敏感行业话术。

到这里，它才从“能演示”变成“能上线”。
