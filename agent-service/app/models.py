from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    sessionId: str = Field(min_length=1, max_length=64)
    userId: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    clientMessageId: str = Field(min_length=1, max_length=80)
    channel: str = Field(default="web", max_length=24)


class CancelRequest(BaseModel):
    sessionId: str = Field(min_length=1, max_length=64)
    clientMessageId: str = Field(min_length=1, max_length=80)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "mock"
    degraded: bool = False
    note: str = ""


@dataclass
class ToolOutcome:
    name: str
    ok: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class TurnContext:
    message: str
    rewritten_query: str
    intent: str
    order_id: str | None = None
    profile: dict[str, Any] = field(default_factory=dict)
    tool_round: int = 0
    tool_outcomes: list[ToolOutcome] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    cited_ids: list[int] = field(default_factory=list)
    degraded: bool = False
    provider_note: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "mock"

    def has_tool(self, name: str) -> bool:
        return any(item.name == name for item in self.tool_outcomes)

    def first(self, name: str) -> ToolOutcome | None:
        return next((item for item in self.tool_outcomes if item.name == name), None)


def sse_line(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


EventType = Literal[
    "meta",
    "stage",
    "tool_start",
    "tool_result",
    "memory",
    "citations",
    "cache",
    "token",
    "grounding",
    "usage",
    "guardrail",
    "done",
    "error",
    "cancelled",
]
