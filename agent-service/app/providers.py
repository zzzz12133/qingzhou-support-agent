from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import date
from typing import Any, Protocol

import httpx

from .config import ProviderConfig, Settings, resolve_provider_config
from .intent import retrieval_query
from .models import LLMResult, ToolCall, ToolOutcome, TurnContext
from .text_utils import truncate

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class Provider(Protocol):
    name: str
    label: str
    model: str
    is_mock: bool

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        context: TurnContext,
    ) -> LLMResult: ...


def _tool_call(name: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(id="call_" + uuid.uuid4().hex[:12], name=name, arguments=arguments)


def _cite(context: TurnContext, keyword: str) -> str:
    for index, citation in enumerate(context.citations, start=1):
        if keyword in citation.get("title", "") or keyword in citation.get("content", ""):
            return f"[{index}]"
    return f"[1]" if context.citations else ""


def _outcome_name(context: TurnContext, name: str) -> ToolOutcome | None:
    return next((item for item in reversed(context.tool_outcomes) if item.name == name), None)


class MockProvider:
    """零依赖演示模型：按意图规划工具，再用工具事实组装答案。

    它不是“假装大模型”，而是刻意做的确定性降级路径：
    没有 API Key 时也能完整演示工具调用、RAG、引用和流式 UI。
    """

    name = "mock"
    label = "本地演示模型"
    model = "mock-planner-v1"
    is_mock = True

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        context: TurnContext,
    ) -> LLMResult:
        await asyncio.sleep(0.12)
        intent = context.intent
        order_id = context.order_id
        lookup = _outcome_name(context, "lookup_order")

        if intent == "greeting" and not context.tool_outcomes:
            name = context.profile.get("name")
            city = context.profile.get("city")
            address = f"{name}" if name else "你"
            local = f"，看到你在{city}" if city else ""
            return LLMResult(
                f"你好，{address}{local}。我是晴舟，轻舟商城的售后助手。"
                "我可以帮你查订单物流、判断退换货条件、处理改址和保修问题，也能在需要时转人工。\n\n"
                "你可以直接发我订单号（例如 A1001），或者说一下遇到的问题。",
                provider=self.label,
            )

        if intent == "human":
            if not _outcome_name(context, "handoff_to_human"):
                return LLMResult(
                    "",
                    [_tool_call("handoff_to_human", {"reason": context.message, "urgency": "normal"})],
                    provider=self.label,
                )
            handoff = _outcome_name(context, "handoff_to_human")
            data = handoff.data if handoff else {}
            return LLMResult(
                f"已经帮你转接人工客服，前方约 **{data.get('queue_position', 3)} 人**，"
                f"预计 **{data.get('estimated_minutes', '3-6')} 分钟**接通。\n\n"
                f"人工在线时间是 {data.get('online_hours', '9:00-21:00')}。"
                "工单摘要里已经带上本次问题，接通后不用再重复描述。",
                provider=self.label,
            )

        # 支持上一轮答案后的动作追问，例如用户回复「帮我登记退货」。
        if ("登记" in context.message or "开工单" in context.message) and order_id:
            if not lookup:
                return LLMResult("", [_tool_call("lookup_order", {"order_id": order_id})], provider=self.label)
            if not _outcome_name(context, "create_ticket"):
                return LLMResult(
                    "",
                    [
                        _tool_call(
                            "create_ticket",
                            {
                                "order_id": order_id,
                                "issue": "用户确认登记退货/售后工单：" + truncate(context.message, 120),
                                "urgency": "normal",
                            },
                        )
                    ],
                    provider=self.label,
                )
            ticket = (_outcome_name(context, "create_ticket") or ToolOutcome("", False, "")).data.get("ticket", {})
            return LLMResult(
                f"已经登记好了，工单号 **{ticket.get('id', '处理中')}**。\n\n"
                f"- 关联订单：{order_id}\n"
                "- 当前状态：待售后专员受理\n"
                "- 处理时效：通常 2 小时内首次联系\n\n"
                "工单里已带上本次对话摘要。如果 2 小时还没人联系你，回复「转人工」我再帮你催。",
                provider=self.label,
            )

        if intent in {"order_status", "refund", "address_change", "warranty"}:
            if not order_id:
                return LLMResult(
                    "可以，我先帮你查。请发一下**订单号**（在「我的订单」详情页可以复制，例如 A1001）。\n\n"
                    "如果一时找不到，也可以告诉我收件手机号后四位，我帮你缩小范围。",
                    provider=self.label,
                )
            if not lookup:
                return LLMResult(
                    "",
                    [_tool_call("lookup_order", {"order_id": order_id})],
                    provider=self.label,
                )
            if not lookup.ok:
                return LLMResult(
                    f"我暂时没查到订单 **{order_id}**。麻烦核对一下订单号，"
                    "注意字母和数字不要漏；也可以发我收件手机号后四位，我再帮你查。",
                    provider=self.label,
                )

            if intent == "refund":
                if not _outcome_name(context, "check_refund_eligibility"):
                    return LLMResult(
                        "",
                        [
                            _tool_call(
                                "check_refund_eligibility",
                                {"order_id": order_id, "reason": context.message},
                            )
                        ],
                        provider=self.label,
                    )
                if not _outcome_name(context, "search_knowledge_base"):
                    return LLMResult(
                        "",
                        [_tool_call("search_knowledge_base", {"query": "退货 退款 七天无理由 运费"})],
                        provider=self.label,
                    )
                return LLMResult(self._refund_answer(context), provider=self.label)

            if intent == "address_change":
                if not _outcome_name(context, "search_knowledge_base"):
                    status = (lookup.data or {}).get("status_code")
                    query = "修改地址 未发货 免费" if status == "pending" else "修改地址 已发货 拦截 运费"
                    return LLMResult(
                        "",
                        [_tool_call("search_knowledge_base", {"query": query})],
                        provider=self.label,
                    )
                if not _outcome_name(context, "create_ticket"):
                    order_status = (lookup.data or {}).get("status_code")
                    return LLMResult(
                        "",
                        [
                            _tool_call(
                                "create_ticket",
                                {
                                    "order_id": order_id,
                                    "issue": f"用户申请修改收货地址（当前状态：{order_status}）",
                                    "urgency": "high",
                                },
                            )
                        ],
                        provider=self.label,
                    )
                return LLMResult(self._address_answer(context), provider=self.label)

            if intent == "warranty":
                if not _outcome_name(context, "search_knowledge_base"):
                    return LLMResult(
                        "",
                        [_tool_call("search_knowledge_base", {"query": "保修 质保 维修 漏水"})],
                        provider=self.label,
                    )
                return LLMResult(self._warranty_answer(context), provider=self.label)

            return LLMResult(self._order_answer(context), provider=self.label)

        # 政策/一般咨询：先检索，再基于命中内容回答，避免空口编规则。
        if not _outcome_name(context, "search_knowledge_base"):
            return LLMResult(
                "",
                [_tool_call("search_knowledge_base", {"query": retrieval_query("policy", context.message)})],
                provider=self.label,
            )
        if context.citations:
            return LLMResult(self._policy_answer(context), provider=self.label)
        return LLMResult(
            "这个问题我暂时没有在平台知识库里找到可引用的规则，不想给你不确定的答案。\n\n"
            "你可以补充一下具体商品或订单场景；如果比较急，我可以帮你转人工核实。",
            provider=self.label,
        )

    def _refund_answer(self, context: TurnContext) -> str:
        order = (_outcome_name(context, "lookup_order") or ToolOutcome("", False, "")).data
        check = (_outcome_name(context, "check_refund_eligibility") or ToolOutcome("", False, "")).data
        cite = _cite(context, "退货") or _cite(context, "退款")
        eligible = check.get("eligible")
        product = order.get("product", "该商品")
        elapsed = check.get("days_since_delivery", 0)
        window = check.get("window_days") or "—"
        reason_type = check.get("reason_type", "退货")
        note = check.get("note", "")

        if eligible:
            return (
                f"**结论：可以申请退货。**\n"
                f"订单 {order.get('order_id')} 的「{product}」已签收第 **{elapsed} 天**，"
                f"符合 **{window} 天{reason_type}** 条件{cite}。\n\n"
                f"- 规则：{note}\n"
                "- 路径：订单详情 → 申请售后 → 退货退款，上传商品和包装照片\n"
                "- 退款：仓库验收后 1-3 个工作日发起，原路退回"
                + (f"{_cite(context, '退款到账')}" if _cite(context, "退款到账") else "")
                + "\n\n需要我帮你登记退货工单吗？回复「登记退货」即可。"
            )
        if check.get("reason_type") == "未发货取消":
            return (
                f"**结论：可以直接取消并全额退款。**\n"
                f"订单 {order.get('order_id')} 目前**尚未发货**，无需走退货质检流程{cite}。"
                "在订单详情点击「取消订单」即可，退款一般原路退回。\n\n"
                "如果已经不想等发货，我可以帮你转售后确认。"
            )
        return (
            f"**结论：这笔订单已超过无理由退货窗口。**\n"
            f"订单 {order.get('order_id')} 已签收第 **{elapsed} 天**，普通会员无理由退货为 7 天{cite}。\n\n"
            f"- 若商品存在漏水、破损等质量问题，15 天内仍可申请质量退换；\n"
            "- 超过 15 天的质量问题，可以走 1 年质保检测。\n\n"
            "要帮你转保修或人工复核吗？"
        )

    def _address_answer(self, context: TurnContext) -> str:
        order = (_outcome_name(context, "lookup_order") or ToolOutcome("", False, "")).data
        ticket = (_outcome_name(context, "create_ticket") or ToolOutcome("", False, "")).data.get("ticket", {})
        cite = _cite(context, "修改") or _cite(context, "配送")
        if order.get("status_code") == "pending":
            headline = "订单还没发货，可以免费修改一次收货地址"
            next_step = "已帮你登记改址工单，售后会在发货前联系你确认新地址。"
            extra = "- 未发货前改址免费，且只能修改一次"
        else:
            headline = "包裹已经发出，系统内不能直接改址"
            next_step = "已帮你登记改址工单，售后会尝试联系承运商拦截；不保证成功。"
            extra = "- 若拦截失败，可选择拒收后重新下单，已产生的运费不退"
        return (
            f"**{headline}。**{cite}\n"
            f"订单 {order.get('order_id')} 当前状态：**{order.get('status')}**，"
            f"商品：{order.get('product')}。\n\n"
            f"{next_step}\n"
            f"- 工单号：**{ticket.get('id', '处理中')}**\n"
            f"{extra}\n\n"
            "请把新地址发在对话里，我补充到工单备注。"
        )

    def _warranty_answer(self, context: TurnContext) -> str:
        order = (_outcome_name(context, "lookup_order") or ToolOutcome("", False, "")).data
        cite = _cite(context, "保修") or _cite(context, "质保")
        return (
            f"订单 {order.get('order_id')} 的「{order.get('product')}」在 **1 年质保**范围内{cite}。\n\n"
            "- 覆盖：内胆脱焊、真空失效、杯盖密封圈非人为损坏\n"
            "- 不覆盖：磕碰、摔坏、自行拆修\n"
            "- 流程：提交问题照片/视频 → 寄修检测（约 7-15 个工作日）→ 确认保修后维修\n\n"
            "你这个杯子具体是**漏水、不保温，还是杯盖问题**？我帮你判断是否属于保修范围。"
        )

    def _order_answer(self, context: TurnContext) -> str:
        order = (_outcome_name(context, "lookup_order") or ToolOutcome("", False, "")).data
        if order.get("status_code") == "pending":
            status_line = f"仓库已接单，预计 **{order.get('estimated_text')}**。"
        elif order.get("status_code") == "delivered":
            status_line = f"已于 **{order.get('estimated_text')}** 签收。"
        else:
            status_line = f"预计 **{order.get('estimated_text')}** 送达。"
        tracking = order.get("tracking_no") or "暂未生成运单号"
        carrier = order.get("carrier") or "待分配承运商"
        return (
            f"查到订单 **{order.get('order_id')}**，当前状态：**{order.get('status')}**。\n"
            f"- 商品：{order.get('product')} × {order.get('quantity')}\n"
            f"- 物流：{carrier} · {tracking}\n"
            f"- 最新：{order.get('latest_event')}\n"
            f"- 时效：{status_line}\n\n"
            + ("需要我帮你登记物流异常或催发货吗？" if order.get("status_code") == "shipped" else "还需要我帮你处理什么？")
        )

    def _policy_answer(self, context: TurnContext) -> str:
        message = context.message

        def find(*keywords: str) -> tuple[int, dict[str, Any]] | None:
            for index, citation in enumerate(context.citations, start=1):
                haystack = (citation.get("title", "") + citation.get("content", ""))
                if all(keyword in haystack for keyword in keywords):
                    return index, citation
            return None

        if "退" in message and "运费" in message:
            hit = find("退货运费") or find("寄回运费")
            if hit:
                index, _ = hit
                return (
                    f"退货运费分两种情况：\n"
                    f"- **无理由退货**：寄回运费由你承担\n"
                    f"- **质量问题**：商家承担往返运费，需先上传问题照片/视频\n\n"
                    f"建议使用可查询轨迹的快递并保留寄件凭证，不要直接用到付 [{index}]。"
                    "如果是质量问题，把订单号和问题照片发我，我帮你登记。"
                )
        if "到账" in message or "退款多久" in message:
            hit = find("退款到账") or find("退款", "到账")
            if hit:
                index, _ = hit
                return (
                    f"退款到账分两步：\n"
                    f"- 仓库验收通过后 **1-3 个工作日**发起退款\n"
                    f"- 原路退回一般 **1-7 个工作日**到账，以支付渠道为准 [{index}]\n\n"
                    "如果超过 7 个工作日还没到账，把订单号发我，我帮你查退款单状态。"
                )
        if "发票" in message:
            hit = find("发票")
            if hit:
                index, _ = hit
                return (
                    f"电子普通发票会在**确认收货后 7 个工作日内**开出，可在订单详情下载 [{index}]。\n\n"
                    "- 企业抬头请在申请时填写税号\n"
                    "- 发票开出后 30 天内可申请重开一次"
                )
        if "保修" in message or "质保" in message or "维修" in message:
            hit = find("保修") or find("质保")
            if hit:
                index, _ = hit
                return (
                    f"云朵系列保温杯提供 **1 年质保**，杯盖、密封圈等配件保修 3 个月 [{index}]。\n\n"
                    "- 覆盖：内胆脱焊、真空失效、非人为的密封损坏\n"
                    "- 不覆盖：磕碰、摔坏、自行拆修\n"
                    "- 寄修检测一般 7-15 个工作日"
                )
        if "包邮" in message or "运费" in message:
            hit = find("运费") or find("包邮")
            if hit:
                index, _ = hit
                return (
                    f"全场满 **99 元包邮**，新疆、西藏、内蒙古部分区域需补 15 元运费 [{index}]。\n\n"
                    "默认使用顺丰或京东物流，暂不支持指定快递。把收货地区发我，我可以帮你确认是否在包邮范围。"
                )
        if "隐私" in message or "验证码" in message or "密码" in message:
            hit = find("隐私")
            if hit:
                index, _ = hit
                return (
                    f"客服不会索要登录密码、短信验证码、银行卡密码或完整身份证号 [{index}]。\n\n"
                    "核对订单只需要订单号或收件手机号后四位。任何索要验证码的“客服”都不要相信。"
                )

        top = context.citations[:2]
        if not top:
            return "我暂时没有检索到可引用的规则，建议转人工核实。"
        lines = ["根据平台现行规则：\n"]
        for index, citation in enumerate(top, start=1):
            snippet = citation.get("snippet", "").strip()
            lines.append(f"- **{citation.get('title', '平台规则')}**：{truncate(snippet, 112)} [{index}]")
        lines.append("\n如果你有具体订单，发我订单号，我可以结合签收时间给出确定结论。")
        return "\n".join(lines)


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
        self.label = config.label
        self.model = config.model
        self.is_mock = False

    @property
    def endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        context: TurnContext,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "temperature": 0.2,
            "max_tokens": 800,
            "tools": tools,
            "tool_choice": "auto",
        }
        timeout = httpx.Timeout(self.config.timeout, connect=min(8.0, self.config.timeout))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise ProviderError(f"{self.label} 网络超时或连接失败", retryable=True) from exc

        if response.status_code >= 400:
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            raise ProviderError(
                f"{self.label} 返回 HTTP {response.status_code}",
                retryable=retryable,
                status=response.status_code,
            )
        try:
            data = response.json()
            choice = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.label} 返回格式异常", retryable=True) from exc

        tool_calls: list[ToolCall] = []
        for index, item in enumerate(choice.get("tool_calls") or []):
            function = item.get("function") or {}
            raw_args = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=item.get("id") or f"call_{uuid.uuid4().hex[:10]}",
                    name=str(function.get("name") or ""),
                    arguments=arguments,
                )
            )
        usage = data.get("usage") or {}
        normalized_usage = {
            "inputTokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "outputTokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            "totalTokens": int(usage.get("total_tokens") or 0),
        }
        return LLMResult(
            content=(choice.get("content") or "").strip(),
            tool_calls=tool_calls,
            usage=normalized_usage,
            provider=self.label,
        )


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 2, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self.open_until

    def success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.open_until = time.monotonic() + self.cooldown_seconds

    @property
    def state(self) -> str:
        if self.open_until and time.monotonic() < self.open_until:
            return "open"
        return "half-open" if self.failures else "closed"


class ProviderRouter:
    def __init__(self, settings: Settings, providers: list[Provider]):
        self.settings = settings
        self.providers = providers
        self.breakers = {provider.name: CircuitBreaker() for provider in providers}
        self._mock = MockProvider()

    @property
    def labels(self) -> list[str]:
        return [provider.label for provider in self.providers] + ["本地降级"]

    @property
    def primary_label(self) -> str:
        return self.providers[0].label if self.providers else "本地降级"

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        context: TurnContext,
    ) -> LLMResult:
        errors: list[str] = []
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if not breaker.allow():
                errors.append(f"{provider.label}: 熔断中")
                continue
            for attempt in range(2 if not provider.is_mock else 1):
                try:
                    result = await asyncio.wait_for(
                        provider.complete(system_prompt, messages, tools, context),
                        timeout=self.settings.request_timeout + 2,
                    )
                    breaker.success()
                    result.provider = provider.label
                    if errors:
                        result.note = "；".join(errors[-2:]) + f"，已切换到 {provider.label}"
                        result.degraded = True
                    return result
                except asyncio.CancelledError:
                    raise
                except ProviderError as exc:
                    errors.append(f"{provider.label}: {str(exc)}")
                    breaker.failure()
                    if not exc.retryable or attempt == 1:
                        break
                    await asyncio.sleep(0.25 * (attempt + 1))
                except asyncio.TimeoutError:
                    errors.append(f"{provider.label}: 超时")
                    breaker.failure()
                    if attempt == 1:
                        break
                except Exception as exc:  # pragma: no cover - 防御性兜底
                    logger.exception("provider %s failed", provider.name)
                    errors.append(f"{provider.label}: {type(exc).__name__}")
                    breaker.failure()
                    break

        # 最后一层：确定性本地引擎。宁可降级，也不让用户看到 500。
        result = await self._mock.complete(system_prompt, messages, [], context)
        result.provider = "本地降级"
        result.degraded = True
        result.note = "模型服务暂不可用，已降级到本地规则引擎" + (f"（{errors[-1]}）" if errors else "")
        return result

    def health(self) -> dict[str, Any]:
        return {
            "primary": self.primary_label,
            "providers": [
                {
                    "name": provider.name,
                    "label": provider.label,
                    "model": provider.model,
                    "circuit": self.breakers[provider.name].state,
                }
                for provider in self.providers
            ],
            "degradedFallback": "本地规则引擎",
        }


def build_router(settings: Settings) -> ProviderRouter:
    names: list[str] = []
    for name in (settings.provider, *settings.fallbacks, "mock"):
        normalized = (name or "").strip().lower()
        if normalized and normalized not in names:
            names.append(normalized)

    providers: list[Provider] = []
    for name in names:
        config = resolve_provider_config(name, settings)
        if config is None:
            logger.warning("provider %s 未配置完整，已跳过（缺少 base_url / model / api_key）", name)
            continue
        if name == "mock":
            providers.append(MockProvider())
        else:
            providers.append(OpenAICompatibleProvider(config))
    if not providers:
        providers = [MockProvider()]
    logger.info("LLM providers: %s", ", ".join(f"{p.name}:{p.model}" for p in providers))
    return ProviderRouter(settings, providers)
