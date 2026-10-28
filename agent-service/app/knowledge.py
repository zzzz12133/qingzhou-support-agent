from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .text_utils import normalize_text, truncate

# 中文没有空格，演示项目不引入 jieba，用「单字 + 二元组」做轻量检索。
PUNCT_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")
SYNONYMS = {
    "退货": ["退货", "退款", "无理由", "七天"],
    "退款": ["退款", "退货", "到账", "原路"],
    "换货": ["换货", "质量问题", "退换"],
    "运费": ["运费", "包邮", "邮费", "寄回"],
    "发货": ["发货", "出库", "时效", "下单"],
    "物流": ["物流", "快递", "运单", "配送"],
    "改地址": ["修改地址", "改地址", "收货地址", "拦截"],
    "保修": ["保修", "质保", "维修", "售后"],
    "漏水": ["漏水", "密封", "质量", "保温"],
    "发票": ["发票", "抬头", "税号"],
    "人工": ["人工", "转人工", "排队", "在线时间"],
    "隐私": ["隐私", "验证码", "密码", "安全"],
}
STOP_TERMS = {"怎么", "什么", "可以", "一下", "这个", "那个", "我的", "请问", "现在", "多久", "如何", "是否", "吗", "呢"}


def tokenize(text: str) -> list[str]:
    text = normalize_text(text)
    tokens: list[str] = []
    for part in PUNCT_RE.split(text):
        if not part:
            continue
        if re.fullmatch(r"[a-z0-9]+", part):
            tokens.append(part)
            continue
        chars = list(part)
        tokens.extend(chars)
        tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return [token for token in tokens if token not in STOP_TERMS]


def expand_query(query: str) -> str:
    normalized = normalize_text(query)
    additions: list[str] = []
    for key, words in SYNONYMS.items():
        if key in normalized:
            additions.extend(word for word in words if word not in normalized)
    return normalized + " " + " ".join(dict.fromkeys(additions))


@dataclass
class KnowledgeChunk:
    id: str
    section: str
    title: str
    content: str
    tokens: list[str]
    title_tokens: list[str]


class KnowledgeBase:
    def __init__(self, directory: Path):
        self.directory = directory
        self.chunks: list[KnowledgeChunk] = []
        self.version = "KB-empty"
        self._load()

    def _load(self) -> None:
        digest = hashlib.sha1()
        files = sorted(self.directory.glob("*.md"))
        for path in files:
            raw = path.read_text(encoding="utf-8")
            digest.update(path.name.encode("utf-8"))
            digest.update(raw.encode("utf-8"))
            category = self._category_name(raw, path.stem)
            for index, (heading, body) in enumerate(self._split_sections(raw), start=1):
                if not body.strip():
                    continue
                title = f"{category} · {heading}" if heading else category
                content = body.strip()
                self.chunks.append(
                    KnowledgeChunk(
                        id=f"{path.stem}-{index}",
                        section=category,
                        title=title,
                        content=content,
                        tokens=tokenize(title + " " + content),
                        title_tokens=tokenize(title),
                    )
                )
        self.version = "KB-" + digest.hexdigest()[:6] if files else "KB-empty"

    @staticmethod
    def _category_name(raw: str, fallback: str) -> str:
        match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        return match.group(1).strip() if match else fallback

    @staticmethod
    def _split_sections(raw: str) -> list[tuple[str, str]]:
        matches = list(re.finditer(r"^##\s+(.+)$", raw, re.MULTILINE))
        sections: list[tuple[str, str]] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            sections.append((match.group(1).strip(), raw[start:end].strip()))
        return sections

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        expanded = expand_query(query)
        q_tokens = tokenize(expanded)
        if not q_tokens or not self.chunks:
            return []

        n = len(self.chunks)
        doc_freq: dict[str, int] = {}
        for chunk in self.chunks:
            for token in set(chunk.tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        avg_len = sum(len(chunk.tokens) for chunk in self.chunks) / n
        k1, b = 1.4, 0.72
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            frequencies: dict[str, int] = {}
            for token in chunk.tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            score = 0.0
            for token in set(q_tokens):
                tf = frequencies.get(token, 0)
                if not tf:
                    continue
                df = doc_freq.get(token, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * len(chunk.tokens) / max(avg_len, 1))
                score += idf * (tf * (k1 + 1)) / denom
                if token in chunk.title_tokens:
                    score += idf * 0.9
            # 精确包含的关键词再给一点权重，避免只靠单字命中。
            for keyword in re.findall(r"[\u4e00-\u9fff]{2,6}", expanded):
                if keyword in chunk.content or keyword in chunk.title:
                    score += 0.35
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, chunk in scored[:top_k]:
            results.append(
                {
                    "id": chunk.id,
                    "title": chunk.title,
                    "section": chunk.section,
                    "snippet": truncate(chunk.content, 150),
                    "content": chunk.content,
                    "score": round(score, 3),
                }
            )
        return results

    def stats(self) -> dict[str, Any]:
        return {
            "chunks": len(self.chunks),
            "documents": len(list(self.directory.glob("*.md"))),
            "version": self.version,
        }
