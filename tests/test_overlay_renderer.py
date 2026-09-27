"""
Unit tests for IBVAP OverlayRenderer (Milestone 7B).
Validates frame dimension/dtype preservation, bounding box rendering,
label/badge rendering, feet crosshair rendering, trajectory trails, and JPEG compression.
"""

import cv2
import numpy as np
import pytest

from core.overlay_renderer import OverlayConfig, OverlayRenderer
from core.tracker import BoundingBox, Track


@pytest.fixture
def blank_frame():
    """Provides a blank 720p dark surveillance frame."""
    return np.full((720, 1280, 3), 20, dtype=np.uint8)


@pytest.fixture
def sample_track():
    """Provides a realistic Track instance with trajectory."""
    bbox = BoundingBox(x1=300.0, y1=200.0, x2=420.0, y2=500.0)
    return Track(
        track_id=12,
        class_id=0,
        class_name="person",
        confidence=0.88,
        bbox=bbox,
        frame_index=15,
        timestamp=1725624000.0,
        trajectory=[(360.0, 480.0), (360.0, 490.0), (360.0, 500.0)],
    )


def test_overlay_renderer_dimensions_and_dtype(blank_frame, sample_track):
    """Verify rendered frame preserves identical width, height, channels, and uint8 dtype."""
    renderer = OverlayRenderer()
    annotated = renderer.render(blank_frame, [sample_track], fps=12.5, camera_id="TEST-CAM")

    assert annotated.shape == blank_frame.shape
    assert annotated.dtype == np.uint8
    assert isinstance(annotated, np.ndarray)


def test_overlay_renderer_empty_tracks(blank_frame):
    """Verify rendering with zero active tracks returns valid frame without errors."""
    renderer = OverlayRenderer()
    annotated = renderer.render(blank_frame, [], fps=10.0)

    assert annotated.shape == blank_frame.shape
    assert annotated.dtype == np.uint8


def test_overlay_renderer_draws_bounding_box_and_badge(blank_frame, sample_track):
    """Verify that drawing occurs and modifies pixel values in the box and badge region."""
    renderer = OverlayRenderer()
    annotated = renderer.render(blank_frame, [sample_track], fps=10.0)

    # Pixel differences must exist between original and annotated
    diff = np.abs(annotated.astype(int) - blank_frame.astype(int))
    assert np.sum(diff) > 0

    # Specifically check the bounding box coordinate region
    box_region_diff = diff[200:500, 300:420]
    assert np.sum(box_region_diff) > 0


def test_overlay_renderer_draws_feet_point(blank_frame, sample_track):
    """Verify ground-contact feet point crosshair is drawn at (360, 500)."""
    cfg = OverlayConfig(show_box=False, show_track_id=False, show_trajectory=False, show_feet=True)
    renderer = OverlayRenderer(cfg)
    annotated = renderer.render(blank_frame, [sample_track])

    diff = np.abs(annotated.astype(int) - blank_frame.astype(int))
    feet_diff = diff[490:510, 350:370]
    assert np.sum(feet_diff) > 0


def test_overlay_renderer_draws_trajectory(blank_frame, sample_track):
    """Verify trajectory trail is rendered when history exists."""
    cfg = OverlayConfig(show_box=False, show_track_id=False, show_feet=False, show_trajectory=True)
    renderer = OverlayRenderer(cfg)
    annotated = renderer.render(blank_frame, [sample_track])

    diff = np.abs(annotated.astype(int) - blank_frame.astype(int))
    assert np.sum(diff) > 0


def test_overlay_renderer_jpeg_encoding(blank_frame, sample_track):
    """Verify JPEG compression produces valid JPEG byte stream matching original resolution."""
    renderer = OverlayRenderer()
    annotated = renderer.render(blank_frame, [sample_track])
    jpeg_bytes = renderer.encode_jpeg(annotated)

    assert isinstance(jpeg_bytes, bytes)
    assert len(jpeg_bytes) > 1000
    # Standard JPEG Start-of-Image (SOI) marker FF D8 FF
    assert jpeg_bytes[:3] == b"\xff\xd8\xff"

    # Verify bytes decode cleanly with OpenCV
    nparr = np.frombuffer(jpeg_bytes, np.uint8)
    decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (720, 1280, 3)


def test_overlay_renderer_renders_vehicle_badge(blank_frame):
    """Verify OverlayRenderer draws vehicle tracks with distinct tactical vehicle styling."""
    renderer = OverlayRenderer()
    car_bbox = BoundingBox(x1=200.0, y1=150.0, x2=450.0, y2=320.0)
    car_track = Track(
        track_id=5,
        class_id=2,
        class_name="car",
        confidence=0.91,
        bbox=car_bbox,
        frame_index=1,
        timestamp=100.0,
        trajectory=[(325.0, 310.0), (325.0, 320.0)],
        object_type="vehicle",
    )

    annotated = renderer.render(blank_frame, [car_track], fps=15.0, camera_id="CAM-01")
    assert annotated.shape == blank_frame.shape

    # Pixel difference must exist in the vehicle box and badge region
    diff = np.abs(annotated.astype(int) - blank_frame.astype(int))
    assert np.sum(diff[150:320, 200:450]) > 0

    # Test mixed tracks (person + vehicle)
    person_bbox = BoundingBox(x1=50.0, y1=100.0, x2=90.0, y2=220.0)
    person_track = Track(
        track_id=1,
        class_id=0,
        class_name="person",
        confidence=0.88,
        bbox=person_bbox,
        frame_index=1,
        timestamp=100.0,
        object_type="person",
    )

    annotated_mixed = renderer.render(blank_frame, [car_track, person_track], fps=15.0)
    assert annotated_mixed.shape == blank_frame.shape
    diff_mixed = np.abs(annotated_mixed.astype(int) - blank_frame.astype(int))
    assert np.sum(diff_mixed) > 0

