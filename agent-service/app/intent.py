from __future__ import annotations

from .text_utils import extract_order_id, normalize_text

INTENT_LABELS = {
    "greeting": "问候",
    "order_status": "订单/物流查询",
    "refund": "退换货",
    "address_change": "修改地址",
    "warranty": "保修/维修",
    "human": "转人工",
    "policy": "政策咨询",
    "other": "一般咨询",
}


def detect_intent(text: str) -> str:
    normalized = normalize_text(text)
    order_id = extract_order_id(text)
    if len(normalized) <= 16 and any(word in normalized for word in ("你好", "您好", "在吗", "hello", "hi", "嗨")):
        return "greeting"
    if (
        len(normalized) <= 28
        and any(word in normalized for word in ("我叫", "叫我"))
        and not any(word in normalized for word in ("退", "订单", "物流", "快递", "坏", "发票", "投诉"))
    ):
        return "greeting"
    if any(word in normalized for word in ("你能做什么", "你会什么", "能帮我做什么", "介绍一下你", "怎么用")):
        return "greeting"
    if any(word in normalized for word in ("转人工", "人工客服", "找人工", "真人", "投诉")):
        return "human"
    if any(word in normalized for word in ("改地址", "修改地址", "地址填错", "换地址", "改收货", "拦截")):
        return "address_change"

    # 不带订单号的规则型问题直接走知识库，避免每个“退款多久到账”都先查一单。
    policy_markers = (
        "运费谁",
        "邮费谁",
        "多久到账",
        "几天到账",
        "退款进度",
        "退款流程",
        "怎么退",
        "如何退",
        "退货规则",
        "退换规则",
        "政策",
        "时效",
        "包邮",
        "发票",
        "保修期",
        "保修多久",
        "保修几年",
        "质保多久",
        "质保几年",
    )
    if not order_id and any(word in normalized for word in policy_markers):
        return "policy"

    if any(word in normalized for word in ("退款", "退货", "退换", "无理由", "退掉", "不想要了")):
        return "refund"
    quality = any(word in normalized for word in ("漏水", "不保温", "坏了", "故障", "破损", "质量"))
    if quality and not any(word in normalized for word in ("退", "换")):
        return "warranty"
    if any(word in normalized for word in ("保修", "质保", "维修", "维修点")):
        return "warranty"
    if any(word in normalized for word in ("订单", "物流", "快递", "到哪", "发货", "签收", "运单", "包裹")):
        return "order_status"
    if any(
        word in normalized
        for word in ("会员", "隐私", "验证码", "多久", "几天", "规则", "流程")
    ):
        return "policy"
    if order_id:
        return "order_status"
    return "other"


def needs_order(intent: str) -> bool:
    return intent in {"order_status", "refund", "address_change", "warranty"}


def retrieval_query(intent: str, message: str) -> str:
    if intent == "refund":
        return "退货 退款 七天无理由 " + message
    if intent == "address_change":
        return "修改地址 发货 拦截 " + message
    if intent == "warranty":
        return "保修 质保 维修 " + message
    if intent == "policy":
        return message + " 规则 政策"
    if intent == "order_status":
        return "物流 配送 时效 " + message
    return message


def intent_label(intent: str) -> str:
    return INTENT_LABELS.get(intent, "一般咨询")
