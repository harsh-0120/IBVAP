"""
Unit tests for IBVAP Multi-Object Tracking (ByteTrack) layer.
"""

import pytest
import numpy as np

from core.detector import BoundingBox, Detection, DetectionResult
from core.tracker import (
    BaseTracker,
    ByteTrackTracker,
    Track,
    TrackingResult,
    TrackerConfig,
)


def test_tracker_initialization():
    """Test tracker instantiation and initial state."""
    config = TrackerConfig(
        track_buffer=20,
        match_thresh=0.75,
        max_trajectory_length=15,
    )
    tracker = ByteTrackTracker(config)

    assert tracker.total_unique_tracks == 0
    assert tracker.config.track_buffer == 20
    assert tracker.config.match_thresh == 0.75
    assert tracker.config.max_trajectory_length == 15


def test_tracker_empty_detections():
    """Test updating tracker with zero detections."""
    tracker = ByteTrackTracker()
    empty_result = DetectionResult(frame_index=1, timestamp=100.0, detections=[])

    track_res = tracker.update(empty_result)
    assert isinstance(track_res, TrackingResult)
    assert track_res.active_count == 0
    assert len(track_res.tracks) == 0
    assert track_res.frame_index == 1


def test_single_person_tracking_structure():
    """Test single person tracking and persistent ID assignment across frames."""
    tracker = ByteTrackTracker()

    # Frame 1: Person at (100, 100, 150, 250)
    det1 = Detection(
        class_id=0,
        class_name="person",
        confidence=0.90,
        bbox=BoundingBox(100.0, 100.0, 150.0, 250.0),
    )
    res1 = tracker.update([det1], frame_index=1, timestamp=100.0)

    assert res1.active_count == 1
    t1 = res1.tracks[0]
    track_id = t1.track_id
    assert track_id > 0
    assert t1.class_name == "person"
    assert t1.feet_point == (125.0, 250.0)
    assert len(t1.trajectory) == 1

    # Frame 2: Same person moved slightly to (103, 101, 153, 251)
    det2 = Detection(
        class_id=0,
        class_name="person",
        confidence=0.88,
        bbox=BoundingBox(103.0, 101.0, 153.0, 251.0),
    )
    res2 = tracker.update([det2], frame_index=2, timestamp=100.033)

    assert res2.active_count == 1
    t2 = res2.tracks[0]
    # Persistent ID must match
    assert t2.track_id == track_id
    assert len(t2.trajectory) == 2


def test_multiple_detections_tracking():
    """Test tracking multiple distinct persons simultaneously."""
    tracker = ByteTrackTracker()

    # Frame 1: Two persons at separate locations
    dets_f1 = [
        Detection(0, "person", 0.92, BoundingBox(50, 100, 100, 250)),
        Detection(0, "person", 0.89, BoundingBox(300, 150, 360, 320)),
    ]
    res1 = tracker.update(dets_f1, frame_index=1, timestamp=1.0)
    assert res1.active_count == 2
    ids_f1 = set(res1.track_ids)
    assert len(ids_f1) == 2

    # Frame 2: Both persons shift slightly
    dets_f2 = [
        Detection(0, "person", 0.91, BoundingBox(52, 101, 102, 251)),
        Detection(0, "person", 0.87, BoundingBox(302, 151, 362, 321)),
    ]
    res2 = tracker.update(dets_f2, frame_index=2, timestamp=1.033)
    assert res2.active_count == 2
    ids_f2 = set(res2.track_ids)

    # Both IDs should persist across frames
    assert ids_f1 == ids_f2


def test_track_result_serialization():
    """Test dictionary serialization of Track and TrackingResult."""
    tracker = ByteTrackTracker()
    det = Detection(0, "person", 0.85, BoundingBox(100, 100, 140, 220))
    res = tracker.update([det], frame_index=10, timestamp=123.45)

    res_dict = res.to_dict()
    assert res_dict["frame_index"] == 10
    assert res_dict["active_count"] == 1
    assert "tracks" in res_dict

    t_dict = res_dict["tracks"][0]
    assert "track_id" in t_dict
    assert "bbox" in t_dict
    assert "center" in t_dict
    assert "feet_point" in t_dict
    assert "trajectory" in t_dict
    assert t_dict["class_name"] == "person"


def test_trajectory_history_accumulation():
    """Test accumulation and length cap of movement trajectories."""
    cfg = TrackerConfig(max_trajectory_length=5)
    tracker = ByteTrackTracker(cfg)

    # Simulate person walking across 8 frames
    for i in range(8):
        det = Detection(
            0,
            "person",
            0.90,
            BoundingBox(100.0 + i * 2, 200.0, 150.0 + i * 2, 350.0),
        )
        res = tracker.update([det], frame_index=i + 1, timestamp=float(i))

    assert res.active_count == 1
    track = res.tracks[0]
    # Length must be capped at max_trajectory_length (5)
    assert len(track.trajectory) == 5
    # The last point must be the newest feet point
    assert track.trajectory[-1] == track.feet_point


def test_track_disappearance_and_cleanup():
    """Test clean handling when a target leaves the scene."""
    cfg = TrackerConfig(track_buffer=5)
    tracker = ByteTrackTracker(cfg)

    # Target present in frames 1-2
    for frame_idx in [1, 2]:
        det = Detection(0, "person", 0.90, BoundingBox(100, 100, 150, 250))
        tracker.update([det], frame_index=frame_idx, timestamp=float(frame_idx))

    assert tracker.total_unique_tracks == 1

    # Target disappears in frames 3-10
    for frame_idx in range(3, 11):
        res = tracker.update([], frame_index=frame_idx, timestamp=float(frame_idx))
        assert res.active_count == 0

    # Total unique tracks recorded remains 1
    assert tracker.total_unique_tracks == 1
    # Internal trajectory for the disappeared track should be cleaned up after track_buffer frames
    assert len(tracker._trajectories) == 0


def test_multi_class_vehicle_tracking():
    """Test tracking mixed person and vehicle targets simultaneously with class preservation."""
    tracker = ByteTrackTracker()

    # Frame 1: One person and one car
    det_person = Detection(0, "person", 0.90, BoundingBox(50, 100, 100, 250))
    det_car = Detection(2, "car", 0.88, BoundingBox(300, 200, 480, 350))

    res1 = tracker.update([det_person, det_car], frame_index=1, timestamp=1.0)
    assert res1.active_count == 2
    assert res1.person_count == 1
    assert res1.vehicle_count == 1

    tracks_by_class = {t.class_name: t for t in res1.tracks}
    assert "person" in tracks_by_class
    assert "car" in tracks_by_class
    assert tracks_by_class["person"].object_type == "person"
    assert tracks_by_class["car"].object_type == "vehicle"

    person_id = tracks_by_class["person"].track_id
    car_id = tracks_by_class["car"].track_id
    assert person_id != car_id

    # Frame 2: Both targets move slightly
    det_person2 = Detection(0, "person", 0.89, BoundingBox(52, 101, 102, 251))
    det_car2 = Detection(2, "car", 0.87, BoundingBox(305, 202, 485, 352))

    res2 = tracker.update([det_person2, det_car2], frame_index=2, timestamp=1.033)
    assert res2.active_count == 2

    tracks_by_id = {t.track_id: t for t in res2.tracks}
    assert person_id in tracks_by_id
    assert car_id in tracks_by_id
    assert tracks_by_id[person_id].class_name == "person"
    assert tracks_by_id[person_id].object_type == "person"
    assert tracks_by_id[car_id].class_name == "car"
    assert tracks_by_id[car_id].object_type == "vehicle"


def test_tracking_result_vehicle_counts_and_dict():
    """Test TrackingResult aggregation for multiple vehicle types."""
    t1 = Track(1, 0, "person", 0.9, BoundingBox(0, 0, 10, 10), 1, 1.0, object_type="person")
    t2 = Track(2, 2, "car", 0.85, BoundingBox(20, 20, 50, 50), 1, 1.0, object_type="vehicle")
    t3 = Track(3, 7, "truck", 0.82, BoundingBox(60, 60, 120, 120), 1, 1.0, object_type="vehicle")

    result = TrackingResult(frame_index=1, timestamp=1.0, tracks=[t1, t2, t3])
    assert result.active_count == 3
    assert result.person_count == 1
    assert result.vehicle_count == 2
    assert result.vehicle_counts_by_class["car"] == 1
    assert result.vehicle_counts_by_class["truck"] == 1
    assert result.vehicle_counts_by_class["motorcycle"] == 0

    d = result.to_dict()
    assert d["active_count"] == 3
    assert d["person_count"] == 1
    assert d["vehicle_count"] == 2
    assert d["tracks"][1]["object_type"] == "vehicle"

