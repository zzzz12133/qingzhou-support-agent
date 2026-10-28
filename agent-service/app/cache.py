from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .text_utils import compact_text


def semantic_tokens(text: str) -> set[str]:
    compact = compact_text(text)
    if len(compact) <= 2:
        return {compact} if compact else set()
    # 中文二元组 + 原串，轻量近似语义匹配，不引入向量库。
    return {compact[index : index + 2] for index in range(len(compact) - 1)} | {compact}


TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("refund_fee", ("退货运费", "退回运费", "寄回运费", "邮费谁", "运费谁", "运费承担", "运费怎么算")),
    ("refund_timing", ("退款多久", "多久到账", "几天到账", "到账时间", "退款进度", "退款什么时候")),
    ("shipping_time", ("发货时效", "多久发货", "几天发货", "什么时候发货", "发货时间", "48小时")),
    ("delivery_time", ("配送时效", "多久送达", "几天送达", "物流时效", "什么时候到")),
    ("free_shipping", ("包邮", "满多少", "邮费")),
    ("warranty", ("保修", "质保", "维修", "漏水")),
    ("invoice", ("发票", "抬头", "税号")),
    ("privacy", ("隐私", "验证码", "密码", "安全")),
    ("human", ("人工", "在线时间", "排队")),
    ("return_policy", ("七天无理由", "退货规则", "退换规则", "怎么退", "如何退")),
    ("cancel_order", ("取消订单", "不想等")),
    ("address", ("修改地址", "改地址", "地址填错")),
)


def faq_topic(query: str) -> str:
    compact = compact_text(query)
    for topic, keywords in TOPIC_RULES:
        if any(keyword in compact for keyword in keywords):
            return topic
    return ""


def similarity(left: str, right: str) -> float:
    a, b = semantic_tokens(left), semantic_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class CacheEntry:
    query: str
    intent: str
    topic: str
    answer: str
    citations: list[dict[str, Any]]
    provider: str
    knowledge_version: str
    created_at: float = field(default_factory=time.time)
    hits: int = 0


class SemanticCache:
    def __init__(self, ttl_seconds: int, max_entries: int, knowledge_version: str):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.knowledge_version = knowledge_version
        self.entries: list[CacheEntry] = []
        self.hits = 0
        self.misses = 0

    def _alive(self, entry: CacheEntry) -> bool:
        return (
            time.time() - entry.created_at <= self.ttl_seconds
            and entry.knowledge_version == self.knowledge_version
        )

    def get(self, query: str, intent: str) -> CacheEntry | None:
        self.entries = [entry for entry in self.entries if self._alive(entry)]
        topic = faq_topic(query)
        best: CacheEntry | None = None
        best_score = 0.0
        for entry in self.entries:
            if entry.intent != intent:
                continue
            if topic and entry.topic == topic:
                score = 1.0
            else:
                score = similarity(query, entry.query)
            if score > best_score:
                best, best_score = entry, score
        if best and best_score >= 0.76:
            best.hits += 1
            self.hits += 1
            return best
        self.misses += 1
        return None

    def put(
        self,
        query: str,
        intent: str,
        answer: str,
        citations: list[dict[str, Any]],
        provider: str,
    ) -> None:
        if not answer.strip():
            return
        topic = faq_topic(query)
        self.entries = [entry for entry in self.entries if self._alive(entry)]
        self.entries = [
            entry
            for entry in self.entries
            if not (topic and entry.topic == topic) and similarity(entry.query, query) < 0.95
        ]
        self.entries.append(
            CacheEntry(
                query=query,
                intent=intent,
                topic=topic,
                answer=answer,
                citations=citations,
                provider=provider,
                knowledge_version=self.knowledge_version,
            )
        )
        if len(self.entries) > self.max_entries:
            self.entries.sort(key=lambda item: (item.hits, item.created_at), reverse=True)
            self.entries = self.entries[: self.max_entries]

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self.entries),
            "hits": self.hits,
            "misses": self.misses,
            "hitRate": round(self.hits / total, 3) if total else 0.0,
            "ttlSeconds": self.ttl_seconds,
            "knowledgeVersion": self.knowledge_version,
        }
