"""
Automated unit & integration tests for IBVAP Live AI Video Streaming & Camera Lifecycle.
Validates camera registry, single-pipeline CPU concurrency, camera switching,
live MJPEG streaming endpoint, and clean resource cleanup.
"""

from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from core.camera_registry import DEMO_CAMERAS, get_camera, list_cameras
from core.live_stream_manager import LiveStreamManager, live_stream_manager
from server.app import app
from server.database import IncidentDatabase
from server.routes import get_config, get_database


@pytest.fixture
def client_live(tmp_path):
    """Provides a TestClient with clean isolated database and state."""
    test_db_file = tmp_path / "test_live_events.db"
    test_db = IncidentDatabase(test_db_file)

    app.dependency_overrides[get_database] = lambda: test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_camera_registry_metadata():
    """Verify demo camera registry lists all 3 CCTV sources with valid metadata."""
    cams = list_cameras()
    assert len(cams) == 3
    cam_ids = [c.camera_id for c in cams]
    assert "CAM-01" in cam_ids
    assert "CAM-02" in cam_ids
    assert "CAM-03" in cam_ids

    cam1 = get_camera("CAM-01")
    assert cam1 is not None
    assert cam1.name == "Border Perimeter"
    assert cam1.resolution == "1280x720"
    assert cam1.source_fps == 25.0
    assert len(cam1.zones) >= 1
    assert len(cam1.tripwires) >= 1

    cam2 = get_camera("CAM-02")
    assert cam2 is not None
    assert cam2.name == "Highway Surveillance"
    assert cam2.resolution == "3840x2160"
    assert len(cam2.zones) >= 1

    cam3 = get_camera("CAM-03")
    assert cam3 is not None
    assert cam3.name == "Overhead Traffic"
    assert cam3.resolution == "2160x3840"


def test_get_cameras_endpoint_returns_demo_sources(client_live):
    """Verify GET /api/cameras returns all 3 registered cameras with operational status."""
    response = client_live.get("/api/cameras")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    assert data[0]["camera_id"] == "CAM-01"
    assert data[0]["name"] == "Border Perimeter"
    assert data[0]["status"] in ["online", "ready", "offline"]
    assert "operational_status" in data[0]

    assert data[1]["camera_id"] == "CAM-02"
    assert data[1]["name"] == "Highway Surveillance"

    assert data[2]["camera_id"] == "CAM-03"
    assert data[2]["name"] == "Overhead Traffic"


def test_select_camera_endpoint(client_live):
    """Verify POST /api/cameras/{camera_id}/select activates camera and validates IDs."""
    # Valid camera selection
    res_valid = client_live.post("/api/cameras/CAM-01/select")
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["camera_id"] == "CAM-01"
    assert data["status"] == "online"
    assert data["operational_status"] == "ONLINE / PROCESSING"

    # Invalid camera selection
    res_invalid = client_live.post("/api/cameras/INVALID-CAM-99/select")
    assert res_invalid.status_code == 404
    assert "not registered" in res_invalid.json()["detail"].lower()


def test_live_stream_invalid_camera_returns_404(client_live):
    """Verify GET /api/video/live/{camera_id} with nonexistent ID returns 404."""
    response = client_live.get("/api/video/live/NON_EXISTENT_CAM")
    assert response.status_code == 404


def test_live_stream_mjpeg_frame_generation(client_live, monkeypatch):
    """Verify GET /api/video/live/{camera_id} yields valid multipart MJPEG frames."""
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"

    def mock_subscribe(self, camera_id):
        for _ in range(3):
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + dummy_jpeg
                + b"\r\n"
            )

    monkeypatch.setattr(LiveStreamManager, "subscribe", mock_subscribe)

    with client_live.stream("GET", "/api/video/live/CAM-01") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]
        chunks = list(response.iter_bytes())
        assert len(chunks) >= 1
        combined = b"".join(chunks)
        assert b"--frame" in combined
        assert b"\xff\xd8" in combined


def test_camera_switching_resource_cleanup():
    """Verify that switching cameras stops previous worker and releases resources."""
    manager = LiveStreamManager()
    
    # Check initial state
    assert manager.active_camera_id is None

    # Switch to CAM-01
    started1 = manager.switch_camera("CAM-01")
    assert started1 is True
    assert manager.active_camera_id == "CAM-01"
    assert manager.get_camera_status("CAM-01") == "ONLINE / PROCESSING"
    assert manager.get_camera_status("CAM-02") == "READY"

    # Switch to CAM-02 -> cleanly stops CAM-01 worker
    started2 = manager.switch_camera("CAM-02")
    assert started2 is True
    assert manager.active_camera_id == "CAM-02"
    assert manager.get_camera_status("CAM-02") == "ONLINE / PROCESSING"

    # Clean shutdown
    with manager._lock:
        manager._stop_current_worker_locked()
    assert manager.active_camera_id is None
