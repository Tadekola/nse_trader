import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from dotenv import load_dotenv
from functools import lru_cache

# Load .env file variables
load_dotenv()


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # tolerate stale env vars from old .env files
    )

    PROJECT_NAME: str = "NSE Trader API"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://nse_trader:nse_trader@localhost:5432/nse_trader",
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://nse_trader:nse_trader@localhost:5432/nse_trader",
    )

    # Cache TTL
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Historical data
    MIN_OHLCV_SESSIONS: int = 60  # Minimum sessions required for indicators
    MIN_ASI_SESSIONS: int = 60  # Minimum ASI sessions for regime engine
    OHLCV_STALENESS_DAYS: int = 5  # Data older than N trading days is stale

    # Centralized HTTP client
    HTTP_TIMEOUT_SECONDS: float = 10.0
    HTTP_MAX_RETRIES: int = 3
    HTTP_BACKOFF_BASE: float = 0.5  # base seconds for exponential backoff
    HTTP_BACKOFF_MAX: float = 30.0  # max backoff cap
    HTTP_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    # NGX Official List PDF
    NGX_PDF_CACHE_DIR: str = "data/ngx_pdfs"  # Local cache for downloaded PDFs
    NGX_PDF_URL_TEMPLATE: str = (
        "https://doclib.ngxgroup.com/DownloadsContent/"
        "Daily%20Official%20List%20-%20Equities%20for%20{dd}-{mm}-{yyyy}.pdf"
    )

    # ── Security (Beta Hardening) ──────────────────────────────────────
    API_KEY_HEADER: str = "X-API-Key"
    # Comma-separated list of allowed origins for CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3002"
    # Rate limiting (requests per minute)
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_HEAVY: str = "30/minute"       # /recommendations, /scanner
    RATE_LIMIT_WRITE: str = "20/minute"        # POST endpoints


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
