from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    env: str = "local"
    database_url: str
    database_url_direct: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev"
    jwt_alg: str = "HS256"
    access_token_minutes: int = 30

    class Config:
        env_file = ".env"


settings = Settings()  # type: ignore
