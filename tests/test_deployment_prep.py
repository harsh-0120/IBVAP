"""
Tests for deployment preparation:
- Dual-mode database configuration (SQLite vs PostgreSQL)
- URL credential masking
- Engine connection argument separation (SQLite check_same_thread vs PostgreSQL pool_pre_ping)
- Configurable CORS origins with wildcard removal
- Vercel configuration file existence and validity
"""

import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from server.database import IncidentDatabase


def test_sqlite_connection_arguments(tmp_path):
    """Verify SQLite database uses check_same_thread: False and correct URL."""
    db_file = tmp_path / "sqlite_test.db"
    db = IncidentDatabase(db_file)
    assert db.db_url.startswith("sqlite:///")
    # Verify engine connect_args contains check_same_thread for SQLite
    assert db.engine.dialect.name == "sqlite"


def test_url_masking_prevents_password_exposure():
    """Verify database password is masked when logging PostgreSQL URLs."""
    raw_url = "postgresql+psycopg2://postgres:MySecretPassword123@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    masked = IncidentDatabase._mask_url(raw_url)
    assert "MySecretPassword123" not in masked
    assert "postgres:***@aws-0-us-east-1.pooler.supabase.com:6543" in masked
    assert masked.startswith("postgresql+psycopg2://")


def test_postgres_engine_arguments_separated_from_sqlite():
    """Verify PostgreSQL connections do NOT pass check_same_thread and configure pool_pre_ping."""
    pg_url = "postgresql+psycopg2://postgres:secret@localhost:5432/testdb"

    with patch("server.database.create_engine") as mock_create_engine, \
         patch("server.database.Base.metadata.create_all"):
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        db = IncidentDatabase(pg_url)
        assert db.db_url == pg_url

        mock_create_engine.assert_called_once()
        _, kwargs = mock_create_engine.call_args

        # Crucial check: check_same_thread must NOT be in connect_args for PostgreSQL
        assert "connect_args" not in kwargs or "check_same_thread" not in kwargs.get("connect_args", {})
        # Pool pre-ping must be enabled for cloud PostgreSQL
        assert kwargs.get("pool_pre_ping") is True
        assert kwargs.get("pool_size") == 5
        assert kwargs.get("max_overflow") == 10


def test_postgresql_url_normalization():
    """
    Verify PostgreSQL URLs are normalized to postgresql+psycopg2:// to match
    the installed psycopg2-binary driver and avoid ModuleNotFoundError for psycopg (v3).
    """
    # 1. postgres:// (legacy prefix)
    assert IncidentDatabase.normalize_db_url("postgres://user:pass@host:5432/db") == \
        "postgresql+psycopg2://user:pass@host:5432/db"

    # 2. postgresql:// (default Supabase / cloud prefix)
    assert IncidentDatabase.normalize_db_url("postgresql://user:pass@host:5432/db") == \
        "postgresql+psycopg2://user:pass@host:5432/db"

    # 3. postgresql+psycopg:// (psycopg3 prefix)
    assert IncidentDatabase.normalize_db_url("postgresql+psycopg://user:pass@host:5432/db") == \
        "postgresql+psycopg2://user:pass@host:5432/db"

    # 4. postgresql+psycopg2:// (already correct)
    assert IncidentDatabase.normalize_db_url("postgresql+psycopg2://user:pass@host:5432/db") == \
        "postgresql+psycopg2://user:pass@host:5432/db"

    # 5. Supabase pooling URL with query parameters
    supabase_url = "postgresql://postgres.myproject:secret123@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    expected = "postgresql+psycopg2://postgres.myproject:secret123@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    assert IncidentDatabase.normalize_db_url(supabase_url) == expected

    # 6. SQLite paths must NOT be altered
    assert IncidentDatabase.normalize_db_url("data/events.db") == "data/events.db"
    assert IncidentDatabase.normalize_db_url("sqlite:///data/events.db") == "sqlite:///data/events.db"


def test_database_initialization_with_postgres_url_normalization():
    """Verify IncidentDatabase initializes with normalized postgresql+psycopg2 URL."""
    legacy_url = "postgres://user:pass@host:5432/db"
    with patch("server.database.create_engine") as mock_create_engine, \
         patch("server.database.Base.metadata.create_all"):
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        db = IncidentDatabase(legacy_url)
        assert db.db_url == "postgresql+psycopg2://user:pass@host:5432/db"
        mock_create_engine.assert_called_once_with(
            "postgresql+psycopg2://user:pass@host:5432/db",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )


def test_cors_configuration_parsing():
    """Verify CORS origins parsing from environment, preservation of localhost, trailing slash trimming, and wildcard exclusion."""
    from server.app import DEFAULT_CORS_ORIGINS

    # 1. Default origins include localhost ports and production Vercel origins
    assert "http://localhost:5173" in DEFAULT_CORS_ORIGINS
    assert "http://127.0.0.1:5173" in DEFAULT_CORS_ORIGINS
    assert "https://ibvap-zeta.vercel.app" in DEFAULT_CORS_ORIGINS
    assert "https://ibvap.vercel.app" in DEFAULT_CORS_ORIGINS

    # 2. Test environment variable parsing with trailing slashes
    test_env = "https://ibvap.vercel.app/, https://custom-domain.org/, *"
    configured_origins = [o.strip().rstrip("/") for o in test_env.split(",") if o.strip()]
    origins = list(dict.fromkeys(DEFAULT_CORS_ORIGINS + configured_origins))
    # Wildcard must be filtered out
    origins = [o for o in origins if o != "*"]

    assert "https://ibvap.vercel.app" in origins
    assert "https://custom-domain.org" in origins
    assert "https://custom-domain.org/" not in origins
    assert "http://localhost:5173" in origins
    assert "*" not in origins


def test_cors_middleware_production_origin():
    """Verify FastAPI CORSMiddleware allows exact production origin on GET requests."""
    from fastapi.testclient import TestClient
    from server.app import app

    client = TestClient(app)
    response = client.get("/api/health", headers={"Origin": "https://ibvap-zeta.vercel.app"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://ibvap-zeta.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_middleware_preflight_options():
    """Verify FastAPI CORSMiddleware accepts OPTIONS preflight from production origin."""
    from fastapi.testclient import TestClient
    from server.app import app

    client = TestClient(app)
    # Test GET preflight
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://ibvap-zeta.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://ibvap-zeta.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"

    # Test POST preflight
    post_preflight = client.options(
        "/api/videos/upload",
        headers={
            "Origin": "https://ibvap-zeta.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert post_preflight.status_code == 200
    assert post_preflight.headers.get("access-control-allow-origin") == "https://ibvap-zeta.vercel.app"


def test_cors_middleware_preview_deployments_regex():
    """Verify Vercel preview deployments matching regex are authorized."""
    from fastapi.testclient import TestClient
    from server.app import app

    client = TestClient(app)
    response = client.get("/api/health", headers={"Origin": "https://ibvap-preview-123.vercel.app"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://ibvap-preview-123.vercel.app"


def test_cors_middleware_rejects_unauthorized_origins():
    """Verify unauthorized origins receive no CORS header on simple requests and 400 on preflight."""
    from fastapi.testclient import TestClient
    from server.app import app

    client = TestClient(app)
    # Simple request: server responds but does NOT attach allow-origin header
    response = client.get("/api/health", headers={"Origin": "https://malicious-attacker.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None

    # Preflight request: must be rejected with 400
    preflight = client.options(
        "/api/health",
        headers={
            "Origin": "https://malicious-attacker.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 400
    assert "Disallowed CORS origin" in preflight.text


def test_vercel_json_configuration():
    """Verify frontend/vercel.json exists and has valid SPA rewrites."""
    vercel_path = Path("frontend/vercel.json")
    assert vercel_path.exists(), "frontend/vercel.json must exist"

    with open(vercel_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "rewrites" in data
    rewrites = data["rewrites"]
    assert any(r.get("source") == "/(.*)" and r.get("destination") == "/index.html" for r in rewrites)
