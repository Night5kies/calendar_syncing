from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "local"
    database_url: Optional[str] = None
    local_database_url: str = "postgresql+psycopg://app:app@127.0.0.1:5432/app"
    use_local_database_in_dev: bool = True
    database_url_direct: Optional[str] = None
    redis_url: Optional[str] = None
    local_redis_url: str = "redis://127.0.0.1:6379/0"
    use_local_redis_in_dev: bool = True
    supabase_jwt_secret: str = "local-dev-secret"
    supabase_jwt_alg: str = "HS256"
    allow_dev_auth: bool = True
    dev_user_id: str = "11111111-1111-1111-1111-111111111111"
    dev_user_email: str = "local-organizer@syzy.dev"
    app_base_url: str = "http://127.0.0.1:3000"
    api_base_url: str = "http://127.0.0.1:8000"
    reminder_sweep_interval_minutes: int = 15
    share_link_ttl_days: int = 30
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
    google_oauth_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"
    google_oauth_userinfo_url: str = "https://www.googleapis.com/oauth2/v3/userinfo"
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://127.0.0.1:8000/v1/calendar/google/callback"
    google_oauth_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/calendar.readonly "
        "https://www.googleapis.com/auth/calendar.events"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            # Playwright e2e boots the Next.js dev server on port 3100
            # (see calendar_syncing_app_web/playwright.config.ts). Without these
            # origins the browser-side fetches in the e2e suite are CORS-blocked.
            "http://localhost:3100",
            "http://127.0.0.1:3100",
        ]
    )

    class Config:
        env_file = ".env"

    @property
    def effective_database_url(self) -> str:
        if self.env == "local" and self.use_local_database_in_dev:
            return self.local_database_url
        if self.database_url:
            return self.database_url
        raise ValueError("DATABASE_URL must be set when local database override is disabled")

    @property
    def effective_redis_url(self) -> str:
        if self.env == "local" and self.use_local_redis_in_dev:
            return self.local_redis_url
        if self.redis_url:
            return self.redis_url
        raise ValueError("REDIS_URL must be set when local redis override is disabled")


settings = Settings()  # type: ignore
