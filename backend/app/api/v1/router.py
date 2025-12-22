from fastapi import APIRouter
from . import auth, requests, share

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(auth.me_router, tags=["auth"])
api_router.include_router(requests.router, prefix="/requests", tags=["requests"])
api_router.include_router(share.router, prefix="/share", tags=["share"])
