from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_alg: str = "HS256"
    access_token_minutes: int = 30

    class Config:
        env_file = ".env"

settings = Settings()  # type: ignore
