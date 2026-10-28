from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .text_utils import truncate

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class SessionAccessError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class ChatMessage:
    id: str
    role: str
    content: str
    created_at: str
    status: str = "done"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "createdAt": self.created_at,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        return cls(
            id=data["id"],
            role=data["role"],
            content=data["content"],
            created_at=data.get("createdAt", now_iso()),
            status=data.get("status", "done"),
            metadata=data.get("metadata") or {},
        )


@dataclass
class SessionState:
    id: str
    user_id: str
    title: str = "新对话"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    messages: list[ChatMessage] = field(default_factory=list)
    summary: str = ""
    summarized_count: int = 0
    profile: dict[str, Any] = field(default_factory=dict)
    last_order_id: str | None = None
    turn_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "title": self.title,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "messages": [message.to_dict() for message in self.messages],
            "summary": self.summary,
            "summarizedCount": self.summarized_count,
            "profile": self.profile,
            "lastOrderId": self.last_order_id,
            "turnCount": self.turn_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        return cls(
            id=data["id"],
            user_id=data["userId"],
            title=data.get("title", "新对话"),
            created_at=data.get("createdAt", now_iso()),
            updated_at=data.get("updatedAt", now_iso()),
            messages=[ChatMessage.from_dict(item) for item in data.get("messages", [])],
            summary=data.get("summary", ""),
            summarized_count=int(data.get("summarizedCount", 0)),
            profile=data.get("profile") or {},
            last_order_id=data.get("lastOrderId"),
            turn_count=int(data.get("turnCount", 0)),
        )


class SessionStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("非法会话 ID")
        return self.directory / f"{session_id}.json"

    def get_or_create(self, session_id: str, user_id: str) -> SessionState:
        session = self.try_get(session_id, user_id)
        if session:
            return session
        with self._lock:
            session = SessionState(id=session_id, user_id=user_id)
            self.save(session)
            return session

    def try_get(self, session_id: str, user_id: str) -> SessionState | None:
        with self._lock:
            path = self._path(session_id)
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                session = SessionState.from_dict(data)
            except (json.JSONDecodeError, OSError, KeyError) as exc:
                raise ValueError("会话数据损坏") from exc
            if session.user_id != user_id:
                raise SessionAccessError("无权访问该会话")
            return session

    def save(self, session: SessionState) -> None:
        with self._lock:
            session.updated_at = now_iso()
            path = self._path(session.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)

    def append_message(
        self,
        session: SessionState,
        role: str,
        content: str,
        *,
        status: str = "done",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=uuid.uuid4().hex,
            role=role,
            content=content,
            created_at=now_iso(),
            status=status,
            metadata=metadata or {},
        )
        session.messages.append(message)
        if role == "user":
            session.turn_count += 1
            if session.title == "新对话":
                session.title = truncate(content.replace("\n", " "), 24)
        self.save(session)
        return message

    def snapshot(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self.try_get(session_id, user_id)
        if not session:
            raise KeyError(session_id)
        return session.to_dict()

    def delete(self, session_id: str, user_id: str) -> None:
        with self._lock:
            path = self._path(session_id)
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("userId") != user_id:
                raise SessionAccessError("无权删除该会话")
            path.unlink()

    @staticmethod
    def message_payload(message: ChatMessage) -> dict[str, Any]:
        return message.to_dict()

    @staticmethod
    def session_summary(session: SessionState) -> dict[str, Any]:
        last_message = next((item for item in reversed(session.messages) if item.role == "assistant"), None)
        return {
            "id": session.id,
            "title": session.title,
            "updatedAt": session.updated_at,
            "messageCount": len(session.messages),
            "preview": truncate(last_message.content.replace("\n", " "), 52) if last_message else "还没有消息",
        }
