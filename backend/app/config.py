"""Application settings, loaded once from the environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database -------------------------------------------------------
    # Async driver URL used by the API and the worker.
    database_url: str = (
        "postgresql+asyncpg://supervisor:supervisor@localhost:5432/order_supervisor"
    )

    # --- Temporal -------------------------------------------------------
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "order-supervisor"

    # --- LLM ------------------------------------------------------------
    # "live"  -> call the Gemini/Anthropic API (requires gemini_api_key or anthropic_api_key)
    # "mock"  -> deterministic rule-based stand-in, no network, no key
    # "auto"  -> live when a key is present, mock otherwise
    llm_mode: str = "auto"
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None

    # Main reasoning agent.
    agent_model: str = "gemini-3.5-flash"
    # Cheap wake-up classifier. One small structured call per incoming event.
    classifier_model: str = "gemini-3.5-flash-lite"
    agent_effort: str = "medium"  # low | medium | high | xhigh | max
    #: Cross-provider safety net. When the primary model errors — a quota
    #: exhaustion, a bad model name, a transport fault — the call is retried
    #: once here before the deterministic policy takes the turn. Different
    #: vendor on purpose: a provider-wide outage or a per-project quota should
    #: not take both tiers down at once.
    fallback_model: str = "openai/gpt-oss-120b"
    #: Output ceiling for fallback calls. Groq reserves ``max_tokens`` against
    #: a per-minute allowance (8k on the free tier), so asking for the agent's
    #: full budget would spend a whole minute of capacity on one call.
    groq_max_tokens: int = 2000
    agent_max_tokens: int = 8000
    # Safety valve on the agent's internal tool-calling loop.
    agent_max_tool_iterations: int = 6

    # --- Workflow defaults ---------------------------------------------
    default_wake_seconds: int = 900  # 15 min between scheduled reviews
    default_max_run_age_seconds: int = 60 * 60 * 24 * 7  # 7 days
    # Roll the workflow over once it has processed this many triggers, so
    # Temporal history stays small on very long-lived orders.
    continue_as_new_after_turns: int = 40
    # Fold the timeline into the rolling summary past this many entries.
    memory_compaction_threshold: int = 12

    # --- API ------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://localhost:4040"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """psycopg2 URL — Alembic runs migrations synchronously."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def llm_live(self) -> bool:
        if self.llm_mode == "live":
            return True
        if self.llm_mode == "mock":
            return False
        return bool(
            self.gemini_api_key or self.anthropic_api_key or self.groq_api_key
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
