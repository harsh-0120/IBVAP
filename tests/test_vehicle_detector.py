"""
Unit tests for IBVAP Vehicle Detection and Classification (Milestone 8).
Validates vehicle class mappings, data structures, VehicleDetector lifecycle,
DetectionResult multi-class aggregation, and mock inference.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from core.detector import (
    ALL_SURVEILLANCE_CLASS_IDS,
    COCO_PERSON_CLASS_ID,
    COCO_VEHICLE_CLASSES,
    VEHICLE_CLASS_IDS,
    BaseDetector,
    BoundingBox,
    Detection,
    DetectionResult,
    DetectorConfig,
    PersonDetector,
    VehicleDetector,
    YOLODetector,
)


def test_vehicle_class_constants():
    """Verify COCO class constants and mapping dictionaries."""
    assert COCO_PERSON_CLASS_ID == 0
    assert VEHICLE_CLASS_IDS == [2, 3, 5, 7]
    assert 2 in COCO_VEHICLE_CLASSES and COCO_VEHICLE_CLASSES[2] == "car"
    assert 3 in COCO_VEHICLE_CLASSES and COCO_VEHICLE_CLASSES[3] == "motorcycle"
    assert 5 in COCO_VEHICLE_CLASSES and COCO_VEHICLE_CLASSES[5] == "bus"
    assert 7 in COCO_VEHICLE_CLASSES and COCO_VEHICLE_CLASSES[7] == "truck"
    assert ALL_SURVEILLANCE_CLASS_IDS == [0, 2, 3, 5, 7]


def test_vehicle_detection_object_type_inference():
    """Verify automatic object_type classification based on class_id or class_name."""
    det_car = Detection(class_id=2, class_name="car", confidence=0.88, bbox=BoundingBox(10, 20, 100, 80))
    assert det_car.object_type == "vehicle"

    det_truck = Detection(class_id=7, class_name="truck", confidence=0.92, bbox=BoundingBox(50, 50, 200, 180))
    assert det_truck.object_type == "vehicle"

    det_person = Detection(class_id=0, class_name="person", confidence=0.85, bbox=BoundingBox(10, 10, 40, 100))
    assert det_person.object_type == "person"

    # Explicit override test
    det_custom = Detection(
        class_id=99,
        class_name="drone",
        confidence=0.75,
        bbox=BoundingBox(0, 0, 10, 10),
        object_type="aerial",
    )
    assert det_custom.object_type == "aerial"


def test_vehicle_detection_to_dict():
    """Verify detection dictionary serialization contains object_type."""
    bbox = BoundingBox(100.0, 120.0, 300.0, 260.0)
    det = Detection(class_id=2, class_name="car", confidence=0.89512, bbox=bbox)
    data = det.to_dict()

    assert data["class_id"] == 2
    assert data["class_name"] == "car"
    assert data["object_type"] == "vehicle"
    assert data["confidence"] == 0.8951
    assert data["bbox"]["feet_point"] == [200.0, 260.0]


def test_detection_result_multi_class_aggregation():
    """Verify DetectionResult person and vehicle counts, and class breakdown."""
    dets = [
        Detection(class_id=0, class_name="person", confidence=0.9, bbox=BoundingBox(10, 10, 30, 80)),
        Detection(class_id=0, class_name="person", confidence=0.85, bbox=BoundingBox(40, 10, 60, 80)),
        Detection(class_id=2, class_name="car", confidence=0.92, bbox=BoundingBox(100, 100, 200, 180)),
        Detection(class_id=2, class_name="car", confidence=0.88, bbox=BoundingBox(210, 100, 300, 180)),
        Detection(class_id=7, class_name="truck", confidence=0.79, bbox=BoundingBox(350, 80, 500, 240)),
        Detection(class_id=3, class_name="motorcycle", confidence=0.81, bbox=BoundingBox(520, 120, 580, 190)),
    ]

    result = DetectionResult(frame_index=10, timestamp=123.456, detections=dets, inference_time_ms=14.2)

    assert result.count == 6
    assert result.person_count == 2
    assert result.vehicle_count == 4
    counts_by_cls = result.vehicle_counts_by_class
    assert counts_by_cls["car"] == 2
    assert counts_by_cls["truck"] == 1
    assert counts_by_cls["motorcycle"] == 1
    assert counts_by_cls["bus"] == 0

    d = result.to_dict()
    assert d["person_count"] == 2
    assert d["vehicle_count"] == 4
    assert d["vehicle_counts_by_class"]["car"] == 2
    assert d["vehicle_counts_by_class"]["truck"] == 1


def test_vehicle_detector_initialization_and_hierarchy():
    """Verify VehicleDetector initializes with correct targets and class hierarchy."""
    detector = VehicleDetector()
    assert isinstance(detector, BaseDetector)
    assert isinstance(detector, YOLODetector)
    assert detector.target_classes == [2, 3, 5, 7]
    assert detector.supported_classes == COCO_VEHICLE_CLASSES


def test_person_detector_backward_compatibility():
    """Verify PersonDetector remains configured strictly for person class 0."""
    detector = PersonDetector()
    assert isinstance(detector, BaseDetector)
    assert isinstance(detector, YOLODetector)
    assert detector.target_classes == [0]


def test_vehicle_detector_empty_input():
    """Verify handling of empty or None frames."""
    detector = VehicleDetector()
    res1 = detector.detect(None, frame_index=1)
    assert isinstance(res1, DetectionResult)
    assert res1.count == 0

    res2 = detector.detect(np.zeros((0, 0, 3), dtype=np.uint8), frame_index=2)
    assert isinstance(res2, DetectionResult)
    assert res2.count == 0


def test_vehicle_detector_config_from_yaml(tmp_path):
    """Verify loading vehicle detection settings from YAML configuration."""
    yaml_content = """
detection:
  model_name: "yolo11n.pt"
  conf_threshold: 0.30
  iou_threshold: 0.40
  imgsz: 640
  device: "cpu"
  target_classes: [0, 2, 3, 5, 7]

vehicle_detection:
  enabled: true
  target_class_ids: [2, 7]
  conf_threshold: 0.30
"""
    cfg_file = tmp_path / "vehicle_cfg.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    cfg = DetectorConfig.from_yaml(cfg_file)
    assert cfg.vehicle_classes == [2, 7]
    assert cfg.target_classes == [0, 2, 3, 5, 7]

    veh_det = VehicleDetector(config=cfg)
    assert veh_det.target_classes == [2, 7]


def test_vehicle_detector_mock_inference():
    """Verify VehicleDetector correctly converts raw YOLO output to structured Detections."""
    detector = VehicleDetector()

    mock_boxes = MagicMock()
    mock_boxes.__len__.return_value = 2
    mock_boxes.xyxy.cpu().numpy.return_value = np.array([
        [100.0, 150.0, 300.0, 320.0],
        [400.0, 120.0, 650.0, 350.0],
    ], dtype=np.float32)
    mock_boxes.conf.cpu().numpy.return_value = np.array([0.91, 0.84], dtype=np.float32)
    mock_boxes.cls.cpu().numpy.return_value = np.array([2.0, 7.0], dtype=np.float32)

    mock_res = MagicMock()
    mock_res.boxes = mock_boxes

    mock_model = MagicMock()
    mock_model.predict.return_value = [mock_res]
    mock_model.names = {2: "car", 7: "truck"}
    detector._model = mock_model

    dummy_frame = np.full((480, 640, 3), 50, dtype=np.uint8)
    result = detector.detect(dummy_frame, frame_index=42)

    assert result.count == 2
    assert result.vehicle_count == 2
    assert result.person_count == 0

    det0 = result.detections[0]
    assert det0.class_id == 2
    assert det0.class_name == "car"
    assert det0.object_type == "vehicle"
    assert det0.bbox.feet_point == (200.0, 320.0)

    det1 = result.detections[1]
    assert det1.class_id == 7
    assert det1.class_name == "truck"
    assert det1.object_type == "vehicle"
    assert det1.bbox.feet_point == (525.0, 350.0)
