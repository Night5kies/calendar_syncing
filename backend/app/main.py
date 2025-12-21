from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import engine
from app.api.v1.router import api_router

app = FastAPI(title="Scheduler Backend")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/db-check")
def db_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}

app.include_router(api_router, prefix="/v1")
