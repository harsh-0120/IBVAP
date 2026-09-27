"""
Unit tests for IBVAP Person Detection logic and structured data representations.
"""

import pytest
import numpy as np

from core.detector import (
    BoundingBox,
    Detection,
    DetectionResult,
    DetectorConfig,
    BaseDetector,
)


def test_bounding_box_geometry():
    """Test bounding box coordinate math, center, and feet ground anchor."""
    bbox = BoundingBox(x1=100.0, y1=150.0, x2=200.0, y2=350.0)

    assert bbox.width == 100.0
    assert bbox.height == 200.0
    assert bbox.area == 20000.0
    assert bbox.center == (150.0, 250.0)

    # Feet ground anchor must be (x_center, y_max)
    assert bbox.feet_point == (150.0, 350.0)

    assert bbox.as_int_tuple() == (100, 150, 200, 350)
    assert bbox.as_xywh() == (100.0, 150.0, 100.0, 200.0)


def test_bounding_box_degenerate():
    """Test degenerate/inverted bounding box edge cases."""
    # When x2 < x1, width should clamp to 0
    bbox = BoundingBox(x1=200.0, y1=100.0, x2=100.0, y2=200.0)
    assert bbox.width == 0.0


def test_detection_to_dict():
    """Test structured serialization of detection objects."""
    bbox = BoundingBox(x1=50.2, y1=60.4, x2=150.8, y2=260.6)
    det = Detection(
        class_id=0,
        class_name="person",
        confidence=0.88765,
        bbox=bbox,
    )

    d = det.to_dict()
    assert d["class_id"] == 0
    assert d["class_name"] == "person"
    assert d["confidence"] == 0.8877  # Rounded to 4 places
    assert d["bbox"]["x1"] == 50.2
    assert d["bbox"]["y2"] == 260.6
    assert d["bbox"]["feet_point"] == [100.5, 260.6]


def test_detection_result_aggregation():
    """Test DetectionResult counts and filtering."""
    det1 = Detection(class_id=0, class_name="person", confidence=0.92, bbox=BoundingBox(10, 10, 50, 90))
    det2 = Detection(class_id=0, class_name="person", confidence=0.84, bbox=BoundingBox(60, 20, 100, 95))
    det3 = Detection(class_id=2, class_name="car", confidence=0.76, bbox=BoundingBox(200, 200, 300, 280))

    result = DetectionResult(
        frame_index=42,
        timestamp=1000.0,
        detections=[det1, det2, det3],
        inference_time_ms=12.5,
    )

    assert result.count == 3
    assert result.person_count == 2
    assert result.inference_time_ms == 12.5

    data = result.to_dict()
    assert data["frame_index"] == 42
    assert data["count"] == 3
    assert data["person_count"] == 2
    assert len(data["detections"]) == 3


def test_detector_config_from_yaml(tmp_path):
    """Test loading detector config from YAML."""
    yaml_content = """
detection:
  model_name: "yolo11n.pt"
  conf_threshold: 0.40
  iou_threshold: 0.50
  imgsz: 640
  device: "cpu"
  target_classes: [0]
"""
    yaml_file = tmp_path / "det_config.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    cfg = DetectorConfig.from_yaml(yaml_file)
    assert cfg.model_name == "yolo11n.pt"
    assert cfg.conf_threshold == 0.40
    assert cfg.iou_threshold == 0.50
    assert cfg.imgsz == 640
    assert cfg.device == "cpu"
    assert cfg.target_classes == [0]


def test_base_detector_subclassing():
    """Test that BaseDetector requires abstract method implementations."""
    class CustomDetector(BaseDetector):
        @property
        def model_name(self) -> str:
            return "mock_model"

        @property
        def device(self) -> str:
            return "cpu"

        def detect(self, frame, frame_index=0):
            return DetectionResult(frame_index=frame_index, timestamp=0.0)

    det = CustomDetector()
    assert det.model_name == "mock_model"
    res = det.detect(np.zeros((100, 100, 3), dtype=np.uint8))
    assert isinstance(res, DetectionResult)
