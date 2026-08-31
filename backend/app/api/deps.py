import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings
from app.core.security import decode_supabase_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    email: str | None
    email_verified: bool = False


def _from_payload(payload: dict) -> CurrentUser:
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    email = payload.get("email")
    email_verified = bool(
        payload.get("email_verified")
        or payload.get("user_metadata", {}).get("email_verified")
    )
    return CurrentUser(user_id=user_id, email=email, email_verified=email_verified)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> CurrentUser:
    if not credentials:
        if settings.env == "local" and settings.allow_dev_auth:
            return CurrentUser(
                user_id=uuid.UUID(settings.dev_user_id),
                email=settings.dev_user_email,
                email_verified=True,
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    payload = decode_supabase_token(token)
    return _from_payload(payload)


def require_verified_organizer(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "organizer_email_unverified",
                "message": (
                    "Verify your email before publishing, sharing, sending reminders, "
                    "or finalizing this event."
                ),
            },
        )
    return current_user
