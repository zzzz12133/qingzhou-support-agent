from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import Settings
from .knowledge import KnowledgeBase
from .models import ToolOutcome
from .text_utils import days_since, extract_order_id, mask_pii, truncate

TOOL_LABELS = {
    "lookup_order": "查询订单",
    "check_refund_eligibility": "校验退款资格",
    "search_knowledge_base": "检索知识库",
    "create_ticket": "创建售后工单",
    "handoff_to_human": "转接人工客服",
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "按订单号查询订单状态、商品、物流和签收信息。回答任何订单相关问题前必须先调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，例如 A1001"},
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_refund_eligibility",
            "description": "根据订单、签收天数和退货原因，判断是否在退货窗口内。不要自行计算退货期限。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号"},
                    "reason": {"type": "string", "description": "用户描述的退货原因"},
                },
                "required": ["order_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "检索平台的售后、配送、保修政策。凡涉及规则、时效、金额，必须引用检索结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "创建售后工单。需要用户明确同意，或问题无法在线即时解决时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，可为空"},
                    "issue": {"type": "string", "description": "问题摘要"},
                    "urgency": {"type": "string", "enum": ["normal", "high"], "description": "紧急程度"},
                },
                "required": ["issue", "urgency"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_to_human",
            "description": "转接人工客服。适用于退款争议、物流丢件、投诉，或用户明确要求人工。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "转人工原因"},
                    "urgency": {"type": "string", "enum": ["normal", "high"], "description": "紧急程度"},
                },
                "required": ["reason", "urgency"],
                "additionalProperties": False,
            },
        },
    },
]


def _fmt_date(value: date) -> str:
    return f"{value.month}月{value.day}日"


def _demo_orders() -> dict[str, dict[str, Any]]:
    today = date.today()
    return {
        "A1001": {
            "order_id": "A1001",
            "status": "运输中",
            "status_code": "shipped",
            "product": "云朵保温杯 480ml · 雾蓝",
            "quantity": 1,
            "amount": 129.0,
            "member_tier": "普通会员",
            "recipient": "张*",
            "phone": "138****6621",
            "city": "杭州",
            "address": "浙江省杭州市西湖区文三路 ** 号",
            "created_at": str(today - timedelta(days=3)),
            "shipped_at": str(today - timedelta(days=2)),
            "estimated_date": str(today + timedelta(days=1)),
            "estimated_text": f"{_fmt_date(today + timedelta(days=1))} 18:00 前",
            "carrier": "顺丰速运",
            "tracking_no": "SF1357 **** 8821",
            "latest_event": "今天 09:42 到达杭州转运中心，准备发往西湖区网点",
            "delivered_at": None,
        },
        "A1002": {
            "order_id": "A1002",
            "status": "已签收",
            "status_code": "delivered",
            "product": "云朵保温杯 600ml · 奶油白",
            "quantity": 1,
            "amount": 159.0,
            "member_tier": "普通会员",
            "recipient": "张*",
            "phone": "138****6621",
            "city": "杭州",
            "address": "浙江省杭州市西湖区文三路 ** 号",
            "created_at": str(today - timedelta(days=7)),
            "shipped_at": str(today - timedelta(days=6)),
            "estimated_date": str(today - timedelta(days=4)),
            "estimated_text": "已签收",
            "carrier": "京东物流",
            "tracking_no": "JDVA **** 3096",
            "latest_event": f"{_fmt_date(today - timedelta(days=4))} 14:18 已由本人签收",
            "delivered_at": str(today - timedelta(days=4)),
        },
        "A1003": {
            "order_id": "A1003",
            "status": "待发货",
            "status_code": "pending",
            "product": "云朵保温杯 480ml · 燕麦色",
            "quantity": 2,
            "amount": 238.0,
            "member_tier": "普通会员",
            "recipient": "张*",
            "phone": "138****6621",
            "city": "杭州",
            "address": "浙江省杭州市西湖区文三路 ** 号",
            "created_at": str(today - timedelta(days=1)),
            "shipped_at": None,
            "estimated_date": str(today + timedelta(days=1)),
            "estimated_text": "预计明天发出",
            "carrier": None,
            "tracking_no": None,
            "latest_event": "仓库已接单，等待拣货出库",
            "delivered_at": None,
        },
        "A1004": {
            "order_id": "A1004",
            "status": "已签收",
            "status_code": "delivered",
            "product": "云朵保温杯 480ml · 雾蓝",
            "quantity": 1,
            "amount": 129.0,
            "member_tier": "普通会员",
            "recipient": "李*",
            "phone": "139****0722",
            "city": "上海",
            "address": "上海市徐汇区漕溪北路 ** 号",
            "created_at": str(today - timedelta(days=45)),
            "shipped_at": str(today - timedelta(days=43)),
            "estimated_date": str(today - timedelta(days=40)),
            "estimated_text": "已签收",
            "carrier": "顺丰速运",
            "tracking_no": "SF1357 **** 1027",
            "latest_event": f"{_fmt_date(today - timedelta(days=40))} 10:05 已签收",
            "delivered_at": str(today - timedelta(days=40)),
        },
        "A1005": {
            "order_id": "A1005",
            "status": "已签收",
            "status_code": "delivered",
            "product": "云朵保温杯 600ml · 雾蓝礼盒",
            "quantity": 1,
            "amount": 189.0,
            "member_tier": "悦享 VIP",
            "recipient": "张*",
            "phone": "138****6621",
            "city": "杭州",
            "address": "浙江省杭州市西湖区文三路 ** 号",
            "created_at": str(today - timedelta(days=16)),
            "shipped_at": str(today - timedelta(days=14)),
            "estimated_date": str(today - timedelta(days=12)),
            "estimated_text": "已签收",
            "carrier": "顺丰速运",
            "tracking_no": "SF1357 **** 6612",
            "latest_event": f"{_fmt_date(today - timedelta(days=12))} 16:31 已签收",
            "delivered_at": str(today - timedelta(days=12)),
        },
    }


class TicketStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def create(self, order_id: str | None, issue: str, urgency: str, user_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                records = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                records = []
            ticket = {
                "id": "T" + date.today().strftime("%m%d") + uuid.uuid4().hex[:4].upper(),
                "orderId": order_id,
                "issue": truncate(mask_pii(issue), 180),
                "urgency": urgency if urgency in {"normal", "high"} else "normal",
                "userId": user_id,
                "status": "open",
                "createdAt": datetime.now().isoformat(timespec="seconds"),
            }
            records.append(ticket)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(records[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return ticket


class ToolRegistry:
    def __init__(self, settings: Settings, knowledge: KnowledgeBase):
        self.settings = settings
        self.knowledge = knowledge
        self.orders = _demo_orders()
        self.tickets = TicketStore(settings.tickets_file)
        self.handlers: dict[str, Callable[[dict[str, Any], str], Awaitable[ToolOutcome]]] = {
            "lookup_order": self._lookup_order,
            "check_refund_eligibility": self._check_refund,
            "search_knowledge_base": self._search_knowledge,
            "create_ticket": self._create_ticket,
            "handoff_to_human": self._handoff,
        }

    async def execute(self, name: str, arguments: dict[str, Any], user_id: str) -> ToolOutcome:
        handler = self.handlers.get(name)
        if not handler:
            return ToolOutcome(name=name, ok=False, summary=f"未知工具：{name}")
        started = datetime.now()
        await asyncio.sleep(self.settings.tool_delay_seconds)
        try:
            outcome = await handler(arguments or {}, user_id)
        except Exception as exc:  # 工具异常不能把整条链路带崩
            outcome = ToolOutcome(name=name, ok=False, summary=f"工具执行失败：{type(exc).__name__}")
        outcome.duration_ms = int((datetime.now() - started).total_seconds() * 1000)
        return outcome

    async def _lookup_order(self, args: dict[str, Any], user_id: str) -> ToolOutcome:
        order_id = str(args.get("order_id") or "").strip().upper()
        if not order_id:
            return ToolOutcome("lookup_order", False, "缺少订单号")
        order = self.orders.get(order_id)
        if not order:
            return ToolOutcome(
                "lookup_order",
                False,
                f"未找到订单 {order_id}，请核对订单号",
                {"found": False, "order_id": order_id},
            )
        summary = f"{order_id} · {order['status']} · {order['product']} · {order['estimated_text']}"
        return ToolOutcome("lookup_order", True, summary, {"found": True, **order})

    async def _check_refund(self, args: dict[str, Any], user_id: str) -> ToolOutcome:
        order_id = str(args.get("order_id") or "").strip().upper()
        reason = truncate(str(args.get("reason") or "未说明原因"), 160)
        order = self.orders.get(order_id)
        if not order:
            return ToolOutcome("check_refund_eligibility", False, f"未找到订单 {order_id}")
        if order["status_code"] == "pending":
            return ToolOutcome(
                "check_refund_eligibility",
                True,
                f"{order_id} 尚未发货，可直接取消订单并全额退款",
                {
                    "eligible": True,
                    "order_id": order_id,
                    "reason_type": "未发货取消",
                    "window_days": None,
                    "days_since_delivery": 0,
                    "note": "未发货订单可直接取消，无需等待仓库验收。",
                },
            )
        if not order.get("delivered_at"):
            return ToolOutcome(
                "check_refund_eligibility",
                True,
                f"{order_id} 运输中，建议送达后验货再申请",
                {
                    "eligible": False,
                    "order_id": order_id,
                    "reason_type": "运输中",
                    "window_days": None,
                    "days_since_delivery": 0,
                    "note": "包裹运输中，可先拒收或送达后 7 天内申请。",
                },
            )

        quality_words = ("漏水", "破损", "坏了", "故障", "质量", "瑕疵", "不保温", "异味")
        is_quality = any(word in reason for word in quality_words)
        elapsed = days_since(order["delivered_at"])
        vip = "VIP" in order["member_tier"]
        window = 15 if (is_quality or vip) else 7
        eligible = elapsed <= window
        if is_quality:
            reason_type = "质量问题"
            note = "质量问题需上传问题照片/视频，商家承担寄回运费。" if eligible else "质量问题超过 15 天，转保修检测。"
        elif vip:
            reason_type = "VIP 无理由退货"
            note = "悦享 VIP 无理由退货窗口为签收后 15 天，商品需不影响二次销售。"
        else:
            reason_type = "七天无理由"
            note = "商品需未使用、包装配件齐全；寄回运费由消费者承担。"

        return ToolOutcome(
            "check_refund_eligibility",
            True,
            f"{'符合' if eligible else '不符合'}{window}天{reason_type}条件（签收第{elapsed}天）",
            {
                "eligible": eligible,
                "order_id": order_id,
                "reason_type": reason_type,
                "window_days": window,
                "days_since_delivery": elapsed,
                "note": note,
                "next_step": "可发起退货申请" if eligible else "可转保修或人工复核",
            },
        )

    async def _search_knowledge(self, args: dict[str, Any], user_id: str) -> ToolOutcome:
        query = truncate(str(args.get("query") or ""), 200)
        results = self.knowledge.search(query, top_k=3)
        if not results:
            return ToolOutcome("search_knowledge_base", False, "知识库没有命中相关内容", {"results": []})
        citations = []
        for item in results:
            citations.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "snippet": item["snippet"],
                    "content": item["content"],
                    "score": item["score"],
                }
            )
        return ToolOutcome(
            "search_knowledge_base",
            True,
            f"命中 {len(results)} 条知识：{results[0]['title']}",
            {"results": results},
            citations=citations,
        )

    async def _create_ticket(self, args: dict[str, Any], user_id: str) -> ToolOutcome:
        issue = truncate(str(args.get("issue") or "用户售后问题"), 240)
        order_id = str(args.get("order_id") or "").strip().upper() or None
        urgency = str(args.get("urgency") or "normal")
        ticket = self.tickets.create(order_id, issue, urgency, user_id)
        return ToolOutcome(
            "create_ticket",
            True,
            f"工单 {ticket['id']} 已创建，等待售后专员处理",
            {"ticket": ticket},
        )

    async def _handoff(self, args: dict[str, Any], user_id: str) -> ToolOutcome:
        reason = truncate(str(args.get("reason") or "用户要求人工"), 200)
        urgency = str(args.get("urgency") or "normal")
        queue = 2 if urgency == "high" else 3
        handoff_id = "H" + uuid.uuid4().hex[:6].upper()
        return ToolOutcome(
            "handoff_to_human",
            True,
            f"已进入人工队列，前方 {queue} 人，预计 3-6 分钟",
            {
                "handoff_id": handoff_id,
                "queue_position": queue,
                "estimated_minutes": "3-6",
                "online_hours": "9:00-21:00",
                "reason": mask_pii(reason),
                "summary_card": "转人工摘要已生成，人工客服可看到订单与知识库依据。",
            },
        )

    def order_snapshot(self, order_id: str | None) -> dict[str, Any] | None:
        if not order_id:
            return None
        order = self.orders.get(order_id.upper())
        return dict(order) if order else None

    def resolve_order_id(self, message: str, last_order_id: str | None) -> str | None:
        return extract_order_id(message) or last_order_id
