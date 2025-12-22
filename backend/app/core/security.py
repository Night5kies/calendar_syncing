from datetime import datetime, timedelta

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _ensure_bcrypt_limit(plain: str) -> None:
    if len(plain.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password too long (max 72 bytes)",
        )


def hash_password(plain: str) -> str:
    _ensure_bcrypt_limit(plain)
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    _ensure_bcrypt_limit(plain)
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    minutes = settings.access_token_minutes if expires_minutes is None else expires_minutes
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
