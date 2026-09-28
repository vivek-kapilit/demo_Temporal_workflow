"""FastAPI application.

    uvicorn app.main:app --reload --port 8000

FastAPI is only the front door: it connects a Temporal Client on startup and
exposes REST endpoints for the React app. It never runs payment steps itself.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import temporal_client
from app.api.payments import router
from app.config import FRONTEND_ORIGIN, TEMPORAL_ADDRESS
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await temporal_client.connect()
    yield


app = FastAPI(title="Temporal Payment POC", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "temporal": TEMPORAL_ADDRESS}
