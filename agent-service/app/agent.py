from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator, Awaitable, Callable

from .cache import SemanticCache
from .config import Settings
from .guardrails import (
    GuardDecision,
    grounding_report,
    guard_log_text,
    inspect_input,
    is_personal_query,
    sanitize_output,
)
from .intent import detect_intent, intent_label, needs_order, retrieval_query
from .knowledge import KnowledgeBase
from .memory import MemoryManager
from .models import AgentRequest, ToolCall, ToolOutcome, TurnContext
from .providers import ProviderRouter
from .store import ChatMessage, SessionAccessError, SessionState, SessionStore
from .text_utils import (
    approximate_tokens,
    extract_order_id,
    mask_pii,
    truncate,
)
from .tools import TOOL_LABELS, TOOL_SCHEMAS, ToolRegistry

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        settings: Settings,
        router: ProviderRouter,
        store: SessionStore,
        knowledge: KnowledgeBase,
        tools: ToolRegistry,
        cache: SemanticCache,
    ):
        self.settings = settings
        self.router = router
        self.store = store
        self.knowledge = knowledge
        self.tools = tools
        self.cache = cache
        self.memory = MemoryManager(settings)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._running: dict[str, asyncio.Task[Any]] = {}
        self._cancel_intents: dict[str, float] = {}
        self.turns = 0
        self.tool_calls = 0
        self.degraded_turns = 0
        self.cancelled = 0

    @staticmethod
    def _run_key(session_id: str, client_message_id: str) -> str:
        return f"{session_id}:{client_message_id}"

    async def cancel(self, session_id: str, client_message_id: str) -> bool:
        key = self._run_key(session_id, client_message_id)
        now = time.monotonic()
        for stale_key, created_at in list(self._cancel_intents.items()):
            if now - created_at > 60:
                self._cancel_intents.pop(stale_key, None)
        task = self._running.get(key)
        if task and not task.done():
            task.cancel()
            self.cancelled += 1
            self._cancel_intents.pop(key, None)
            logger.info("cancelled run session=%s client_message=%s", session_id, client_message_id)
            return True
        # 取消请求可能比 stream 的注册更早到达，留一个短期墓碑供新任务消费。
        self._cancel_intents[key] = now
        logger.info("recorded pending cancel session=%s client_message=%s", session_id, client_message_id)
        return False

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "providers": self.router.health(),
            "knowledge": self.knowledge.stats(),
            "cache": self.cache.stats(),
            "sessions": len(list(self.settings.sessions_dir.glob("*.json"))),
            "metrics": {
                "turns": self.turns,
                "toolCalls": self.tool_calls,
                "degradedTurns": self.degraded_turns,
                "cancelled": self.cancelled,
            },
        }

    async def stream(
        self,
        request: AgentRequest,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        started = time.monotonic()
        run_id = uuid.uuid4().hex
        run_key = self._run_key(request.sessionId, request.clientMessageId)
        task = asyncio.current_task()
        if task:
            self._running[run_key] = task

        lock = self._locks[request.sessionId]
        acquired = False
        try:
            if self._cancel_intents.pop(run_key, None) is not None:
                self.cancelled += 1
                logger.info("applied pending cancel session=%s", request.sessionId)
                if task:
                    task.cancel()
                raise asyncio.CancelledError()
            try:
                session = self.store.get_or_create(request.sessionId, request.userId)
            except SessionAccessError:
                yield self._error("FORBIDDEN", "这个会话不属于当前用户，请新建对话。", False)
                return
            except ValueError as exc:
                yield self._error("BAD_SESSION", str(exc), False)
                return

            try:
                await asyncio.wait_for(lock.acquire(), timeout=0.4)
                acquired = True
            except asyncio.TimeoutError:
                yield self._error("SESSION_BUSY", "上一条消息还在生成，请稍等一下。", True)
                return

            if len(request.message) > self.settings.max_message_chars:
                guard = GuardDecision(
                    False,
                    "message_too_long",
                    f"消息不能超过 {self.settings.max_message_chars} 字，请精简后再试。",
                    "low",
                )
            else:
                guard = inspect_input(request.message)
            if guard.allowed:
                self.memory.observe_user(session, request.message)
            intent = detect_intent(request.message)
            bundle = self.memory.build(session, request.message, intent)
            rewritten = self.memory.rewrite_query(session, request.message, intent)
            order_id = extract_order_id(request.message)
            if not order_id and needs_order(intent):
                order_id = session.last_order_id

            user_message = self.store.append_message(session, "user", request.message)
            self.turns += 1
            logger.info(
                "turn session=%s intent=%s input=%s",
                session.id,
                intent,
                guard_log_text(request.message),
            )

            yield {
                "type": "meta",
                "runId": run_id,
                "sessionId": session.id,
                "userMessage": user_message.to_dict(),
                "provider": self.router.primary_label,
                "intent": intent,
                "intentLabel": intent_label(intent),
                "guardrail": not guard.allowed,
            }
            yield {"type": "stage", "stage": "understanding", "label": f"正在理解问题 · {intent_label(intent)}"}
            yield self.memory.memory_event(session, {**bundle.memory_snapshot, "totalMessages": len(session.messages)})

            # 1) 输入安全护栏：命中注入/越权/辱骂时不调用模型。
            if not guard.allowed:
                answer = sanitize_output(guard.reply)
                yield {
                    "type": "guardrail",
                    "category": guard.category,
                    "severity": guard.severity,
                    "label": "输入安全护栏",
                }
                async for event in self._finish(
                    session=session,
                    answer=answer,
                    citations=[],
                    provider="安全护栏",
                    usage={"inputTokens": 0, "outputTokens": approximate_tokens(answer), "totalTokens": approximate_tokens(answer)},
                    grounding={
                        "status": "blocked",
                        "label": "安全拦截",
                        "detail": "请求命中安全规则，未调用模型。",
                        "invalidCitations": [],
                    },
                    intent=intent,
                    trace=[],
                    started=started,
                    cache_hit=False,
                    degraded=False,
                    provider_note="",
                    is_disconnected=is_disconnected,
                ):
                    yield event
                return

            # 2) 语义缓存：只缓存与个人订单无关的政策类问题。
            cacheable = (
                self.settings.enable_semantic_cache
                and intent == "policy"
                and not is_personal_query(request.message, order_id)
            )
            if cacheable:
                cached = self.cache.get(request.message, intent)
                if cached:
                    logger.info("semantic cache hit session=%s", session.id)
                    yield {
                        "type": "cache",
                        "hit": True,
                        "similarity": "≥0.76",
                        "ttlSeconds": self.settings.cache_ttl_seconds,
                        "savedModelCall": True,
                    }
                    yield {"type": "citations", "citations": self._public_citations(cached.citations)}
                    async for event in self._finish(
                        session=session,
                        answer=cached.answer,
                        citations=cached.citations,
                        provider=cached.provider + " · 语义缓存",
                        usage={
                            "inputTokens": 0,
                            "outputTokens": approximate_tokens(cached.answer),
                            "totalTokens": approximate_tokens(cached.answer),
                            "cached": True,
                        },
                        grounding=grounding_report(cached.answer, cached.citations, 0),
                        intent=intent,
                        trace=[
                            {
                                "name": "semantic_cache",
                                "label": "语义缓存命中",
                                "status": "success",
                                "durationMs": 1,
                                "summary": "相似政策问题已缓存，直接返回并保留引用",
                            }
                        ],
                        started=started,
                        cache_hit=True,
                        degraded=False,
                        provider_note="",
                        is_disconnected=is_disconnected,
                    ):
                        yield event
                    return

            yield {"type": "stage", "stage": "reasoning", "label": "正在检索规则并规划工具"}

            context = TurnContext(
                message=request.message,
                rewritten_query=rewritten,
                intent=intent,
                order_id=order_id,
                profile=dict(session.profile),
            )
            messages = list(bundle.messages)
            trace: list[dict[str, Any]] = []
            executed: set[str] = set()
            answer = ""
            last_result_provider = self.router.primary_label
            provider_note = ""
            degraded = False
            citations_sent = 0

            # 3) Agent 工具循环。真实模型和 Mock 走同一套协议。
            for step in range(self.settings.max_tool_rounds + 1):
                if is_disconnected and await is_disconnected():
                    logger.info("client disconnected before model call session=%s", session.id)
                    return
                try:
                    result = await self.router.complete(bundle.system_prompt, messages, TOOL_SCHEMAS, context)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # 理论上 router 已兜底，这里防止协议层异常
                    logger.exception("agent completion failed")
                    yield self._error("AGENT_FAILED", f"生成回答时出了点问题：{type(exc).__name__}", True)
                    return

                last_result_provider = result.provider
                degraded = degraded or result.degraded
                provider_note = result.note or provider_note
                self._merge_usage(context.usage, result.usage)

                if not result.tool_calls:
                    answer = result.content
                    break
                if step >= self.settings.max_tool_rounds:
                    answer = ""
                    break

                assistant_tool_calls = []
                for call in result.tool_calls:
                    assistant_tool_calls.append(
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                    )
                messages.append({"role": "assistant", "content": result.content or "", "tool_calls": assistant_tool_calls})

                for call in result.tool_calls:
                    args = self._prepare_args(call, context, session)
                    signature = call.name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)
                    if signature in executed:
                        tool_message = {
                            "ok": True,
                            "summary": "重复调用已跳过，本轮已经执行过同样的工具。",
                            "data": {},
                        }
                    else:
                        executed.add(signature)
                        yield {
                            "type": "tool_start",
                            "callId": call.id,
                            "name": call.name,
                            "label": TOOL_LABELS.get(call.name, call.name),
                            "arguments": truncate(mask_pii(json.dumps(args, ensure_ascii=False)), 220),
                        }
                        outcome = await self.tools.execute(call.name, args, request.userId)
                        self.tool_calls += 1
                        if call.name == "lookup_order" and outcome.ok:
                            self.memory.observe_order(session, outcome.data)
                            context.order_id = outcome.data.get("order_id") or context.order_id
                        if outcome.citations:
                            self._add_citations(context, outcome.citations)
                        context.tool_outcomes.append(outcome)
                        context.tool_round = step + 1
                        trace.append(
                            {
                                "id": call.id,
                                "name": call.name,
                                "label": TOOL_LABELS.get(call.name, call.name),
                                "status": "success" if outcome.ok else "error",
                                "durationMs": outcome.duration_ms,
                                "summary": sanitize_output(outcome.summary),
                            }
                        )
                        yield {
                            "type": "tool_result",
                            "callId": call.id,
                            "name": call.name,
                            "label": TOOL_LABELS.get(call.name, call.name),
                            "ok": outcome.ok,
                            "durationMs": outcome.duration_ms,
                            "summary": sanitize_output(outcome.summary),
                            "citationCount": len(outcome.citations),
                        }
                        tool_message = {
                            "ok": outcome.ok,
                            "summary": outcome.summary,
                            "data": outcome.data,
                        }
                        if outcome.citations:
                            tool_message["citation_indexes"] = list(
                                range(len(context.citations) - len(outcome.citations) + 1, len(context.citations) + 1)
                            )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "name": call.name,
                                "content": truncate(json.dumps(tool_message, ensure_ascii=False, default=str), 3800),
                            }
                        )
                        continue

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(tool_message, ensure_ascii=False),
                        }
                    )

                if len(context.citations) > citations_sent:
                    citations_sent = len(context.citations)
                    yield {"type": "citations", "citations": self._public_citations(context.citations)}
                yield {"type": "stage", "stage": "composing", "label": "正在核对依据并生成答复"}

            if not answer:
                answer = self._fallback_answer(context)
            answer = sanitize_output(truncate(answer, 4000))
            if not answer:
                answer = "我暂时没能生成可靠答复。可以回复「转人工」，我帮你接入人工客服。"

            if context.degraded:
                self.degraded_turns += 1
            if len(context.citations) > citations_sent:
                yield {"type": "citations", "citations": self._public_citations(context.citations)}
            if cacheable and context.citations and not context.degraded:
                self.cache.put(request.message, intent, answer, context.citations, last_result_provider)

            grounding = grounding_report(answer, context.citations, len(context.tool_outcomes))
            if grounding["status"] == "flagged":
                answer += "\n\n> 部分依据未能自动核对，已标记给人工复核。"

            usage = self._final_usage(context, answer, bundle.token_estimate)
            async for event in self._finish(
                session=session,
                answer=answer,
                citations=context.citations,
                provider=last_result_provider,
                usage=usage,
                grounding=grounding,
                intent=intent,
                trace=trace,
                started=started,
                cache_hit=False,
                degraded=degraded,
                provider_note=provider_note,
                is_disconnected=is_disconnected,
            ):
                yield event

        except asyncio.CancelledError:
            logger.info("run cancelled session=%s", request.sessionId)
            raise
        except Exception:
            logger.exception("unhandled agent error session=%s", request.sessionId)
            yield self._error("INTERNAL", "服务暂时不可用，请稍后重试。", True)
        finally:
            self._running.pop(run_key, None)
            if acquired:
                lock.release()

    async def _finish(
        self,
        *,
        session: SessionState,
        answer: str,
        citations: list[dict[str, Any]],
        provider: str,
        usage: dict[str, Any],
        grounding: dict[str, Any],
        intent: str,
        trace: list[dict[str, Any]],
        started: float,
        cache_hit: bool,
        degraded: bool,
        provider_note: str,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        if is_disconnected and await is_disconnected():
            return

        for chunk in self._chunks(answer, 9):
            yield {"type": "token", "text": chunk}
            if self.settings.stream_delay_seconds:
                await asyncio.sleep(self.settings.stream_delay_seconds)
            if is_disconnected and await is_disconnected():
                return

        elapsed_ms = int((time.monotonic() - started) * 1000)
        metadata = {
            "provider": provider,
            "citations": self._public_citations(citations),
            "usage": usage,
            "grounding": grounding,
            "intent": intent,
            "intentLabel": intent_label(intent),
            "trace": trace,
            "cacheHit": cache_hit,
            "degraded": degraded,
            "durationMs": elapsed_ms,
        }
        assistant = self.store.append_message(session, "assistant", answer, metadata=metadata)
        yield {"type": "usage", "usage": usage, "elapsedMs": elapsed_ms, "provider": provider}
        if provider_note:
            yield {"type": "notice", "level": "warning", "message": provider_note}
        yield {"type": "grounding", "grounding": grounding}
        yield {
            "type": "done",
            "message": assistant.to_dict(),
            "content": answer,
            "citations": self._public_citations(citations),
            "usage": usage,
            "provider": provider,
            "degraded": degraded,
            "cacheHit": cache_hit,
            "durationMs": elapsed_ms,
            "intent": intent,
            "intentLabel": intent_label(intent),
            "grounding": grounding,
            "trace": trace,
            "sessionTitle": session.title,
        }

    def _prepare_args(self, call: ToolCall, context: TurnContext, session: SessionState) -> dict[str, Any]:
        args = dict(call.arguments or {})
        if call.name in {"lookup_order", "check_refund_eligibility"}:
            args.setdefault("order_id", context.order_id or session.last_order_id or "")
            args["order_id"] = str(args.get("order_id") or "").strip().upper()
        if call.name == "check_refund_eligibility":
            args.setdefault("reason", context.message)
        if call.name == "search_knowledge_base" and not args.get("query"):
            args["query"] = retrieval_query(context.intent, context.message)
        if call.name == "create_ticket":
            args.setdefault("order_id", context.order_id or session.last_order_id)
            args.setdefault("issue", context.message)
            args.setdefault("urgency", "normal")
        if call.name == "handoff_to_human":
            args.setdefault("reason", context.message)
            args.setdefault("urgency", "normal")
        return args

    @staticmethod
    def _merge_usage(total: dict[str, Any], usage: dict[str, Any]) -> None:
        for key in ("inputTokens", "outputTokens", "totalTokens"):
            total[key] = int(total.get(key, 0)) + int(usage.get(key, 0) or 0)

    def _final_usage(self, context: TurnContext, answer: str, context_tokens: int) -> dict[str, Any]:
        output = approximate_tokens(answer)
        if context.usage.get("totalTokens"):
            return {
                **context.usage,
                "outputTokens": context.usage.get("outputTokens") or output,
                "estimated": False,
            }
        return {
            "inputTokens": context_tokens,
            "outputTokens": output,
            "totalTokens": context_tokens + output,
            "estimated": True,
        }

    @staticmethod
    def _add_citations(context: TurnContext, incoming: list[dict[str, Any]]) -> None:
        existing = {item["id"] for item in context.citations}
        for item in incoming:
            if item["id"] in existing:
                continue
            context.citations.append(item)
            existing.add(item["id"])

    @staticmethod
    def _public_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "index": index,
                "id": item.get("id"),
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "score": item.get("score"),
            }
            for index, item in enumerate(citations, start=1)
        ]

    @staticmethod
    def _chunks(text: str, size: int = 9) -> list[str]:
        return [text[index : index + size] for index in range(0, len(text), size)]

    @staticmethod
    def _error(code: str, message: str, retryable: bool) -> dict[str, Any]:
        return {"type": "error", "code": code, "message": message, "retryable": retryable}

    @staticmethod
    def _fallback_answer(context: TurnContext) -> str:
        if not context.tool_outcomes:
            return "我还没有拿到足够的信息。请补充订单号或具体问题，我再帮你查。"
        summaries = "\n".join(f"- {truncate(item.summary, 120)}" for item in context.tool_outcomes[-3:])
        return (
            "我已经查到以下信息，但本轮生成答复时工具调用轮数达到了上限：\n"
            f"{summaries}\n\n"
            "为避免给你错误结论，建议回复「转人工」让售后专员继续处理。"
        )
