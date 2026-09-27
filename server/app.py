"""
IBVAP FastAPI Application
Command & Control REST API server for border surveillance analytics.
"""

from contextlib import asynccontextmanager
import logging
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
    db_path = config.get("incident", {}).get("db_path", "data/events.db")
    app.state.db = IncidentDatabase(db_path)
    logger.info(f"IBVAP FastAPI application initialized with database: {db_path}")

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
# Development CORS Configuration (allowing local dashboard development)
# --------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "*",
    ],
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
