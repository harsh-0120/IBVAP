"""
Automated unit tests for IBVAP Surveillance Analytics aggregation and API endpoint.
Tests time bucketing (24h, 7d, all), UTC alignment, severity mapping, mathematical consistency,
empty database handling, and parameter validation.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.database import IncidentDatabase
from server.routes import get_database


@pytest.fixture
def test_db_instance(tmp_path: Path):
    """Provides an isolated SQLite IncidentDatabase instance in a temp directory."""
    db_file = tmp_path / "test_analytics.db"
    return IncidentDatabase(db_file)


@pytest.fixture
def client_with_db(test_db_instance):
    """Provides a TestClient with dependency override for get_database."""
    app.dependency_overrides[get_database] = lambda: test_db_instance
    client = TestClient(app)
    yield client, test_db_instance
    app.dependency_overrides.clear()


def test_empty_database_analytics(test_db_instance):
    """Test that querying an empty database returns zeroed metrics and valid buckets without error."""
    now_dt = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    now_ts = now_dt.timestamp()

    # 24h empty
    res_24h = test_db_instance.get_analytics_summary(time_range="24h", now_ts=now_ts)
    assert res_24h["total_incidents"] == 0
    assert len(res_24h["incidents_over_time"]) == 24
    assert all(b["count"] == 0 for b in res_24h["incidents_over_time"])
    assert res_24h["incidents_by_severity"] == {"critical": 0, "warning": 0}
    assert res_24h["incidents_by_type"] == {"ZONE_INTRUSION": 0, "TRIPWIRE_CROSSING": 0}
    assert res_24h["incidents_by_camera"] == {}

    # 7d empty
    res_7d = test_db_instance.get_analytics_summary(time_range="7d", now_ts=now_ts)
    assert res_7d["total_incidents"] == 0
    assert len(res_7d["incidents_over_time"]) == 7
    assert all(b["count"] == 0 for b in res_7d["incidents_over_time"])

    # all empty
    res_all = test_db_instance.get_analytics_summary(time_range="all", now_ts=now_ts)
    assert res_all["total_incidents"] == 0
    assert len(res_all["incidents_over_time"]) == 7
    assert all(b["count"] == 0 for b in res_all["incidents_over_time"])


def test_24h_bucketing_and_math(test_db_instance):
    """Test 24h hourly bucketing mathematics, boundary filtering, and severity split."""
    now_dt = datetime(2026, 9, 27, 15, 30, 0, tzinfo=timezone.utc)
    now_ts = now_dt.timestamp()

    # Inside:
    # 1. 30 mins ago -> ZONE_INTRUSION
    test_db_instance.create_incident({
        "timestamp": now_ts - 30 * 60,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 1,
        "zone_id": "z1",
        "zone_name": "Sector A",
        "frame_index": 10,
        "feet_point": [100.0, 100.0],
        "snapshot_path": "dummy.jpg",
    })
    # 2. 2 hours ago -> TRIPWIRE_CROSSING
    test_db_instance.create_incident({
        "timestamp": now_ts - 2 * 3600,
        "camera_id": "CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 2,
        "zone_id": "t1",
        "zone_name": "Wire Alpha",
        "frame_index": 20,
        "feet_point": [150.0, 150.0],
        "snapshot_path": "dummy.jpg",
    })
    # 3. 22 hours ago -> ZONE_INTRUSION on CAM-02
    test_db_instance.create_incident({
        "timestamp": now_ts - 22 * 3600,
        "camera_id": "CAM-02",
        "event_type": "ZONE_INTRUSION",
        "track_id": 3,
        "zone_id": "z2",
        "zone_name": "Sector B",
        "frame_index": 30,
        "feet_point": [200.0, 200.0],
        "snapshot_path": "dummy.jpg",
    })
    # Outside: 26 hours ago -> should NOT be counted in 24h
    test_db_instance.create_incident({
        "timestamp": now_ts - 26 * 3600,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 4,
        "zone_id": "z1",
        "zone_name": "Sector A",
        "frame_index": 40,
        "feet_point": [100.0, 100.0],
        "snapshot_path": "dummy.jpg",
    })

    res = test_db_instance.get_analytics_summary(time_range="24h", now_ts=now_ts)
    assert res["total_incidents"] == 3
    assert len(res["incidents_over_time"]) == 24

    bucket_sum = sum(b["count"] for b in res["incidents_over_time"])
    assert bucket_sum == res["total_incidents"] == 3

    assert res["incidents_by_severity"]["critical"] == 2
    assert res["incidents_by_severity"]["warning"] == 1
    assert (
        res["incidents_by_severity"]["critical"] + res["incidents_by_severity"]["warning"]
        == res["total_incidents"]
    )

    assert res["incidents_by_camera"]["CAM-01"] == 2
    assert res["incidents_by_camera"]["CAM-02"] == 1


def test_7d_bucketing_and_severity_mapping(test_db_instance):
    """Test 7d daily bucketing, severity mapping consistency, and camera grouping."""
    now_dt = datetime(2026, 9, 27, 20, 0, 0, tzinfo=timezone.utc)
    now_ts = now_dt.timestamp()

    # Day 0 (today)
    test_db_instance.create_incident({
        "timestamp": now_ts - 3600,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 1,
        "zone_id": "z1",
        "zone_name": "Sector A",
        "frame_index": 1,
        "feet_point": [1.0, 1.0],
        "snapshot_path": "dummy.jpg",
    })
    # Day 2 ago
    test_db_instance.create_incident({
        "timestamp": now_ts - 2 * 86400,
        "camera_id": "CAM-01",
        "event_type": "TRIPWIRE_CROSSING",
        "track_id": 2,
        "zone_id": "t1",
        "zone_name": "Wire B",
        "frame_index": 2,
        "feet_point": [2.0, 2.0],
        "snapshot_path": "dummy.jpg",
    })
    # Day 5 ago
    test_db_instance.create_incident({
        "timestamp": now_ts - 5 * 86400,
        "camera_id": "CAM-03",
        "event_type": "ZONE_INTRUSION",
        "track_id": 3,
        "zone_id": "z3",
        "zone_name": "Sector C",
        "frame_index": 3,
        "feet_point": [3.0, 3.0],
        "snapshot_path": "dummy.jpg",
    })
    # Day 8 ago (outside 7d window)
    test_db_instance.create_incident({
        "timestamp": now_ts - 8 * 86400,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 4,
        "zone_id": "z1",
        "zone_name": "Sector A",
        "frame_index": 4,
        "feet_point": [4.0, 4.0],
        "snapshot_path": "dummy.jpg",
    })

    res = test_db_instance.get_analytics_summary(time_range="7d", now_ts=now_ts)
    assert res["total_incidents"] == 3
    assert len(res["incidents_over_time"]) == 7

    bucket_sum = sum(b["count"] for b in res["incidents_over_time"])
    assert bucket_sum == res["total_incidents"] == 3
    assert res["incidents_by_severity"]["critical"] == 2
    assert res["incidents_by_severity"]["warning"] == 1
    assert sum(res["incidents_by_severity"].values()) == 3


def test_all_time_bucketing(test_db_instance):
    """Test all-time span calculation with spanning buckets and complete totals."""
    now_dt = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    now_ts = now_dt.timestamp()

    # Spread incidents across 12 days
    for days_ago in [11, 8, 5, 2, 0]:
        test_db_instance.create_incident({
            "timestamp": now_ts - days_ago * 86400,
            "camera_id": "CAM-01",
            "event_type": "ZONE_INTRUSION" if days_ago % 2 == 0 else "TRIPWIRE_CROSSING",
            "track_id": days_ago + 1,
            "zone_id": f"z_{days_ago}",
            "zone_name": f"Sector {days_ago}",
            "frame_index": days_ago * 10,
            "feet_point": [50.0, 50.0],
            "snapshot_path": "dummy.jpg",
        })

    res = test_db_instance.get_analytics_summary(time_range="all", now_ts=now_ts)
    assert res["total_incidents"] == 5
    assert len(res["incidents_over_time"]) >= 12
    bucket_sum = sum(b["count"] for b in res["incidents_over_time"])
    assert bucket_sum == res["total_incidents"] == 5


def test_api_analytics_endpoint(client_with_db):
    """Test GET /api/analytics HTTP endpoint, query params, and validation."""
    client, db = client_with_db

    now_ts = datetime.now(timezone.utc).timestamp()
    db.create_incident({
        "timestamp": now_ts - 100,
        "camera_id": "CAM-01",
        "event_type": "ZONE_INTRUSION",
        "track_id": 99,
        "zone_id": "zone_perimeter",
        "zone_name": "Perimeter Wall",
        "frame_index": 1,
        "feet_point": [120.0, 340.0],
        "snapshot_path": "snap.jpg",
    })

    # Test valid ranges
    for tr in ["24h", "7d", "all"]:
        response = client.get(f"/api/analytics?time_range={tr}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["time_range"] == tr
        assert payload["total_incidents"] >= 1
        assert "incidents_over_time" in payload
        assert "incidents_by_type" in payload
        assert "incidents_by_camera" in payload
        assert "incidents_by_severity" in payload
        assert "camera_status_distribution" in payload
        assert "total_cameras" in payload
        assert "online_cameras" in payload

    # Test invalid range triggers HTTP 422
    invalid_resp = client.get("/api/analytics?time_range=invalid_range")
    assert invalid_resp.status_code == 422
