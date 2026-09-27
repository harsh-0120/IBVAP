"""
Unit tests for IBVAP Spatial Analytics Engine (Virtual Fences & Tripwires).
All geometry tests use deterministic synthetic coordinates.
"""

import pytest
from core.detector import BoundingBox
from core.tracker import Track
from core.spatial_engine import (
    CrossingDirection,
    PolygonZone,
    SpatialConfig,
    SpatialEngine,
    SpatialEvent,
    SpatialEventType,
    Tripwire,
    ZoneState,
)


def make_track(track_id: int, feet_x: float, feet_y: float, width: float = 40.0, height: float = 100.0) -> Track:
    """Helper to synthesize a Track with a precise ground-contact feet point."""
    x1 = feet_x - width / 2.0
    x2 = feet_x + width / 2.0
    y2 = feet_y
    y1 = feet_y - height
    bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
    return Track(
        track_id=track_id,
        class_id=0,
        class_name="person",
        confidence=0.90,
        bbox=bbox,
        frame_index=1,
        timestamp=1.0,
        trajectory=[(feet_x, feet_y)],
    )


def test_feet_point_calculation():
    """1. Test feet-point ground-contact anchor calculation."""
    bbox = BoundingBox(x1=100.0, y1=200.0, x2=200.0, y2=450.0)
    # Expected: ((100+200)/2, 450) = (150, 450)
    assert bbox.feet_point == (150.0, 450.0)

    track = make_track(track_id=1, feet_x=350.0, feet_y=500.0)
    assert track.feet_point == (350.0, 500.0)


def test_point_inside_polygon():
    """2. Test point strictly inside polygon."""
    zone = PolygonZone("z1", "Test Zone", [(200, 200), (600, 200), (600, 600), (200, 600)])
    assert zone.contains_point((400, 400)) is True


def test_point_outside_polygon():
    """3. Test point strictly outside polygon."""
    zone = PolygonZone("z1", "Test Zone", [(200, 200), (600, 200), (600, 600), (200, 600)])
    assert zone.contains_point((100, 100)) is False
    assert zone.contains_point((700, 400)) is False


def test_polygon_boundary_handling():
    """4. Test point touching the boundary edge or vertex."""
    zone = PolygonZone("z1", "Test Zone", [(200, 200), (600, 200), (600, 600), (200, 600)])
    # On the edge
    assert zone.contains_point((200, 400)) is True
    # On the vertex
    assert zone.contains_point((200, 200)) is True


def test_outside_to_inside_transition():
    """5. Test OUTSIDE -> INSIDE transition generates exactly one intrusion event."""
    zone = PolygonZone("z1", "Restricted Area", [(200, 200), (600, 200), (600, 600), (200, 600)])
    cfg = SpatialConfig(zones=[zone], cooldown_sec=5.0, min_track_frames=1)
    engine = SpatialEngine(cfg)

    # Frame 1: Person outside at (100, 400)
    t1 = make_track(track_id=10, feet_x=100, feet_y=400)
    events1, states1 = engine.process_tracks([t1], frame_index=1, timestamp=1.0)
    assert len(events1) == 0
    assert states1[10]["z1"] == ZoneState.OUTSIDE

    # Frame 2: Person moves inside to (350, 400)
    t2 = make_track(track_id=10, feet_x=350, feet_y=400)
    events2, states2 = engine.process_tracks([t2], frame_index=2, timestamp=1.04)
    assert len(events2) == 1
    assert events2[0].event_type == SpatialEventType.ZONE_INTRUSION
    assert events2[0].track_id == 10
    assert events2[0].zone_id == "z1"
    assert states2[10]["z1"] == ZoneState.INSIDE
    assert engine.total_intrusions == 1


def test_inside_to_inside_no_repeated_intrusion():
    """6. Test INSIDE -> INSIDE does not generate repeated events on consecutive frames."""
    zone = PolygonZone("z1", "Restricted Area", [(200, 200), (600, 200), (600, 600), (200, 600)])
    cfg = SpatialConfig(zones=[zone], cooldown_sec=5.0, min_track_frames=1)
    engine = SpatialEngine(cfg)

    # Frame 1: Outside
    t1 = make_track(track_id=10, feet_x=100, feet_y=400)
    engine.process_tracks([t1], frame_index=1, timestamp=1.0)

    # Frame 2: Steps Inside -> Intrusion Event
    t2 = make_track(track_id=10, feet_x=300, feet_y=400)
    ev2, _ = engine.process_tracks([t2], frame_index=2, timestamp=1.04)
    assert len(ev2) == 1

    # Frames 3, 4, 5: Continues walking inside
    for i in range(3, 6):
        t = make_track(track_id=10, feet_x=300 + i * 10, feet_y=400)
        events, states = engine.process_tracks([t], frame_index=i, timestamp=1.0 + i * 0.04)
        assert len(events) == 0, f"Frame {i} should not generate repeated intrusion event"
        assert states[10]["z1"] == ZoneState.INSIDE

    assert engine.total_intrusions == 1


def test_inside_to_outside_transition():
    """7. Test INSIDE -> OUTSIDE transition resets zone state cleanly without intrusion."""
    zone = PolygonZone("z1", "Restricted Area", [(200, 200), (600, 200), (600, 600), (200, 600)])
    cfg = SpatialConfig(zones=[zone], cooldown_sec=5.0, min_track_frames=1)
    engine = SpatialEngine(cfg)

    # Start Inside
    t1 = make_track(track_id=10, feet_x=300, feet_y=400)
    engine.process_tracks([t1], frame_index=1, timestamp=1.0)

    # Step Outside to (700, 400)
    t2 = make_track(track_id=10, feet_x=700, feet_y=400)
    events, states = engine.process_tracks([t2], frame_index=2, timestamp=1.04)
    assert len(events) == 0
    assert states[10]["z1"] == ZoneState.OUTSIDE


def test_tripwire_crossing_detection():
    """8. Test tripwire crossing intersection."""
    tripwire = Tripwire("w1", "Border Wire", start=(500, 100), end=(500, 800))
    # Segment from (450, 400) to (550, 400) intersects wire at (500, 400)
    crossed, direction = tripwire.check_crossing(p_prev=(450, 400), p_curr=(550, 400))
    assert crossed is True


def test_tripwire_left_to_right_direction():
    """9. Test LEFT_TO_RIGHT crossing direction along vertical wire going top-to-bottom."""
    tripwire = Tripwire("w1", "Border Wire", start=(500, 100), end=(500, 800))
    # Vector is from (500, 100) down to (500, 800).
    # Moving from x=450 (left of vector) to x=550 (right of vector)
    crossed, direction = tripwire.check_crossing(p_prev=(450, 400), p_curr=(550, 400))
    assert crossed is True
    assert direction == CrossingDirection.LEFT_TO_RIGHT


def test_tripwire_right_to_left_direction():
    """10. Test RIGHT_TO_LEFT crossing direction."""
    tripwire = Tripwire("w1", "Border Wire", start=(500, 100), end=(500, 800))
    # Moving from x=550 (right of vector) to x=450 (left of vector)
    crossed, direction = tripwire.check_crossing(p_prev=(550, 400), p_curr=(450, 400))
    assert crossed is True
    assert direction == CrossingDirection.RIGHT_TO_LEFT


def test_tripwire_no_crossing():
    """11. Test no crossing when trajectory does not intersect tripwire."""
    tripwire = Tripwire("w1", "Border Wire", start=(500, 100), end=(500, 800))
    # Trajectory staying on left side: (300, 400) -> (400, 400)
    crossed, direction = tripwire.check_crossing(p_prev=(300, 400), p_curr=(400, 400))
    assert crossed is False
    assert direction == CrossingDirection.UNKNOWN


def test_state_cleanup_on_disappearance():
    """12. Test internal state cleanup when track disappears from camera view."""
    zone = PolygonZone("z1", "Test Zone", [(200, 200), (600, 200), (600, 600), (200, 600)])
    tripwire = Tripwire("w1", "Test Wire", start=(500, 100), end=(500, 800))
    cfg = SpatialConfig(zones=[zone], tripwires=[tripwire], min_track_frames=1)
    engine = SpatialEngine(cfg)

    # Track 5 active
    t = make_track(track_id=5, feet_x=400, feet_y=400)
    engine.process_tracks([t], frame_index=1, timestamp=1.0)
    assert (5, "z1") in engine._zone_states
    assert 5 in engine._previous_feet_points

    # Track 5 disappears in next frame (empty tracks list)
    engine.process_tracks([], frame_index=2, timestamp=1.04)
    # State must be cleaned up
    assert (5, "z1") not in engine._zone_states
    assert 5 not in engine._previous_feet_points
    assert 5 not in engine._track_lifespans


def test_spatial_event_serialization():
    """Test SpatialEvent serialization to dictionary."""
    ev = SpatialEvent(
        event_type=SpatialEventType.TRIPWIRE_CROSSING,
        track_id=17,
        zone_id="border_line_1",
        zone_name="Border Perimeter",
        object_type="person",
        frame_index=42,
        timestamp=123.456,
        feet_point=(642.12, 418.78),
        direction=CrossingDirection.LEFT_TO_RIGHT,
    )
    d = ev.to_dict()
    assert d["event_type"] == "TRIPWIRE_CROSSING"
    assert d["track_id"] == 17
    assert d["zone_id"] == "border_line_1"
    assert d["direction"] == "LEFT_TO_RIGHT"
    assert d["feet_point"] == [642.12, 418.78]
