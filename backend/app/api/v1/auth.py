import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.deps import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserLogin

router = APIRouter()
me_router = APIRouter()


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


@me_router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return {"id": str(current_user.id), "email": current_user.email}
