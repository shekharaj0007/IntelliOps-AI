from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"


def default_sqlite_url() -> str:
    path = (DATA_DIR / "intelliops.db").resolve()
    return "sqlite:///" + path.as_posix()


DATABASE_URL = os.getenv("DATABASE_URL", default_sqlite_url())
JWT_SECRET = os.getenv("JWT_SECRET", "intelliops-local-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 12)))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

DEMO_EMAIL = "operator@intelliops.ai"
DEMO_PASSWORD = "operator123"
DEMO_NAME = "Operator"
