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
    app_base_url: str = "http://127.0.0.1:3000"
    api_base_url: str = "http://127.0.0.1:8000"
    notification_mode: str = "file"
    notification_from_email: str = "noreply@syzy.dev"
    notification_outbox_dir: str = "dev_outbox"
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    google_api_base_url: str = "https://www.googleapis.com/calendar/v3"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    class Config:
        env_file = ".env"


settings = Settings()  # type: ignore
