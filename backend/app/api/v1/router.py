from fastapi import APIRouter
from . import auth, availability, calendar, events, requests, share

api_router = APIRouter()
api_router.include_router(auth.me_router, tags=["auth"])
api_router.include_router(requests.router, prefix="/requests", tags=["requests"])
api_router.include_router(share.router, prefix="/share", tags=["share"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(availability.router, tags=["availability"])
