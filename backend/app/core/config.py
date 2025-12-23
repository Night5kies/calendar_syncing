from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    env: str = "local"
    database_url: str
    database_url_direct: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    supabase_jwt_secret: str
    supabase_jwt_alg: str = "HS256"

    class Config:
        env_file = ".env"


settings = Settings()  # type: ignore
