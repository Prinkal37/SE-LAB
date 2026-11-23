"""Application settings, read from environment variables / .env (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- core ---
    app_name: str = "Adaptive Viva Generator API"
    api_prefix: str = "/api/v1"
    # SQLite for local dev/tests, PostgreSQL in Docker/production:
    # postgresql+psycopg://avg:avg@db:5432/avg
    database_url: str = "sqlite:///./avg.db"
    # Comma-separated list of frontend origins allowed to call the API with cookies.
    cors_origins: str = "http://localhost:3000"

    # --- auth (NFR-5.3.3 / 5.3.4) ---
    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    cookie_name: str = "avg_token"
    cookie_secure: bool = False  # True in production (HTTPS)
    cookie_samesite: str = "lax"  # "none" when frontend and API are on different sites

    # --- encryption at rest (NFR-5.3.1) ---
    # Fernet key (generate: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
    # Empty = store code as plain text (dev only).
    encryption_key: str = ""

    # --- uploads (FR-4.2.3) ---
    max_file_bytes: int = 5 * 1024 * 1024
    max_zip_bytes: int = 50 * 1024 * 1024
    max_zip_members: int = 500

    # --- AST thresholds (FR-4.3.3) ---
    max_nesting_depth: int = 3
    max_function_lines: int = 50
    high_complexity: int = 10

    # --- question generation (FR-4.4.x) ---
    min_questions: int = 3
    max_questions: int = 5
    # Any LiteLLM model string, e.g. "gpt-4o-mini", "groq/llama-3.1-8b-instant",
    # "gemini/gemini-1.5-flash". Empty = offline template generator (no API key needed).
    llm_model: str = ""
    # "tools" (function calling, best for OpenAI/Anthropic/Gemini) or "json" (works with almost any model)
    llm_mode: str = "tools"
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 30
    # NFR-5.3.5: send only short flagged snippets, never the whole file.
    llm_send_snippets: bool = True
    llm_snippet_max_lines: int = 12

    # --- background jobs (NFR-5.1.2) ---
    # "rq" = Redis queue + separate worker process; "inline" = FastAPI background task
    queue_mode: str = "inline"
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "avg"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
