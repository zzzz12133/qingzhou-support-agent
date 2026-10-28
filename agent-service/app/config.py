from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = SERVICE_DIR.parent


def load_dotenv() -> None:
    """读取项目根目录的 .env，不依赖 python-dotenv。"""
    for candidate in (PROJECT_DIR / ".env", SERVICE_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("AGENT_DATA_DIR", SERVICE_DIR / "data")))
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock").strip().lower())
    fallbacks: tuple[str, ...] = field(default_factory=lambda: _env_list("LLM_FALLBACKS"))
    request_timeout: float = field(default_factory=lambda: _env_float("LLM_TIMEOUT_SECONDS", 25.0))
    recent_messages: int = field(default_factory=lambda: _env_int("RECENT_MESSAGES", 12))
    summary_trigger: int = field(default_factory=lambda: _env_int("SUMMARY_TRIGGER", 16))
    token_budget: int = field(default_factory=lambda: _env_int("CONTEXT_TOKEN_BUDGET", 3200))
    max_tool_rounds: int = field(default_factory=lambda: _env_int("MAX_TOOL_ROUNDS", 4))
    max_message_chars: int = field(default_factory=lambda: _env_int("MAX_MESSAGE_CHARS", 2000))
    cache_ttl_seconds: int = field(default_factory=lambda: _env_int("CACHE_TTL_SECONDS", 600))
    cache_max_entries: int = field(default_factory=lambda: _env_int("CACHE_MAX_ENTRIES", 128))
    enable_semantic_cache: bool = field(default_factory=lambda: _env_bool("ENABLE_SEMANTIC_CACHE", True))
    tool_delay_seconds: float = field(default_factory=lambda: _env_float("TOOL_DELAY_SECONDS", 0.18))
    stream_delay_seconds: float = field(default_factory=lambda: _env_float("STREAM_CHUNK_DELAY", 0.006))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def tickets_file(self) -> Path:
        return self.data_dir / "tickets.json"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    label: str
    base_url: str
    model: str
    api_key: str
    timeout: float


def resolve_provider_config(name: str, settings: Settings) -> ProviderConfig | None:
    """把供应商名解析成连接信息。所有密钥只从环境变量读取。"""
    name = name.strip().lower()
    common_key = os.getenv("LLM_API_KEY", "").strip()
    if name == "mock":
        return ProviderConfig("mock", "本地演示模型", "", "mock-planner-v1", "", settings.request_timeout)

    preset: dict[str, str] = {}
    if name == "deepseek":
        preset = {
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "api_key": os.getenv("DEEPSEEK_API_KEY", "") or common_key,
            "label": "DeepSeek",
        }
    elif name == "openai":
        preset = {
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": os.getenv("OPENAI_API_KEY", "") or common_key,
            "label": "OpenAI",
        }
    elif name in {"custom", "openai-compatible", "compatible"}:
        preset = {
            "base_url": os.getenv("LLM_BASE_URL", ""),
            "model": os.getenv("LLM_MODEL", ""),
            "api_key": common_key,
            "label": "自定义模型",
        }
    else:
        return None

    # 主供应商允许通过 LLM_* 覆盖；空值不覆盖，避免 .env 里未填写的通用变量
    # 把 DEEPSEEK_API_KEY / OPENAI_API_KEY 冲掉。
    if settings.provider == name:
        base_url = os.getenv("LLM_BASE_URL") or preset["base_url"]
        model = os.getenv("LLM_MODEL") or preset["model"]
        api_key = os.getenv("LLM_API_KEY") or preset["api_key"]
    else:
        base_url = preset["base_url"]
        model = preset["model"]
        api_key = preset["api_key"]

    if not base_url or not model or not api_key:
        return None
    return ProviderConfig(name, preset["label"], base_url.rstrip("/"), model, api_key, settings.request_timeout)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(os.getenv("AGENT_DATA_DIR", SERVICE_DIR / "data")).resolve()
    return Settings(
        data_dir=data_dir,
        provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
        fallbacks=_env_list("LLM_FALLBACKS"),
        request_timeout=_env_float("LLM_TIMEOUT_SECONDS", 25.0),
        recent_messages=_env_int("RECENT_MESSAGES", 12),
        summary_trigger=_env_int("SUMMARY_TRIGGER", 16),
        token_budget=_env_int("CONTEXT_TOKEN_BUDGET", 3200),
        max_tool_rounds=_env_int("MAX_TOOL_ROUNDS", 4),
        max_message_chars=_env_int("MAX_MESSAGE_CHARS", 2000),
        cache_ttl_seconds=_env_int("CACHE_TTL_SECONDS", 600),
        cache_max_entries=_env_int("CACHE_MAX_ENTRIES", 128),
        enable_semantic_cache=_env_bool("ENABLE_SEMANTIC_CACHE", True),
        tool_delay_seconds=_env_float("TOOL_DELAY_SECONDS", 0.18),
        stream_delay_seconds=_env_float("STREAM_CHUNK_DELAY", 0.006),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
