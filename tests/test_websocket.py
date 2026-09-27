"""
Tests for IBVAP Real-time WebSocket Event Stream (Milestone 6B).
Validates connection lifecycle, initial handshake, heartbeat ping/pong,
real-time incident broadcast, multi-client distribution, and dead connection pruning.
"""

import asyncio
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
import numpy as np

from core.incident_manager import IncidentConfig, IncidentManager, IncidentRecord
from core.spatial_engine import SpatialEvent, SpatialEventType, CrossingDirection
from core.tracker import BoundingBox, Track
from server.app import app
from server.database import IncidentDatabase
from server.routes import get_config, get_database
from server.schemas import RealtimeEvent
from server.websocket_manager import WebSocketManager, ws_manager


@pytest.fixture
def test_db_setup(tmp_path):
    """Fixture providing an isolated SQLite database and its path."""
    db_file = tmp_path / "test_events.db"
    db = IncidentDatabase(str(db_file))
    return db, str(db_file)


@pytest.fixture
def client(test_db_setup, tmp_path):
    """Fixture providing a TestClient with overridden isolated DB and snapshot dirs."""
    test_db, db_path = test_db_setup
    test_snapshots = tmp_path / "snapshots"
    test_snapshots.mkdir()

    test_cfg: Dict[str, Any] = {
        "video": {"source_type": "file", "file_path": "data/sample_videos/border_perimeter_demo.mp4"},
        "incident": {
            "camera_id": "TEST-CAM-01",
            "db_path": db_path,
            "snapshot_dir": str(test_snapshots),
            "jpeg_quality": 85,
        },
        "spatial": {
            "zones": [{"id": "Z1", "name": "Restricted Sector A", "points": [[0, 0], [100, 0], [100, 100], [0, 100]]}],
            "tripwires": [{"id": "TW1", "name": "Outer Perimeter", "start": [0, 50], "end": [200, 50]}],
        },
    }

    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_config] = lambda: test_cfg
    app.state.db = test_db
    app.state.config = test_cfg

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_websocket_handshake(client):
    """Verify that connecting to /ws/events receives the initial CONNECTED handshake."""
    with client.websocket_connect("/ws/events") as websocket:
        data = websocket.receive_json()
        assert data["message_type"] == "CONNECTED"
        assert data["service"] == "IBVAP"
        assert data["active_clients"] >= 1


def test_websocket_ping_pong(client):
    """Verify heartbeat ping/pong protocol."""
    with client.websocket_connect("/ws/events") as websocket:
        handshake = websocket.receive_json()
        assert handshake["message_type"] == "CONNECTED"

        websocket.send_text("ping")
        response = websocket.receive_text()
        assert response == "pong"


def test_websocket_single_client_broadcast(client):
    """Verify broadcasting an incident to a single connected client."""
    sample_payload = {
        "message_type": "NEW_INCIDENT",
        "id": 101,
        "timestamp": 1725624000.0,
        "iso_timestamp": "2026-09-06T12:00:00.000000Z",
        "camera_id": "TEST-CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 42,
        "object_type": "person",
        "zone_id": "ZONE-01",
        "zone_name": "Test Zone",
        "direction": None,
        "confidence": 0.88,
        "frame_index": 120,
        "feet_point": [320.0, 480.0],
        "snapshot_path": "data/snapshots/test.jpg",
    }

    with client.websocket_connect("/ws/events") as websocket:
        _ = websocket.receive_json()

        ws_manager.broadcast_sync(sample_payload)

        received = websocket.receive_json()
        assert received["message_type"] == "NEW_INCIDENT"
        assert received["id"] == 101
        assert received["event_type"] == "ZONE_INTRUSION"
        assert received["track_id"] == 42
        assert received["camera_id"] == "TEST-CAM-01"
        assert received["confidence"] == 0.88

        validated_event = RealtimeEvent(**received)
        assert validated_event.id == 101
        assert validated_event.event_type == "ZONE_INTRUSION"


def test_websocket_multi_client_broadcast(client):
    """Verify concurrent broadcast delivery across multiple connected WebSocket clients."""
    sample_payload = {
        "message_type": "NEW_INCIDENT",
        "id": 202,
        "timestamp": 1725624050.0,
        "iso_timestamp": "2026-09-06T12:00:50.000000Z",
        "camera_id": "TEST-CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 7,
        "object_type": "person",
        "zone_id": "TW-01",
        "zone_name": "Perimeter Wire",
        "direction": "LEFT_TO_RIGHT",
        "confidence": 0.94,
        "frame_index": 250,
        "feet_point": [500.0, 350.0],
        "snapshot_path": "data/snapshots/tripwire.jpg",
    }

    with client.websocket_connect("/ws/events") as ws1:
        _ = ws1.receive_json()
        with client.websocket_connect("/ws/events") as ws2:
            _ = ws2.receive_json()

            ws_manager.broadcast_sync(sample_payload)

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["id"] == 202
            assert msg2["id"] == 202
            assert msg1["event_type"] == "TRIPWIRE_CROSSING"
            assert msg2["event_type"] == "TRIPWIRE_CROSSING"
            assert msg1["direction"] == "LEFT_TO_RIGHT"
            assert msg2["direction"] == "LEFT_TO_RIGHT"


def test_websocket_client_disconnect_cleanup(client):
    """Verify that disconnecting client safely decrements active count."""
    initial_count = ws_manager.active_count

    with client.websocket_connect("/ws/events") as ws:
        _ = ws.receive_json()
        assert ws_manager.active_count == initial_count + 1

    assert ws_manager.active_count == initial_count


def test_websocket_manager_prunes_dead_connection():
    """Unit test: Verify that WebSocketManager gracefully handles and prunes broken connections."""
    manager = WebSocketManager()

    good_client = AsyncMock()
    good_client.send_json = AsyncMock()

    bad_client = AsyncMock()
    bad_client.send_json = AsyncMock(side_effect=RuntimeError("Socket closed unexpectedly"))

    manager._active_connections.add(good_client)
    manager._active_connections.add(bad_client)
    assert manager.active_count == 2

    delivered = asyncio.run(manager.broadcast_json({"test": "data"}))

    assert delivered == 1
    assert manager.active_count == 1
    assert good_client in manager._active_connections
    assert bad_client not in manager._active_connections


def test_incident_manager_callback_integration(tmp_path, test_db_setup):
    """Verify IncidentManager properly triggers on_incident callback upon breach."""
    test_db, db_path = test_db_setup
    received_incidents = []

    def incident_callback(record: IncidentRecord):
        received_incidents.append(record)

    cfg = IncidentConfig(
        camera_id="CAM-CB",
        db_path=db_path,
        snapshot_dir=str(tmp_path / "cb_snapshots"),
    )
    manager = IncidentManager(config=cfg, database=test_db, on_incident=incident_callback)

    event = SpatialEvent(
        event_type=SpatialEventType.ZONE_INTRUSION,
        track_id=15,
        object_type="person",
        zone_id="ZONE-ALPHA",
        zone_name="Restricted Bunker",
        direction=None,
        timestamp=1725624500.0,
        frame_index=99,
        feet_point=(150.0, 300.0),
    )
    track = Track(
        track_id=15,
        class_id=0,
        class_name="person",
        confidence=0.91,
        bbox=BoundingBox(100.0, 150.0, 200.0, 300.0),
        frame_index=99,
        timestamp=1725624500.0,
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    rec = manager.process_event(event=event, frame=frame, track=track)

    assert len(received_incidents) == 1
    assert received_incidents[0].id == rec.id
    assert received_incidents[0].track_id == 15
    assert received_incidents[0].zone_id == "ZONE-ALPHA"


def test_api_routes_and_websocket_coexistence(client):
    """Verify that both REST endpoints and WebSocket endpoints function concurrently."""
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "online"

    stats_resp = client.get("/api/stats")
    assert stats_resp.status_code == 200

    with client.websocket_connect("/ws/events") as ws:
        handshake = ws.receive_json()
        assert handshake["message_type"] == "CONNECTED"
