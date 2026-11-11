from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from backend.app.anomaly import model_loaded
from backend.app.config import CORS_ORIGINS, DATA_DIR, DATABASE_URL, MODELS_DIR
from backend.app.database import SessionLocal, engine
from backend.app.models import Anomaly, Base
from backend.app.routers import alerts, anomalies, auth, incidents, overview, services, status
from backend.app.seed import seed_if_empty

log = logging.getLogger("intelliops")
REQUEST_COUNT = 0


def redis_status() -> str:
    url = os.getenv("REDIS_URL")
    if not url:
        return "skipped"
    try:
        import redis  # type: ignore
    except ImportError:
        log.info("REDIS_URL is set but the redis package is not installed; skipping")
        return "skipped"
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=0.2)
        client.ping()
        return "connected"
    except Exception:
        log.info("Redis is not reachable; continuing without it")
        return "skipped"


def database_kind() -> str:
    if DATABASE_URL.startswith("sqlite"):
        return "sqlite"
    return DATABASE_URL.split(":", 1)[0]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    log.info("IntelliOps ready (data_origin=synthetic, redis=%s)", redis_status())
    yield


app = FastAPI(
    title="IntelliOps AI",
    summary="Synthetic IT operations prototype for anomaly detection and incident investigation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def count_requests(request, call_next):
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    return await call_next(request)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_origin": "synthetic",
        "database": database_kind(),
        "redis": redis_status(),
        "model_loaded": model_loaded(),
    }


@app.get("/metrics")
def metrics():
    db = SessionLocal()
    try:
        open_anomalies = (
            db.scalar(select(func.count()).select_from(Anomaly).where(Anomaly.status == "open")) or 0
        )
    finally:
        db.close()
    body = "\n".join(
        [
            "# HELP intelliops_http_requests_total HTTP requests served by this process.",
            "# TYPE intelliops_http_requests_total counter",
            f"intelliops_http_requests_total {REQUEST_COUNT}",
            "# HELP intelliops_open_anomalies Anomalies currently in open status.",
            "# TYPE intelliops_open_anomalies gauge",
            f"intelliops_open_anomalies {int(open_anomalies)}",
            "",
        ]
    )
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")


app.include_router(auth.router)
app.include_router(services.router)
app.include_router(anomalies.router)
app.include_router(incidents.router)
app.include_router(overview.router)
app.include_router(alerts.router)
app.include_router(status.router)
