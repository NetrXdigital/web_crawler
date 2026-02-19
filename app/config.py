from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "dev"
    DATABASE_URL: str
    REDIS_URL: str
    LOG_LEVEL: str = "INFO"
    CRAWLER_LOG_LEVEL: str = "DEBUG"

    MAX_PAGES: int = 5000
    MAX_DEPTH: int = 5
    MAX_MINUTES: int = 60
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3540
    CELERY_TASK_TIME_LIMIT: int = 3600

    RENDER_MODE: str = "hybrid"  # hybrid | http | browser
    INCLUDE_SUBDOMAINS: bool = True
    USER_AGENT: str = "NetrXAuditBot/1.0"
    BROWSER_TIMEOUT_MS: int = 15000

settings = Settings()
