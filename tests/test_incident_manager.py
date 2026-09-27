"""
Unit tests for IBVAP Incident Management and SQLite Persistence layer.
Uses temporary isolated databases to guarantee demo database integrity.
"""

from pathlib import Path
import numpy as np
import pytest

from core.detector import BoundingBox
from core.incident_manager import IncidentConfig, IncidentManager, IncidentRecord
from core.spatial_engine import (
    CrossingDirection,
    SpatialEvent,
    SpatialEventType,
)
from core.tracker import Track
from server.database import IncidentDatabase, IncidentModel


@pytest.fixture
def temp_db(tmp_path) -> IncidentDatabase:
    """Provides an isolated temporary SQLite database for testing."""
    db_file = tmp_path / "test_events.db"
    return IncidentDatabase(db_file)


@pytest.fixture
def incident_mgr(tmp_path, temp_db) -> IncidentManager:
    """Provides an isolated IncidentManager with temporary storage."""
    cfg = IncidentConfig(
        camera_id="CAM-TEST-01",
        db_path=str(tmp_path / "test_events.db"),
        snapshot_dir=str(tmp_path / "snapshots"),
        jpeg_quality=85,
    )
    return IncidentManager(config=cfg, database=temp_db)


def test_database_initialization(temp_db):
    """1. Test database schema setup and initial empty count."""
    assert temp_db.count_incidents() == 0
    assert temp_db.count_by_event_type() == {}


def test_incident_insertion(temp_db):
    """2. Test inserting an incident record into SQLite."""
    data = {
        "timestamp": 1788700000.0,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 42,
        "object_type": "person",
        "zone_id": "zone_alpha",
        "zone_name": "Sector Alpha",
        "direction": None,
        "confidence": 0.89,
        "frame_index": 100,
        "feet_point": [500.0, 600.0],
        "snapshot_path": "data/snapshots/test.jpg",
    }
    incident = temp_db.create_incident(data)
    assert incident.id is not None
    assert incident.id > 0
    assert incident.track_id == 42
    assert incident.event_type == "ZONE_INTRUSION"
    assert incident.feet_x == 500.0
    assert incident.feet_y == 600.0
    assert temp_db.count_incidents() == 1


def test_incident_retrieval(temp_db):
    """3. Test retrieving an incident by ID."""
    data = {
        "timestamp": 1788700000.0,
        "camera_id": "CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 99,
        "object_type": "person",
        "zone_id": "wire_1",
        "zone_name": "Border Wire",
        "direction": "LEFT_TO_RIGHT",
        "confidence": 0.95,
        "frame_index": 50,
        "feet_point": [400.0, 300.0],
        "snapshot_path": "data/snapshots/wire.jpg",
    }
    created = temp_db.create_incident(data)
    fetched = temp_db.get_incident_by_id(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.direction == "LEFT_TO_RIGHT"
    assert fetched.confidence == pytest.approx(0.95, 0.001)


def test_incident_serialization(temp_db):
    """4. Test dictionary serialization of database model and IncidentRecord."""
    data = {
        "timestamp": 1788700000.0,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 10,
        "object_type": "person",
        "zone_id": "zone_1",
        "zone_name": "North Fence",
        "direction": None,
        "confidence": 0.88765,
        "frame_index": 20,
        "feet_point": [350.0, 550.0],
        "snapshot_path": "data/snapshots/snap1.jpg",
    }
    rec = temp_db.create_incident(data)
    d = rec.to_dict()

    assert d["id"] == rec.id
    assert d["camera_id"] == "CAM-01"
    assert d["track_id"] == 10
    assert d["feet_point"] == [350.0, 550.0]
    assert d["confidence"] == 0.8877
    assert "iso_timestamp" in d


def test_snapshot_creation(incident_mgr):
    """5. Test physical snapshot image file generation on disk."""
    ev = SpatialEvent(
        event_type=SpatialEventType.ZONE_INTRUSION,
        track_id=15,
        zone_id="zone_test",
        zone_name="Test Restricted Zone",
        object_type="person",
        frame_index=12,
        timestamp=1788700010.0,
        feet_point=(300.0, 400.0),
    )
    frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
    track = Track(
        track_id=15,
        class_id=0,
        class_name="person",
        confidence=0.91,
        bbox=BoundingBox(280, 300, 320, 400),
        frame_index=12,
        timestamp=1788700010.0,
    )

    incident = incident_mgr.process_event(ev, frame, track=track)
    snap_path = Path(incident.snapshot_path)

    assert snap_path.exists()
    assert snap_path.stat().st_size > 0
    assert snap_path.suffix.lower() == ".jpg"
    assert "track-15" in snap_path.name


def test_event_to_incident_conversion(incident_mgr):
    """6. Test SpatialEvent mapping to IncidentRecord and SQLite insertion."""
    ev = SpatialEvent(
        event_type=SpatialEventType.TRIPWIRE_CROSSING,
        track_id=77,
        zone_id="wire_alpha",
        zone_name="Border Tripwire Alpha",
        object_type="person",
        frame_index=88,
        timestamp=1788700050.0,
        feet_point=(600.0, 350.0),
        direction=CrossingDirection.LEFT_TO_RIGHT,
    )
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    inc = incident_mgr.process_event(ev, dummy_frame)
    assert inc.id is not None
    assert inc.camera_id == "CAM-TEST-01"
    assert inc.event_type == "TRIPWIRE_CROSSING"
    assert inc.direction == "LEFT_TO_RIGHT"
    assert inc.track_id == 77
    assert inc.feet_point == (600.0, 350.0)


def test_recent_incident_query(temp_db):
    """7. Test querying recent incidents ordered by descending timestamp."""
    for i in range(5):
        temp_db.create_incident({
            "timestamp": 1000.0 + i * 10,
            "camera_id": "CAM-01",
            "event_type": "ZONE_INTRUSION",
            "track_id": i + 1,
            "object_type": "person",
            "zone_id": "z1",
            "zone_name": "Zone 1",
            "frame_index": i,
            "feet_point": [100.0, 200.0],
            "snapshot_path": f"snap_{i}.jpg",
        })

    recent = temp_db.get_recent_incidents(limit=3)
    assert len(recent) == 3
    # Newest first
    assert recent[0].timestamp == 1040.0
    assert recent[1].timestamp == 1030.0
    assert recent[2].timestamp == 1020.0


def test_event_type_filtering(temp_db):
    """8. Test filtering incidents by event type."""
    # Insert 2 Intrusions and 1 Crossing
    temp_db.create_incident({
        "timestamp": 100.0,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 1,
        "object_type": "person",
        "zone_id": "z1",
        "zone_name": "Zone",
        "frame_index": 1,
        "feet_point": [0, 0],
        "snapshot_path": "s1.jpg",
    })
    temp_db.create_incident({
        "timestamp": 110.0,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 2,
        "object_type": "person",
        "zone_id": "z1",
        "zone_name": "Zone",
        "frame_index": 2,
        "feet_point": [0, 0],
        "snapshot_path": "s2.jpg",
    })
    temp_db.create_incident({
        "timestamp": 120.0,
        "camera_id": "CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 3,
        "object_type": "person",
        "zone_id": "w1",
        "zone_name": "Wire",
        "direction": "RIGHT_TO_LEFT",
        "frame_index": 3,
        "feet_point": [0, 0],
        "snapshot_path": "s3.jpg",
    })

    intrusions = temp_db.get_incidents_by_event_type("ZONE_INTRUSION")
    crossings = temp_db.get_incidents_by_event_type("TRIPWIRE_CROSSING")

    assert len(intrusions) == 2
    assert len(crossings) == 1
    counts = temp_db.count_by_event_type()
    assert counts["ZONE_INTRUSION"] == 2
    assert counts["TRIPWIRE_CROSSING"] == 1


def test_camera_filtering(temp_db):
    """9. Test filtering incidents by camera node ID."""
    temp_db.create_incident({
        "timestamp": 100.0,
        "camera_id": "CAM-ALPHA",
        "event_type": "ZONE_INTRUSION",
        "track_id": 1,
        "object_type": "person",
        "zone_id": "z1",
        "zone_name": "Zone",
        "frame_index": 1,
        "feet_point": [0, 0],
        "snapshot_path": "s1.jpg",
    })
    temp_db.create_incident({
        "timestamp": 105.0,
        "camera_id": "CAM-BETA",
        "event_type": "ZONE_INTRUSION",
        "track_id": 2,
        "object_type": "person",
        "zone_id": "z1",
        "zone_name": "Zone",
        "frame_index": 2,
        "feet_point": [0, 0],
        "snapshot_path": "s2.jpg",
    })

    cam_alpha = temp_db.get_incidents_by_camera("CAM-ALPHA")
    cam_beta = temp_db.get_incidents_by_camera("CAM-BETA")

    assert len(cam_alpha) == 1
    assert len(cam_beta) == 1
    assert cam_alpha[0].track_id == 1
    assert cam_beta[0].track_id == 2


def test_duplicate_prevention_on_single_event(incident_mgr):
    """10. Verify that each confirmed event generates strictly one database row."""
    ev = SpatialEvent(
        event_type=SpatialEventType.ZONE_INTRUSION,
        track_id=88,
        zone_id="z_alpha",
        zone_name="Sector Alpha",
        object_type="person",
        frame_index=10,
        timestamp=1788700000.0,
        feet_point=(400.0, 500.0),
    )
    frame = np.zeros((200, 200, 3), dtype=np.uint8)

    # Calling process_event once
    inc = incident_mgr.process_event(ev, frame)
    assert inc.id is not None
    assert incident_mgr.db.count_incidents() == 1

    # Database only contains 1 incident
    all_incidents = incident_mgr.db.get_recent_incidents()
    assert len(all_incidents) == 1
    assert all_incidents[0].id == inc.id
