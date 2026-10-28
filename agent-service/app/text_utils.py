from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

ORDER_RE = re.compile(r"\b([A-Za-z]\d{4,10})\b")
PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)(\d{4})\d{10}(\d{3}[\dXx])(?!\d)")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def compact_text(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’()（）\[\]【】]+", "", normalize_text(text))


def approximate_tokens(text: str) -> int:
    """中文按 1.45 字/token，英文按 4 字符/token 粗估，足够做预算控制。"""
    if not text:
        return 0
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - chinese)
    return max(1, int(chinese / 1.45 + other / 4))


def mask_pii(text: str) -> str:
    text = PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", text)
    text = ID_CARD_RE.sub(lambda m: f"{m.group(1)}**********{m.group(2)}", text)
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
    return text


def extract_order_id(text: str) -> str | None:
    match = ORDER_RE.search(text or "")
    return match.group(1).upper() if match else None


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?\n])", text)
    return [part for part in parts if part.strip()]


def humanize_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%m月%d日")
    except (ValueError, TypeError):
        return value


def days_since(value: str) -> int:
    try:
        return max(0, (date.today() - date.fromisoformat(value)).days)
    except (ValueError, TypeError):
        return 9999


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
