from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import AgentService
from .cache import SemanticCache
from .config import Settings, get_settings
from .knowledge import KnowledgeBase
from .models import AgentRequest, CancelRequest, sse_line
from .providers import build_router
from .store import SessionAccessError, SessionStore
from .tools import TOOL_LABELS, TOOL_SCHEMAS, ToolRegistry

logger = logging.getLogger(__name__)


def build_service(settings: Settings | None = None) -> AgentService:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    knowledge = KnowledgeBase(settings.knowledge_dir)
    store = SessionStore(settings.sessions_dir)
    tools = ToolRegistry(settings, knowledge)
    router = build_router(settings)
    cache = SemanticCache(settings.cache_ttl_seconds, settings.cache_max_entries, knowledge.version)
    return AgentService(settings, router, store, knowledge, tools, cache)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.service = build_service()
    logger.info("客服 Agent 服务已启动")
    yield
    logger.info("客服 Agent 服务已停止")


app = FastAPI(
    title="晴舟客服 Agent",
    version="0.1.0",
    description="客服 Agent 与工具调用服务：记忆、RAG、护栏、模型降级。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8088",
        "http://127.0.0.1:8088",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    elapsed = int((time.monotonic() - started) * 1000)
    logger.info("%s %s %s %sms", request.method, request.url.path, response.status_code, elapsed)
    return response


def service(request: Request) -> AgentService:
    return request.app.state.service


@app.get("/")
async def index() -> dict[str, Any]:
    return {
        "name": "晴舟客服 Agent",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/v1/health",
    }


@app.get("/v1/health")
async def health(request: Request) -> dict[str, Any]:
    payload = service(request).health()
    payload["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return payload


@app.get("/v1/tools")
async def tools() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": item["function"]["name"],
                "label": TOOL_LABELS.get(item["function"]["name"], item["function"]["name"]),
                "description": item["function"]["description"],
            }
            for item in TOOL_SCHEMAS
        ]
    }


@app.get("/v1/knowledge/search")
async def search_knowledge(request: Request, q: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
    results = service(request).knowledge.search(q, top_k=5)
    return {"query": q, "results": results, "version": service(request).knowledge.version}


@app.post("/v1/agent/stream")
async def stream_agent(payload: AgentRequest, request: Request) -> StreamingResponse:
    agent = service(request)

    async def generate() -> AsyncIterator[str]:
        try:
            async for event in agent.stream(payload, request.is_disconnected):
                if await request.is_disconnected():
                    break
                yield sse_line(event)
        except asyncio.CancelledError:
            logger.info("stream disconnected session=%s", payload.sessionId)
            raise
        except Exception:
            logger.exception("stream failed session=%s", payload.sessionId)
            yield sse_line(
                {
                    "type": "error",
                    "code": "STREAM_FAILED",
                    "message": "连接中断，请重试。",
                    "retryable": True,
                }
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/v1/agent/cancel")
async def cancel_agent(payload: CancelRequest, request: Request) -> dict[str, Any]:
    cancelled = await service(request).cancel(payload.sessionId, payload.clientMessageId)
    return {"cancelled": cancelled}


@app.get("/v1/sessions/{session_id}")
async def session_snapshot(
    session_id: str,
    request: Request,
    user_id: str = Query(default="demo-user", min_length=1, max_length=64),
) -> dict[str, Any]:
    try:
        data = service(request).store.snapshot(session_id, user_id)
    except SessionAccessError:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # 调试接口只返回结构与记忆，不重复暴露全部消息。
    return {
        "id": data["id"],
        "title": data["title"],
        "profile": data["profile"],
        "summary": data["summary"],
        "summarizedCount": data["summarizedCount"],
        "lastOrderId": data["lastOrderId"],
        "messageCount": len(data["messages"]),
        "turnCount": data["turnCount"],
    }
