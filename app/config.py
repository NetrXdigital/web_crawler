from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "dev"
    DATABASE_URL: str
    REDIS_URL: str

    MAX_PAGES: int = 5000
    MAX_DEPTH: int = 5
    MAX_MINUTES: int = 60

    RENDER_MODE: str = "hybrid"  # hybrid | http | browser
    INCLUDE_SUBDOMAINS: bool = True
    USER_AGENT: str = "NetrXAuditBot/1.0"

settings = Settings()
