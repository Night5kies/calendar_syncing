from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field


class Settings(BaseSettings):
    env: str = "local"
    database_url: str
    database_url_direct: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    supabase_jwt_secret: str
    supabase_jwt_alg: str = "HS256"
    allow_dev_auth: bool = True
    dev_user_id: str = "11111111-1111-1111-1111-111111111111"
    dev_user_email: str = "local-organizer@syzy.dev"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    class Config:
        env_file = ".env"


settings = Settings()  # type: ignore
