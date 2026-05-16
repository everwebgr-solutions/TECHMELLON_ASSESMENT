"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import Base, engine
from api.models import Booking, Flight  # noqa: F401 — register models with Base
from api.routes import bookings, flights, knowledge, webhooks

app = FastAPI(
    title="Sky Airways API",
    description="Booking and knowledge base API for the Sky Airways voice AI agent.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup (idempotent — use migrations for schema changes)
Base.metadata.create_all(bind=engine)

app.include_router(flights.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "sky-airways-api"}
