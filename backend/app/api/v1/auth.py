from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.deps import get_db
from app.models.profile import Profile

me_router = APIRouter()


@me_router.get("/me")
def me(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    profile = db.get(Profile, current_user.user_id)
    return {
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "profile": {
            "id": str(profile.id),
            "display_name": profile.display_name,
            "timezone": profile.timezone,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        }
        if profile
        else None,
    }
