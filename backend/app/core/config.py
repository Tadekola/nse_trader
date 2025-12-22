import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from functools import lru_cache

# Load .env file variables
load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "NSE Trader API"
    API_V1_STR: str = "/api/v1"

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD")
    REDIS_URL: str | None = None # Construct if needed, e.g., redis://:[password]@[host]:[port]/[db]
    CACHE_TTL_SECONDS: int = 300 # 5 minutes

    # RabbitMQ Configuration
    RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "localhost")
    RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", 5672))
    RABBITMQ_USER: str | None = os.getenv("RABBITMQ_USER")
    RABBITMQ_PASSWORD: str | None = os.getenv("RABBITMQ_PASSWORD")
    RABBITMQ_VHOST: str = os.getenv("RABBITMQ_VHOST", "/")
    CELERY_BROKER_URL: str | None = None # Construct: amqp://user:pass@host:port/vhost

    # External APIs (Placeholders - use secure secret management in production)
    NGX_API_BASE_URL: str = "http://localhost:8001/ngx-sim" # Example simulator URL
    TRADINGVIEW_API_KEY: str | None = os.getenv("TRADINGVIEW_API_KEY") # Example

    # Celery Worker Settings
    CELERY_RESULT_BACKEND: str | None = None # Construct from Redis settings if using Redis as backend

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Construct URLs if needed
    if not settings.REDIS_URL:
         password = f":{settings.REDIS_PASSWORD}" if settings.REDIS_PASSWORD else ""
         settings.REDIS_URL = f"redis://{password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

    if not settings.CELERY_BROKER_URL:
        user_pass = f"{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}@" if settings.RABBITMQ_USER and settings.RABBITMQ_PASSWORD else ""
        settings.CELERY_BROKER_URL = f"amqp://{user_pass}{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}{settings.RABBITMQ_VHOST}"

    # Use Redis as the result backend by default
    if not settings.CELERY_RESULT_BACKEND:
        settings.CELERY_RESULT_BACKEND = settings.REDIS_URL

    return settings

settings = get_settings()

# Example usage: print(settings.REDIS_HOST)
