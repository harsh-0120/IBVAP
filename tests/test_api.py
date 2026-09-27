"""
Automated unit tests for IBVAP FastAPI Backend REST API.
Uses TestClient with isolated temporary databases to protect the production demo database.
"""

from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.database import IncidentDatabase
from server.routes import get_config, get_database


@pytest.fixture
def client_and_test_db(tmp_path):
    """Provides a TestClient connected to an isolated temporary SQLite database."""
    test_db_file = tmp_path / "test_api_events.db"
    test_db = IncidentDatabase(test_db_file)

    test_snapshot_dir = tmp_path / "snapshots"
    test_snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy JPEG snapshot file
    dummy_snap_file = test_snapshot_dir / "test_snapshot_001.jpg"
    dummy_img = np.full((100, 100, 3), 180, dtype=np.uint8)
    cv2.imwrite(str(dummy_snap_file), dummy_img)

    # Insert sample seed incidents
    inc1 = test_db.create_incident({
        "timestamp": 1788701000.0,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 10,
        "object_type": "person",
        "zone_id": "restricted_alpha",
        "zone_name": "Sector Alpha",
        "direction": None,
        "confidence": 0.92,
        "frame_index": 50,
        "feet_point": [500.0, 300.0],
        "snapshot_path": str(dummy_snap_file),
    })

    inc2 = test_db.create_incident({
        "timestamp": 1788701050.0,
        "camera_id": "CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 15,
        "object_type": "person",
        "zone_id": "wire_bravo",
        "zone_name": "Perimeter Wire",
        "direction": "LEFT_TO_RIGHT",
        "confidence": 0.85,
        "frame_index": 95,
        "feet_point": [800.0, 400.0],
        "snapshot_path": str(dummy_snap_file),
    })

    test_config = {
        "video": {
            "source_type": "file",
            "file_path": "data/sample_videos/border_perimeter_demo.mp4",
            "loop": True,
            "buffer_size": 1,
        },
        "incident": {
            "camera_id": "CAM-01",
            "db_path": str(test_db_file),
            "snapshot_dir": str(test_snapshot_dir),
            "jpeg_quality": 90,
        },
        "spatial": {
            "enabled": True,
            "cooldown_sec": 5.0,
            "zones": [
                {
                    "id": "zone_1",
                    "name": "Restricted Zone 1",
                    "points": [[100, 100], [500, 100], [500, 500], [100, 500]],
                }
            ],
            "tripwires": [
                {
                    "id": "wire_1",
                    "name": "Border Wire 1",
                    "start": [400, 100],
                    "end": [400, 600],
                }
            ],
        },
    }

    # Override dependencies
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_config] = lambda: test_config

    client = TestClient(app)
    yield client, test_db, inc1.id, inc2.id, dummy_snap_file

    # Clean up overrides
    app.dependency_overrides.clear()


def test_health_endpoint(client_and_test_db):
    """1. Test GET /api/health endpoint."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "IBVAP"
    assert "version" in data


def test_events_endpoint(client_and_test_db):
    """2. Test GET /api/events list endpoint."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/events?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["incidents"]) == 2
    assert data["incidents"][0]["event_type"] in ["ZONE_INTRUSION", "TRIPWIRE_CROSSING"]


def test_event_retrieval_by_id(client_and_test_db):
    """3. Test GET /api/events/{id} retrieval."""
    client, _, inc1_id, _, _ = client_and_test_db
    response = client.get(f"/api/events/{inc1_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == inc1_id
    assert data["camera_id"] == "CAM-01"
    assert data["event_type"] == "ZONE_INTRUSION"
    assert data["track_id"] == 10
    assert data["confidence"] == 0.92


def test_event_not_found_404(client_and_test_db):
    """4. Test GET /api/events/{id} with non-existent ID."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/events/999999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_statistics_endpoint(client_and_test_db):
    """5. Test GET /api/stats endpoint."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_incidents"] == 2
    assert data["zone_intrusions"] == 1
    assert data["tripwire_crossings"] == 1
    assert data["camera_id"] == "CAM-01"
    assert data["active_camera_count"] == 1


def test_cameras_endpoint(client_and_test_db):
    """6. Test GET /api/cameras endpoint."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/cameras")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["camera_id"] == "CAM-01"
    assert data[0]["source_type"] == "file"
    assert data[0]["status"] in ["online", "offline"]


def test_zones_endpoint(client_and_test_db):
    """7. Test GET /api/zones and POST /api/zones endpoints."""
    client, _, _, _, _ = client_and_test_db

    # GET
    res_get = client.get("/api/zones")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert len(data_get["zones"]) == 1
    assert len(data_get["tripwires"]) == 1
    assert data_get["zones"][0]["id"] == "zone_1"

    # POST new polygon zone
    new_zone = {
        "id": "new_zone_alpha",
        "name": "New Alpha Sector",
        "type": "polygon",
        "points": [[200, 200], [600, 200], [600, 600], [200, 600]],
    }
    res_post = client.post("/api/zones", json=new_zone)
    assert res_post.status_code == 201
    data_post = res_post.json()
    zone_ids = [z["id"] for z in data_post["zones"]]
    assert "new_zone_alpha" in zone_ids


def test_snapshot_download_endpoint(client_and_test_db):
    """8. Test GET /api/events/{id}/snapshot download."""
    client, _, inc1_id, _, _ = client_and_test_db
    response = client.get(f"/api/events/{inc1_id}/snapshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0


def test_invalid_parameters_handling(client_and_test_db):
    """9. Test input validation and error responses for malformed query parameters."""
    client, _, _, _, _ = client_and_test_db

    # Limit must be >= 1
    res_bad_limit = client.get("/api/events?limit=0")
    assert res_bad_limit.status_code == 422

    # Negative event ID
    res_bad_id = client.get("/api/events/-5")
    assert res_bad_id.status_code in [400, 422]


def test_api_openapi_and_docs_schemas(client_and_test_db):
    """10. Test OpenAPI schema accessibility and compliance."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi = response.json()
    assert "paths" in openapi
    assert "/api/health" in openapi["paths"]
    assert "/api/events" in openapi["paths"]
    assert "/api/stats" in openapi["paths"]
    assert "/api/cameras" in openapi["paths"]
    assert "/api/zones" in openapi["paths"]
    assert "/api/video/demo" in openapi["paths"]
    assert "/api/video/annotated" in openapi["paths"]


def test_video_demo_endpoint(client_and_test_db):
    """11. Test demo surveillance video endpoint returns valid mp4 stream."""
    client, _, _, _, _ = client_and_test_db
    response = client.get("/api/video/demo")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert int(response.headers["content-length"]) > 1000000


def test_video_annotated_endpoint(client_and_test_db, monkeypatch):
    """12. Test annotated MJPEG surveillance video endpoint returns valid multipart stream."""
    client, _, _, _, _ = client_and_test_db

    # In unit tests, monkeypatch stream_mjpeg to yield a finite sequence of valid MJPEG frames
    # so StreamingResponse cleanly finishes and TestClient does not deadlock waiting for an infinite generator.
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"

    def mock_stream_mjpeg(self):
        for _ in range(3):
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(dummy_jpeg)).encode("ascii") + b"\r\n\r\n"
                + dummy_jpeg + b"\r\n"
            )

    monkeypatch.setattr(
        "core.video_pipeline.AnnotatedVideoPipeline.__init__",
        lambda self, *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "core.video_pipeline.AnnotatedVideoPipeline.stream_mjpeg",
        mock_stream_mjpeg,
    )

    with client.stream("GET", "/api/video/annotated") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]
        chunks = list(response.iter_bytes())
        assert len(chunks) >= 1
        combined = b"".join(chunks)
        assert b"--frame" in combined
        assert b"\xff\xd8" in combined

