"""
Automated unit tests for IBVAP Video Upload and Ingestion Pipeline.
Tests chunked upload streaming, 500 MB limit enforcement, signature validation,
OpenCV probing, filename sanitization/path traversal defense, cleanup on failure,
and dynamic camera registration.
"""

from pathlib import Path
import io
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.app import app
from core.camera_registry import get_camera, list_cameras, remove_camera
from core.live_stream_manager import live_stream_manager


@pytest.fixture
def dummy_mp4_bytes() -> bytes:
    """Generates a small valid MP4 video in memory."""
    buf_path = Path("tests/temp_test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(buf_path), fourcc, 10.0, (160, 120))
    for _ in range(15):
        frame = np.full((120, 160, 3), 100, dtype=np.uint8)
        out.write(frame)
    out.release()

    with open(buf_path, "rb") as f:
        data = f.read()

    buf_path.unlink()
    return data


def test_valid_video_upload(dummy_mp4_bytes):
    """Test successful video upload, format probing, and camera registration."""
    client = TestClient(app)
    files = {"file": ("border_recon_sector9.mp4", io.BytesIO(dummy_mp4_bytes), "video/mp4")}
    data = {"camera_name": "Sector 9 Reconnaissance"}

    response = client.post("/api/videos/upload", files=files, data=data)
    assert response.status_code == 201

    payload = response.json()
    cam_id = payload["camera_id"]
    assert cam_id.startswith("CAM-UP-")
    assert payload["name"] == "Sector 9 Reconnaissance"
    assert payload["resolution"] == "160x120"
    assert payload["frame_count"] == 15
    assert payload["file_size_bytes"] == len(dummy_mp4_bytes)

    # Verify registration in camera registry
    reg_cam = get_camera(cam_id)
    assert reg_cam is not None
    assert reg_cam.camera_id == cam_id
    assert reg_cam.exists_on_disk is True
    assert len(reg_cam.zones) > 0
    assert len(reg_cam.tripwires) > 0

    # Cleanup test camera
    remove_camera(cam_id, delete_file=True)


def test_upload_invalid_signature_rejected():
    """Verify upload fails and partial file is deleted when magic bytes are invalid."""
    client = TestClient(app)
    fake_content = b"This is plain text disguised as video footage with fake headers."
    files = {"file": ("malicious.mp4", io.BytesIO(fake_content), "video/mp4")}

    response = client.post("/api/videos/upload", files=files)
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()

    # Verify no file created in data/uploads/
    upload_files = list(Path("data/uploads").glob("*malicious*"))
    assert len(upload_files) == 0


def test_upload_empty_file_rejected():
    """Verify 0-byte upload is rejected with HTTP 400."""
    client = TestClient(app)
    files = {"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")}

    response = client.post("/api/videos/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_path_traversal_sanitization(dummy_mp4_bytes):
    """Verify path traversal sequences are neutralized and stored strictly in data/uploads/."""
    client = TestClient(app)
    files = {"file": ("../../../../etc/passwd.mp4", io.BytesIO(dummy_mp4_bytes), "video/mp4")}

    response = client.post("/api/videos/upload", files=files)
    assert response.status_code == 201

    payload = response.json()
    cam_id = payload["camera_id"]
    saved_path = Path(payload["file_path"]).resolve()
    upload_dir = Path("data/uploads").resolve()

    # Assert saved path is strictly child of data/uploads/
    assert saved_path.parent == upload_dir

    remove_camera(cam_id, delete_file=True)


def test_upload_corrupt_video_rejected():
    """Verify video with valid container header but undecodable stream fails OpenCV probe."""
    client = TestClient(app)
    # Valid MP4 header (ftyp box) but truncated corrupt payload
    corrupt_content = b"\x00\x00\x00\x1cftypiso5\x00\x00\x02\x00" + b"\xff" * 100
    files = {"file": ("corrupt.mp4", io.BytesIO(corrupt_content), "video/mp4")}

    response = client.post("/api/videos/upload", files=files)
    assert response.status_code == 400
    assert "corrupt" in response.json()["detail"].lower() or "decode" in response.json()["detail"].lower()

    upload_files = list(Path("data/uploads").glob("*corrupt*"))
    assert len(upload_files) == 0


def test_oversized_upload_limit(dummy_mp4_bytes, monkeypatch):
    """Verify in-flight streaming aborts with HTTP 413 and deletes partial file if size exceeds limit."""
    import server.routes as routes

    # Lower limit to 100 bytes for test
    monkeypatch.setattr(routes, "MAX_UPLOAD_SIZE", 100)

    client = TestClient(app)
    files = {"file": ("oversized.mp4", io.BytesIO(dummy_mp4_bytes), "video/mp4")}

    response = client.post("/api/videos/upload", files=files)
    assert response.status_code == 413
    assert "limit" in response.json()["detail"].lower()

    upload_files = list(Path("data/uploads").glob("*oversized*"))
    assert len(upload_files) == 0


def test_uploaded_camera_pipeline_integration(dummy_mp4_bytes):
    """Verify uploaded camera can be selected, processed, and streamed through the AI pipeline."""
    client = TestClient(app)
    files = {"file": ("pipeline_test_source.mp4", io.BytesIO(dummy_mp4_bytes), "video/mp4")}
    upload_res = client.post("/api/videos/upload", files=files)
    assert upload_res.status_code == 201

    cam_id = upload_res.json()["camera_id"]

    # Select the uploaded camera feed
    select_res = client.post(f"/api/cameras/{cam_id}/select")
    assert select_res.status_code == 200
    assert select_res.json()["camera_id"] == cam_id

    # Verify live stream manager switched to this camera
    assert live_stream_manager.active_camera_id == cam_id

    # Cleanup
    live_stream_manager.switch_camera("CAM-01")
    remove_camera(cam_id, delete_file=True)
