"""Single source of configuration. Every value can be overridden from the environment / `.env`."""

from functools import cached_property
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated

BACKEND_DIR = Path(__file__).resolve().parents[2]
# The single project-wide `.env` lives at the repository root (shared with the frontend and Docker).
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"

# Placeholder shipped in .env.example; never accepted in production.
INSECURE_SECRET_PLACEHOLDER = "change-me-in-production"  # noqa: S105


def parse_pricing(value: str) -> Dict[str, Tuple[float, float]]:
    """Parse "model=in/out,model2=in/out" into {model: (usd per 1M input tokens, usd per 1M output tokens)}."""
    prices: Dict[str, Tuple[float, float]] = {}
    for entry in filter(None, (part.strip() for part in value.split(","))):
        try:
            model, rates = entry.split("=", 1)
            input_rate, output_rate = (float(r) for r in rates.split("/", 1))
        except ValueError as exc:
            raise ValueError(f"LLM_PRICING entry {entry!r} must look like model=input/output") from exc
        if not model.strip() or input_rate < 0 or output_rate < 0:
            raise ValueError(f"LLM_PRICING entry {entry!r} must look like model=input/output")
        prices[model.strip()] = (input_rate, output_rate)
    return prices


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # ---- Application -------------------------------------------------------------------------
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "Promise vs. Progress Engine"
    APP_HOST: str = "0.0.0.0"  # noqa: S104 - bind address inside the container
    APP_PORT: int = Field(default=8000, ge=1, le=65535)
    APP_RELOAD: bool = False
    API_PREFIX: str = "/api/v1"
    # IANA timezone that decides what "today" means for due/overdue checks.
    APP_TIMEZONE: str = "UTC"

    # ---- Logging -----------------------------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_TO_CONSOLE: bool = True
    LOG_TO_FILE: bool = True
    # Relative paths resolve against the project root (next to `.env`).
    LOG_DIR: Path = Path("logs")
    LOG_FILE_PREFIX: str = Field(default="app", pattern=r"^[A-Za-z0-9_-]{1,40}$")
    # A new timestamped file starts when the current one reaches this size.
    LOG_FILE_MAX_MB: float = Field(default=2.0, gt=0, le=1024)
    # Oldest files beyond this count are deleted.
    LOG_MAX_FILES: int = Field(default=6, ge=1, le=1000)
    # Files older than this are deleted even when under LOG_MAX_FILES (0 = keep by count only).
    LOG_RETENTION_DAYS: int = Field(default=7, ge=0, le=3650)

    # ---- Startup checks ----------------------------------------------------------------------
    # Probe every integration before serving traffic and log the result of each check.
    STARTUP_CHECKS_ENABLED: bool = True
    STARTUP_CHECK_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=120)
    # Live LLM probe sends one tiny request per configured provider (a few tokens).
    STARTUP_CHECK_LLM: bool = True
    STARTUP_CHECK_GITHUB: bool = True
    STARTUP_CHECK_SMTP: bool = True
    # Verifies the Langfuse keys (only when LANGFUSE_ENABLED=true).
    STARTUP_CHECK_LANGFUSE: bool = True
    # Refuse to start when a warning-level check fails (the database is always required).
    STARTUP_FAIL_ON_WARNING: bool = False

    # ---- Frontend / HTTP ---------------------------------------------------------------------
    # Public URL of the web app (used for CORS and for links in emails).
    FRONTEND_URL: str = "http://localhost:5173"
    # Extra allowed browser origins, comma-separated. FRONTEND_URL is always allowed.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = []

    # ---- Security ----------------------------------------------------------------------------
    SECRET_KEY: str = INSECURE_SECRET_PLACEHOLDER
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=720, ge=5)
    PASSWORD_MIN_LENGTH: int = Field(default=10, ge=8, le=64)
    LOGIN_ATTEMPTS_PER_MINUTE: int = Field(default=10, ge=1)
    SIGNUPS_PER_HOUR_PER_IP: int = Field(default=5, ge=1)
    DEMO_MODE: bool = False  # isolated throwaway workspaces on the sign-in page

    # ---- Storage -----------------------------------------------------------------------------
    DATA_DIR: Path = BACKEND_DIR / "data"
    DATABASE_URL: Optional[str] = None  # default: SQLite in DATA_DIR
    RUN_MIGRATIONS_ON_STARTUP: bool = True
    # Folder with the sample meeting transcripts offered in the New meeting wizard (relative = project root).
    SAMPLES_DIR: Path = Path("samples")
    # Connection pool per API process (Postgres only; SQLite ignores these).
    # Keep (DB_POOL_SIZE + DB_MAX_OVERFLOW) x processes below the server's max_connections, or put PgBouncer in front.
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=200)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=200)
    DB_POOL_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    # Recycle connections older than this, so idle connections dropped by proxies/firewalls are replaced.
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=60)

    # ---- LLM (shared) ------------------------------------------------------------------------
    # Provider tried first when both have keys: "gemini" or "openai".
    LLM_DEFAULT_PROVIDER: Literal["gemini", "openai"] = "gemini"
    LLM_TEMPERATURE: float = Field(default=0.1, ge=0.0, le=2.0)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=256)
    LLM_TIMEOUT_SECONDS: float = Field(default=45.0, gt=0)
    # Extra attempts the extraction agent makes when the model returns invalid JSON.
    LLM_MAX_REPAIR_ATTEMPTS: int = Field(default=1, ge=0, le=3)
    # Retries for temporary provider errors (HTTP 429 / 5xx), with exponential backoff.
    LLM_TRANSIENT_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_RETRY_BACKOFF_SECONDS: float = Field(default=2.0, ge=0, le=30)
    # After a "quota exceeded" error, skip that model for this long and use the fallback directly.
    LLM_MODEL_COOLDOWN_SECONDS: int = Field(default=300, ge=0, le=86400)
    # Per-task overrides; leave empty to use LLM_TEMPERATURE.
    EXTRACTION_TEMPERATURE: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    BRIEFING_TEMPERATURE: Optional[float] = Field(default=None, ge=0.0, le=2.0)

    # ---- LLM providers -----------------------------------------------------------------------
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    # Lighter model tried when GEMINI_MODEL is overloaded (HTTP 429/5xx); empty = no fallback.
    GEMINI_FALLBACK_MODEL: Optional[str] = None
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_FALLBACK_MODEL: Optional[str] = None
    # OpenAI-compatible endpoint (Azure OpenAI, vLLM, a self-hosted gateway...). Empty = api.openai.com.
    OPENAI_BASE_URL: Optional[str] = None

    # ---- Extraction --------------------------------------------------------------------------
    MAX_TRANSCRIPT_CHARS: int = Field(default=100_000, ge=1_000)
    MAX_PARTICIPANTS: int = Field(default=50, ge=1)

    # ---- Semantic search ---------------------------------------------------------------------
    SEMANTIC_SEARCH_ENABLED: bool = True
    CHROMA_PERSIST_DIRECTORY: Optional[Path] = None
    # "local" (offline hashed embeddings) or "gemini" (needs GEMINI_API_KEY).
    EMBEDDING_PROVIDER: Literal["local", "gemini"] = "local"
    SEMANTIC_SEARCH_RESULTS: int = Field(default=10, ge=1, le=50)

    # ---- GitHub ------------------------------------------------------------------------------
    # Without a token the engine runs in explicit, clearly labelled simulation mode.
    GITHUB_PERSONAL_ACCESS_TOKEN: Optional[str] = None
    GITHUB_DEFAULT_OWNER: Optional[str] = None
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    GITHUB_MAX_CONCURRENCY: int = Field(default=8, ge=1, le=50)

    # ---- Jira (server-wide default; users can connect their own in Settings) ------------------
    JIRA_BASE_URL: Optional[str] = None
    JIRA_EMAIL: Optional[str] = None
    JIRA_API_TOKEN: Optional[str] = None
    JIRA_PROJECT_KEY: Optional[str] = None
    JIRA_ISSUE_TYPE: str = "Task"
    JIRA_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=120)

    # ---- Slack (server-wide default; users can connect their own in Settings) -----------------
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL: Optional[str] = None
    SLACK_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=120)

    # ---- Integrations --------------------------------------------------------------------------
    # Tools users can connect. The others are shown as "Coming soon" and are never called.
    ENABLED_INTEGRATIONS: Annotated[List[str], NoDecode] = Field(default_factory=lambda: ["github"])
    # Extra hosts users may point connectors at (e.g. a self-hosted Jira), comma-separated.
    # By default only the tools' own domains are accepted, so user-supplied URLs cannot reach internal services.
    INTEGRATION_ALLOWED_HOSTS: Annotated[List[str], NoDecode] = Field(default_factory=list)
    # "Test connection" calls allowed per user per 5 minutes.
    INTEGRATION_TESTS_PER_5_MIN: int = Field(default=20, ge=1, le=1000)

    # ---- Reconciliation ----------------------------------------------------------------------
    # Commitments due within this many days with no progress are flagged "at risk".
    AT_RISK_WINDOW_DAYS: int = Field(default=2, ge=0, le=30)
    # How often the background job re-checks GitHub for every user.
    VERIFICATION_INTERVAL_MINUTES: int = Field(default=60, ge=5)
    ENABLE_SCHEDULER: bool = True  # with several API replicas, enable in exactly one

    # ---- Email -------------------------------------------------------------------------------
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "briefings@example.com"
    SMTP_STARTTLS: bool = True
    SMTP_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0)
    EMAILS_PER_USER_PER_DAY: int = Field(default=50, ge=1)

    # ---- Observability (Langfuse) ------------------------------------------------------------
    # Master switch. When false (or when Langfuse is unreachable or misconfigured) tracing is a no-op
    # and the application behaves exactly the same.
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    # https://cloud.langfuse.com (EU), https://us.cloud.langfuse.com (US) or a self-hosted URL.
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    # Defaults to ENVIRONMENT when empty.
    LANGFUSE_ENVIRONMENT: Optional[str] = None
    # Free-form release/version tag attached to every trace (e.g. a git SHA).
    LANGFUSE_RELEASE: Optional[str] = None
    # Share of traces to keep (1.0 = all).
    LANGFUSE_SAMPLE_RATE: float = Field(default=1.0, ge=0, le=1)
    # Send prompts, transcripts and model outputs. false = only metadata, tokens, cost and timings.
    LANGFUSE_CAPTURE_CONTENT: bool = True
    LANGFUSE_FLUSH_AT: int = Field(default=15, ge=1, le=1000)
    LANGFUSE_FLUSH_INTERVAL_SECONDS: float = Field(default=5.0, gt=0, le=300)
    LANGFUSE_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=120)
    LANGFUSE_DEBUG: bool = False
    # Optional USD prices per 1M tokens, used to report cost for models Langfuse has no price for:
    # model=input/output pairs separated by commas, e.g. "gemini-3.8-flash=0.30/2.50,gpt-5-mini=0.25/2.00".
    LLM_PRICING: str = ""

    # ---- Validators --------------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", "INTEGRATION_ALLOWED_HOSTS", "ENABLED_INTEGRATIONS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "GEMINI_FALLBACK_MODEL",
        "OPENAI_FALLBACK_MODEL",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "GITHUB_DEFAULT_OWNER",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_HOST",
        "DATABASE_URL",
        "EXTRACTION_TEMPERATURE",
        "BRIEFING_TEMPERATURE",
        "LANGFUSE_PUBLIC_KEY",
        "JIRA_BASE_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_PROJECT_KEY",
        "SLACK_WEBHOOK_URL",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_ENVIRONMENT",
        "LANGFUSE_RELEASE",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("LLM_PRICING")
    @classmethod
    def _validate_pricing(cls, value: str) -> str:
        parse_pricing(value)  # raises ValueError with the offending entry
        return value

    @field_validator("API_PREFIX")
    @classmethod
    def _normalise_prefix(cls, value: str) -> str:
        return "/" + value.strip("/")

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == INSECURE_SECRET_PLACEHOLDER or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be a random value of at least 32 characters in production")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        if self.EMBEDDING_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("EMBEDDING_PROVIDER=gemini requires GEMINI_API_KEY")
        return self

    # ---- Derived values ----------------------------------------------------------------------
    @cached_property
    def data_dir(self) -> Path:
        path = self.DATA_DIR if self.DATA_DIR.is_absolute() else BACKEND_DIR / self.DATA_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_dir(self) -> Path:
        return self.LOG_DIR if self.LOG_DIR.is_absolute() else PROJECT_DIR / self.LOG_DIR

    @property
    def samples_dir(self) -> Path:
        return self.SAMPLES_DIR if self.SAMPLES_DIR.is_absolute() else PROJECT_DIR / self.SAMPLES_DIR

    @property
    def log_file_max_bytes(self) -> int:
        return int(self.LOG_FILE_MAX_MB * 1024 * 1024)

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL or f"sqlite+aiosqlite:///{self.data_dir / 'app.db'}"

    @property
    def chroma_dir(self) -> Path:
        path = self.CHROMA_PERSIST_DIRECTORY or self.data_dir / "chroma"
        return path if path.is_absolute() else BACKEND_DIR / path

    @property
    def allowed_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL.rstrip("/"), *self.CORS_ORIGINS]
        return list(dict.fromkeys(o for o in origins if o))

    @property
    def extraction_temperature(self) -> float:
        return self.LLM_TEMPERATURE if self.EXTRACTION_TEMPERATURE is None else self.EXTRACTION_TEMPERATURE

    @property
    def briefing_temperature(self) -> float:
        return self.LLM_TEMPERATURE if self.BRIEFING_TEMPERATURE is None else self.BRIEFING_TEMPERATURE

    @property
    def github_mode(self) -> Literal["live", "simulated"]:
        return "live" if self.GITHUB_PERSONAL_ACCESS_TOKEN else "simulated"

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @property
    def langfuse_environment(self) -> str:
        return self.LANGFUSE_ENVIRONMENT or self.ENVIRONMENT

    @cached_property
    def llm_pricing(self) -> Dict[str, Tuple[float, float]]:
        return parse_pricing(self.LLM_PRICING)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)


settings = Settings()
