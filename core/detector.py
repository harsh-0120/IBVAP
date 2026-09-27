"""
IBVAP AI Detection Layer: Multi-Class Detection & Classification
Modular object detection interface supporting YOLO11n, YOLOv8n, and custom weights.
Provides unified single-pass detection, dedicated PersonDetector, and specialized VehicleDetector.
"""

import abc
import enum
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import yaml

logger = logging.getLogger("ibvap.detector")

# Standard COCO class mappings
COCO_PERSON_CLASS_ID = 0
COCO_VEHICLE_CLASSES: Dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
VEHICLE_CLASS_IDS: List[int] = [2, 3, 5, 7]
ALL_SURVEILLANCE_CLASS_IDS: List[int] = [0, 2, 3, 5, 7]


@dataclass
class BoundingBox:
    """Bounding box coordinates with spatial helper utilities."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> Tuple[float, float]:
        """Center point (x_center, y_center)."""
        return (self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0

    @property
    def feet_point(self) -> Tuple[float, float]:
        """
        Ground-contact reference point (bottom-center).
        Crucial for border virtual fence and tripwire ground-plane verification.
        """
        return (self.x1 + self.x2) / 2.0, self.y2

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_int_tuple(self) -> Tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2) as integers."""
        return int(round(self.x1)), int(round(self.y1)), int(round(self.x2)), int(round(self.y2))

    def as_xywh(self) -> Tuple[float, float, float, float]:
        """Return (x1, y1, width, height)."""
        return self.x1, self.y1, self.width, self.height


@dataclass
class Detection:
    """Structured representation of a single detected object."""
    class_id: int
    class_name: str
    confidence: float
    bbox: BoundingBox
    object_type: Optional[str] = None

    def __post_init__(self):
        if self.object_type is None:
            cname = self.class_name.lower()
            if self.class_id in VEHICLE_CLASS_IDS or cname in ["car", "motorcycle", "bus", "truck"]:
                self.object_type = "vehicle"
            else:
                self.object_type = "person"

    def to_dict(self) -> Dict[str, Any]:
        """Convert detection to structured serializable dictionary."""
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "object_type": self.object_type,
            "confidence": round(float(self.confidence), 4),
            "bbox": {
                "x1": round(float(self.bbox.x1), 2),
                "y1": round(float(self.bbox.y1), 2),
                "x2": round(float(self.bbox.x2), 2),
                "y2": round(float(self.bbox.y2), 2),
                "feet_point": [round(c, 2) for c in self.bbox.feet_point],
            },
        }


@dataclass
class DetectionResult:
    """Result of inference on a single frame."""
    frame_index: int
    timestamp: float
    detections: List[Detection] = field(default_factory=list)
    inference_time_ms: float = 0.0

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def person_count(self) -> int:
        return sum(1 for d in self.detections if d.object_type == "person")

    @property
    def vehicle_count(self) -> int:
        return sum(1 for d in self.detections if d.object_type == "vehicle")

    @property
    def vehicle_counts_by_class(self) -> Dict[str, int]:
        counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        for d in self.detections:
            cname = d.class_name.lower()
            if cname in counts:
                counts[cname] += 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "count": self.count,
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "vehicle_counts_by_class": self.vehicle_counts_by_class,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "detections": [d.to_dict() for d in self.detections],
        }


@dataclass
class DetectorConfig:
    """Configuration for AI object detector."""
    model_name: str = "yolo11n.pt"
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    imgsz: int = 640
    device: str = "auto"
    target_classes: List[int] = field(default_factory=lambda: [0])  # 0 is COCO person
    vehicle_classes: List[int] = field(default_factory=lambda: list(VEHICLE_CLASS_IDS))

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "DetectorConfig":
        """Load detector configuration from YAML."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        det_cfg: Dict[str, Any] = data.get("detection", {})
        veh_cfg: Dict[str, Any] = data.get("vehicle_detection", {})
        veh_classes = list(veh_cfg.get("target_class_ids", VEHICLE_CLASS_IDS))

        return cls(
            model_name=str(det_cfg.get("model_name", "yolo11n.pt")),
            conf_threshold=float(det_cfg.get("conf_threshold", 0.25)),
            iou_threshold=float(det_cfg.get("iou_threshold", 0.45)),
            imgsz=int(det_cfg.get("imgsz", 640)),
            device=str(det_cfg.get("device", "auto")),
            target_classes=list(det_cfg.get("target_classes", [0])),
            vehicle_classes=veh_classes,
        )


class BaseDetector(abc.ABC):
    """Abstract base class for pluggable object detectors."""

    @abc.abstractmethod
    def detect(self, frame: np.ndarray, frame_index: int = 0) -> DetectionResult:
        """Run detection on a single frame."""
        pass

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Name of the active detection model."""
        pass

    @property
    @abc.abstractmethod
    def device(self) -> str:
        """Active computing device (e.g., 'cpu' or 'cuda:0')."""
        pass


class YOLODetector(BaseDetector):
    """
    Ultralytics YOLO-based multi-class detector.
    Underlying general detector for person and vehicle detection/classification.
    Performs fast edge / CPU inference for configurable target classes.
    """

    def __init__(
        self,
        config: Optional[DetectorConfig] = None,
        target_classes: Optional[List[int]] = None,
    ):
        self.config = config or DetectorConfig()
        self._target_classes = (
            list(target_classes)
            if target_classes is not None
            else list(self.config.target_classes)
        )
        self._model = None
        self._resolved_device = self._resolve_device(self.config.device)
        self._load_model()

    @property
    def target_classes(self) -> List[int]:
        return self._target_classes

    @target_classes.setter
    def target_classes(self, classes: List[int]) -> None:
        self._target_classes = list(classes)

    def _resolve_device(self, requested_device: str) -> str:
        """Determine device based on hardware availability and user setting."""
        import torch

        req = requested_device.strip().lower()
        if req == "auto":
            if torch.cuda.is_available():
                selected = "cuda:0"
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"CUDA GPU detected: {gpu_name}. Using device '{selected}'.")
            else:
                selected = "cpu"
                logger.info("CUDA not available. Using 'cpu' for inference.")
            return selected

        if req.startswith("cuda") and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available. Falling back to 'cpu'.")
            return "cpu"

        return req

    def _load_model(self) -> None:
        """Initialize the Ultralytics YOLO model."""
        from ultralytics import YOLO

        logger.info(
            f"Loading object detection model: '{self.config.model_name}' on device '{self._resolved_device}'..."
        )
        self._model = YOLO(self.config.model_name)
        logger.info(f"Model '{self.config.model_name}' successfully loaded.")

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def device(self) -> str:
        return self._resolved_device

    def detect(self, frame: np.ndarray, frame_index: int = 0) -> DetectionResult:
        """
        Execute detection on the input frame.

        Args:
            frame: BGR numpy image array.
            frame_index: Sequential index of frame.

        Returns:
            DetectionResult containing structured Detection objects.
        """
        if frame is None or frame.size == 0:
            return DetectionResult(frame_index=frame_index, timestamp=time.time())

        t_start = time.time()

        # Run single-pass inference filtering for target classes
        results = self._model.predict(
            source=frame,
            conf=self.config.conf_threshold,
            iou=self.config.iou_threshold,
            imgsz=self.config.imgsz,
            classes=self._target_classes,
            device=self._resolved_device,
            verbose=False,
        )

        inference_time_ms = (time.time() - t_start) * 1000.0

        detections: List[Detection] = []
        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                cls_ids = boxes.cls.cpu().numpy().astype(int)
                names = self._model.names

                for box, conf, cls_id in zip(xyxy, confs, cls_ids):
                    raw_name = names.get(cls_id, str(cls_id)) if names else str(cls_id)
                    class_name = COCO_VEHICLE_CLASSES.get(cls_id, raw_name)
                    bbox = BoundingBox(
                        x1=float(box[0]),
                        y1=float(box[1]),
                        x2=float(box[2]),
                        y2=float(box[3]),
                    )
                    detections.append(
                        Detection(
                            class_id=int(cls_id),
                            class_name=class_name,
                            confidence=float(conf),
                            bbox=bbox,
                        )
                    )

        return DetectionResult(
            frame_index=frame_index,
            timestamp=time.time(),
            detections=detections,
            inference_time_ms=inference_time_ms,
        )

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: DetectionResult,
        draw_feet: bool = True,
        fps: Optional[float] = None,
    ) -> np.ndarray:
        """
        Draw high-contrast tactical HUD bounding boxes and telemetry on frame.
        """
        annotated = frame.copy()

        # Tactical color palette
        PERSON_BOX_COLOR = (0, 220, 255)    # Cyan target box
        VEHICLE_BOX_COLOR = (0, 180, 255)   # Amber target box for vehicles
        FEET_COLOR = (0, 0, 255)            # Red crosshair for ground contact
        TEXT_BG_COLOR = (20, 20, 20)        # Dark background for readability
        TEXT_COLOR = (255, 255, 255)

        for det in result.detections:
            x1, y1, x2, y2 = det.bbox.as_int_tuple()
            box_color = VEHICLE_BOX_COLOR if det.object_type == "vehicle" else PERSON_BOX_COLOR

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)

            # Label text
            label = f"{det.class_name.upper()}: {det.confidence:.2f}"
            (w, h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

            # Top label box
            cv2.rectangle(annotated, (x1, max(0, y1 - h - 6)), (x1 + w + 6, max(0, y1)), TEXT_BG_COLOR, -1)
            cv2.rectangle(annotated, (x1, max(0, y1 - h - 6)), (x1 + w + 6, max(0, y1)), box_color, 1)
            cv2.putText(
                annotated,
                label,
                (x1 + 3, max(h + 2, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                TEXT_COLOR,
                1,
                cv2.LINE_AA,
            )

            # Ground-plane anchor point
            if draw_feet:
                fx, fy = int(det.bbox.feet_point[0]), int(det.bbox.feet_point[1])
                cv2.circle(annotated, (fx, fy), 4, FEET_COLOR, -1)
                cv2.line(annotated, (fx - 8, fy), (fx + 8, fy), FEET_COLOR, 1)
                cv2.line(annotated, (fx, fy - 8), (fx, fy + 8), FEET_COLOR, 1)

        # Tactical HUD telemetry banner at top-right
        hud_lines = [
            f"AI MODEL: {self.model_name} [{self.device.upper()}]",
            f"TARGETS: {result.count} (PERSONS: {result.person_count}, VEHICLES: {result.vehicle_count})",
            f"INFERENCE: {result.inference_time_ms:.1f} ms",
        ]
        if fps is not None:
            hud_lines.append(f"FPS: {fps:.1f}")

        banner_x = annotated.shape[1] - 340
        banner_y = 20
        cv2.rectangle(annotated, (banner_x - 10, banner_y - 15), (annotated.shape[1] - 15, banner_y + len(hud_lines) * 22 + 5), (15, 15, 15), -1)
        cv2.rectangle(annotated, (banner_x - 10, banner_y - 15), (annotated.shape[1] - 15, banner_y + len(hud_lines) * 22 + 5), (0, 200, 255), 1)

        for i, line in enumerate(hud_lines):
            color = (0, 255, 200) if "TARGETS" not in line else ((0, 100, 255) if result.count > 0 else (180, 180, 180))
            cv2.putText(
                annotated,
                line,
                (banner_x, banner_y + i * 22 + 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                color,
                1,
                cv2.LINE_AA,
            )

        return annotated


class PersonDetector(YOLODetector):
    """
    Ultralytics YOLO-based person detector.
    Configured specifically for the 'person' class (COCO 0).
    100% backward-compatible wrapper preserving existing PersonDetector usage and tests.
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        cfg = config or DetectorConfig()
        # Default strictly to person class [0] for backward compatibility
        super().__init__(config=cfg, target_classes=[COCO_PERSON_CLASS_ID])


class VehicleDetector(YOLODetector):
    """
    Ultralytics YOLO-based vehicle detector and classifier.
    Specializes in detecting and classifying vehicles:
    car (2), motorcycle (3), bus (5), and truck (7).
    Independently usable and testable.
    """

    SUPPORTED_VEHICLE_CLASSES = COCO_VEHICLE_CLASSES

    def __init__(
        self,
        config: Optional[DetectorConfig] = None,
        vehicle_classes: Optional[List[int]] = None,
    ):
        cfg = config or DetectorConfig()
        target_classes = (
            list(vehicle_classes)
            if vehicle_classes is not None
            else list(getattr(cfg, "vehicle_classes", VEHICLE_CLASS_IDS))
        )
        super().__init__(config=cfg, target_classes=target_classes)

    @property
    def supported_classes(self) -> Dict[int, str]:
        """Dictionary of supported COCO vehicle class ID to class name."""
        return dict(self.SUPPORTED_VEHICLE_CLASSES)

