"""
IBVAP FastAPI Application
Command & Control REST API server for border surveillance analytics.
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import yaml

from server.database import IncidentDatabase
from server.routes import router, ws_router

logger = logging.getLogger("ibvap.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager initializing DB and configuration."""
    cfg_path = Path("config/default_config.yaml")
    config: Dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    app.state.config = config

    # Check DATABASE_URL environment variable first, then fallback to config/default_config.yaml
    db_env = os.environ.get("DATABASE_URL")
    if db_env and db_env.strip():
        db_source = db_env.strip()
    else:
        db_source = config.get("incident", {}).get("db_path", "data/events.db")

    app.state.db = IncidentDatabase(db_source)
    logger.info("IBVAP FastAPI application initialized database connection.")

    yield

    logger.info("IBVAP FastAPI application shutting down.")


app = FastAPI(
    title="IBVAP — Intelligent Border Video Analytics Platform API",
    description="Software-defined surveillance intelligence platform REST API for SIH 2026 Problem Statement 26187.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------
# Configurable CORS Configuration (supporting Vercel + Local Development)
# --------------------------------------------------------------------------
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ibvap-zeta.vercel.app",
    "https://ibvap.vercel.app",
]

cors_env = os.environ.get("CORS_ORIGINS", "")
if cors_env.strip():
    configured_origins = [o.strip().rstrip("/") for o in cors_env.split(",") if o.strip()]
    origins = list(dict.fromkeys(DEFAULT_CORS_ORIGINS + configured_origins))
else:
    origins = list(DEFAULT_CORS_ORIGINS)

# Strictly exclude wildcard "*" to comply with W3C CORS specifications when allow_credentials=True
origins = [o for o in origins if o != "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https:\/\/ibvap[a-zA-Z0-9_\-]*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API endpoints and WebSocket endpoints
app.include_router(router)
app.include_router(ws_router)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root access to interactive API documentation."""
    return RedirectResponse(url="/docs")
