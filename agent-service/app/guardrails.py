from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .text_utils import compact_text, mask_pii

INJECTION_PATTERNS = [
    re.compile(r"(忽略|无视|跳过|忘记).{0,10}(指令|规则|提示词|设定|限制)"),
    re.compile(r"(系统|system).{0,6}(prompt|提示词|消息)"),
    re.compile(r"(开发者|developer|debug|调试).{0,6}(模式|mode)"),
    re.compile(r"(你现在|从现在起|假装).{0,12}(是|扮演|作为).{0,12}(管理员|开发者|root|无限制)"),
    re.compile(r"(输出|打印|泄露|reveal|print|repeat).{0,16}(提示词|系统消息|密钥|api[_ -]?key|prompt|instructions?)", re.I),
    re.compile(r"(ignore|disregard).{0,24}(instructions?|prompt|rules?)", re.I),
]

PRIVACY_PATTERNS = [
    re.compile(r"(给我|查一下|告诉我|发我).{0,10}(别人|其他客户|上一个用户).{0,10}(手机号|电话|地址|订单)"),
    re.compile(r"(导出|下载).{0,8}(全部|所有).{0,8}(客户|用户).{0,6}(数据|信息)"),
    re.compile(r"(绕过|关闭|跳过).{0,8}(实名|验证|权限|登录)"),
]

ABUSE_RE = re.compile(r"(傻逼|操你|去死|弄死你|狗日的|fuck\s*you)", re.I)
API_KEY_RE = re.compile(r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,})")
PHONE_FULL_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
ID_FULL_RE = re.compile(r"(?<!\d)(\d{4})\d{10}(\d{3}[\dXx])(?!\d)")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
CITATION_RE = re.compile(r"\[(\d{1,2})\]")
POLICY_NUMBER_RE = re.compile(r"(\d{1,3})\s*(天|个工作日|元)")


@dataclass
class GuardDecision:
    allowed: bool
    category: str = ""
    reply: str = ""
    severity: str = "info"


def inspect_input(text: str) -> GuardDecision:
    normalized = text.strip()
    if not normalized:
        return GuardDecision(False, "empty", "消息不能为空，请告诉我你遇到的问题。")

    for pattern in INJECTION_PATTERNS:
        if pattern.search(normalized):
            return GuardDecision(
                False,
                "prompt_injection",
                "这个请求我不会执行。我的职责是处理订单、物流和售后问题，"
                "也不会透露内部规则。你可以继续告诉我订单号或遇到的具体问题。",
                "high",
            )

    for pattern in PRIVACY_PATTERNS:
        if pattern.search(normalized):
            return GuardDecision(
                False,
                "privacy",
                "抱歉，我不能提供或导出其他用户的个人信息。请只查询本人订单；"
                "核对身份只需要订单号或收件手机号后四位。",
                "high",
            )

    if ABUSE_RE.search(normalized):
        return GuardDecision(
            False,
            "abuse",
            "我理解你可能有些着急，但请使用文明用语。告诉我订单号和具体问题，我会优先帮你处理。",
            "medium",
        )

    return GuardDecision(True)


def sanitize_output(text: str) -> str:
    text = API_KEY_RE.sub("sk-***已隐藏***", text)
    text = PHONE_FULL_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", text)
    text = ID_FULL_RE.sub(lambda m: f"{m.group(1)}**********{m.group(2)}", text)
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
    return text.strip()


def contains_prompt_leak(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in ("系统提示词是", "system prompt:", "我的系统指令", "以下是开发者指令", "you are a helpful assistant")
    )


def guard_log_text(text: str) -> str:
    """日志只留脱敏后的截断内容，避免把完整手机号写进磁盘。"""
    return mask_pii(text)[:300]


def grounding_report(answer: str, citations: list[dict[str, Any]], tool_count: int) -> dict[str, Any]:
    if not citations:
        if tool_count:
            return {
                "status": "tool_grounded",
                "label": "工具事实已校验",
                "detail": "回答基于订单/售后工具返回的结构化数据。",
                "invalidCitations": [],
            }
        return {
            "status": "unverified",
            "label": "未使用外部依据",
            "detail": "本轮没有调用工具或知识库，回答仅作一般说明。",
            "invalidCitations": [],
        }

    used = sorted({int(value) for value in CITATION_RE.findall(answer)})
    valid = set(range(1, len(citations) + 1))
    invalid = [value for value in used if value not in valid]
    if invalid:
        return {
            "status": "flagged",
            "label": "引用待复核",
            "detail": "回答里出现了知识库中不存在的引用编号，已提示人工复核。",
            "invalidCitations": invalid,
        }
    if not used:
        return {
            "status": "partially_grounded",
            "label": "依据未标注",
            "detail": "检索到了知识库内容，但回答没有标注引用编号。",
            "invalidCitations": [],
        }
    return {
        "status": "grounded",
        "label": "知识库已引用",
        "detail": f"已核对 {len(used)} 条知识库依据。",
        "invalidCitations": [],
    }


def has_policy_claim(text: str) -> bool:
    return bool(POLICY_NUMBER_RE.search(text))


def is_personal_query(text: str, order_id: str | None) -> bool:
    if order_id:
        return True
    compact = compact_text(text)
    return any(
        marker in compact
        for marker in ("我的订单", "我的快递", "我买", "退款进度", "改地址", "手机号", "签收")
    )
