"""
IBVAP Multi-Object Tracking Layer: ByteTrack Integration
Provides persistent tracking IDs, ground-plane trajectory histories,
and lifecycle management for detected persons in border surveillance feeds.
"""

import abc
import collections
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import yaml

from core.detector import BoundingBox, Detection, DetectionResult

logger = logging.getLogger("ibvap.tracker")

# Tactical color palette for distinct track visualization
TACTICAL_TRACK_COLORS = [
    (0, 255, 255),    # Amber / Yellow
    (255, 191, 0),    # Deep Sky Blue
    (0, 255, 128),    # Spring Green
    (255, 105, 180),  # Hot Pink
    (50, 205, 50),    # Lime Green
    (0, 165, 255),    # Orange
    (255, 255, 0),    # Cyan
    (238, 130, 238),  # Violet
    (0, 215, 255),    # Gold
    (128, 255, 0),    # Chartreuse
    (205, 133, 63),   # Peru
    (0, 250, 154),    # Medium Spring Green
]


def get_track_color(track_id: int) -> Tuple[int, int, int]:
    """Returns a deterministic BGR color for a given track ID."""
    return TACTICAL_TRACK_COLORS[track_id % len(TACTICAL_TRACK_COLORS)]


@dataclass
class Track:
    """Represents a single active tracked object across consecutive frames."""
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: BoundingBox
    frame_index: int
    timestamp: float
    trajectory: List[Tuple[float, float]] = field(default_factory=list)
    object_type: Optional[str] = None

    def __post_init__(self):
        if self.object_type is None:
            cname = self.class_name.lower()
            if self.class_id in [2, 3, 5, 7] or cname in ["car", "motorcycle", "bus", "truck"]:
                self.object_type = "vehicle"
            else:
                self.object_type = "person"

    @property
    def center(self) -> Tuple[float, float]:
        """Spatial center of target bounding box."""
        return self.bbox.center

    @property
    def feet_point(self) -> Tuple[float, float]:
        """
        Ground-plane contact point (bottom center).
        Crucial for virtual fence and border perimeter crossing detection.
        """
        return self.bbox.feet_point

    def to_dict(self) -> Dict[str, Any]:
        """Convert track to structured serializable dictionary."""
        return {
            "track_id": int(self.track_id),
            "class_id": int(self.class_id),
            "class_name": self.class_name,
            "object_type": self.object_type,
            "confidence": round(float(self.confidence), 4),
            "bbox": {
                "x1": round(float(self.bbox.x1), 2),
                "y1": round(float(self.bbox.y1), 2),
                "x2": round(float(self.bbox.x2), 2),
                "y2": round(float(self.bbox.y2), 2),
            },
            "center": [round(c, 2) for c in self.center],
            "feet_point": [round(c, 2) for c in self.feet_point],
            "frame_index": int(self.frame_index),
            "timestamp": round(float(self.timestamp), 3),
            "trajectory_length": len(self.trajectory),
            "trajectory": [[round(pt[0], 2), round(pt[1], 2)] for pt in self.trajectory],
        }


@dataclass
class TrackingResult:
    """Aggregated tracking results for a single video frame."""
    frame_index: int
    timestamp: float
    tracks: List[Track] = field(default_factory=list)

    @property
    def active_count(self) -> int:
        return len(self.tracks)

    @property
    def person_count(self) -> int:
        return sum(1 for t in self.tracks if t.object_type == "person")

    @property
    def vehicle_count(self) -> int:
        return sum(1 for t in self.tracks if t.object_type == "vehicle")

    @property
    def vehicle_counts_by_class(self) -> Dict[str, int]:
        counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        for t in self.tracks:
            cname = t.class_name.lower()
            if cname in counts:
                counts[cname] += 1
        return counts

    @property
    def track_ids(self) -> List[int]:
        return [t.track_id for t in self.tracks]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "active_count": self.active_count,
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "vehicle_counts_by_class": self.vehicle_counts_by_class,
            "track_ids": self.track_ids,
            "tracks": [t.to_dict() for t in self.tracks],
        }


@dataclass
class TrackerConfig:
    """Configuration parameters for multi-object tracking."""
    tracker_type: str = "bytetrack"
    track_high_thresh: float = 0.25
    track_low_thresh: float = 0.10
    new_track_thresh: float = 0.25
    track_buffer: int = 30
    match_thresh: float = 0.80
    max_trajectory_length: int = 30
    target_classes: List[str] = field(default_factory=lambda: ["person", "car", "motorcycle", "bus", "truck"])

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "TrackerConfig":
        """Load tracker configuration from YAML file."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        trk_cfg: Dict[str, Any] = data.get("tracking", {})
        return cls(
            tracker_type=str(trk_cfg.get("tracker_type", "bytetrack")),
            track_high_thresh=float(trk_cfg.get("track_high_thresh", 0.25)),
            track_low_thresh=float(trk_cfg.get("track_low_thresh", 0.10)),
            new_track_thresh=float(trk_cfg.get("new_track_thresh", 0.25)),
            track_buffer=int(trk_cfg.get("track_buffer", 30)),
            match_thresh=float(trk_cfg.get("match_thresh", 0.80)),
            max_trajectory_length=int(trk_cfg.get("max_trajectory_length", 30)),
            target_classes=list(trk_cfg.get("target_classes", ["person", "car", "motorcycle", "bus", "truck"])),
        )


class BaseTracker(abc.ABC):
    """Abstract base class for pluggable Multi-Object Trackers."""

    @abc.abstractmethod
    def update(
        self,
        detections: Union[DetectionResult, List[Detection]],
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> TrackingResult:
        """Update tracker state with new frame detections."""
        pass

    @abc.abstractmethod
    def reset(self) -> None:
        """Clear all active tracks and trajectory history."""
        pass


class _ByteTrackAdapter:
    """
    Internal adapter mimicking Ultralytics Results object
    for BYTETracker consumption. Exposes conf, cls, and xywh (center format).
    """

    def __init__(self, xywh: np.ndarray, conf: np.ndarray, cls: np.ndarray):
        self.xywh = np.asarray(xywh, dtype=np.float32).reshape(-1, 4)
        self.conf = np.asarray(conf, dtype=np.float32).reshape(-1)
        self.cls = np.asarray(cls, dtype=np.float32).reshape(-1)

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, idx: Any) -> "_ByteTrackAdapter":
        return _ByteTrackAdapter(self.xywh[idx], self.conf[idx], self.cls[idx])


class ByteTrackTracker(BaseTracker):
    """
    Multi-Object Tracker utilizing ByteTrack.
    Associates detections across consecutive frames to assign stable, persistent track IDs
    and retains trajectory histories for ground movement analysis.
    """

    def __init__(self, config: Optional[TrackerConfig] = None):
        self.config = config or TrackerConfig()
        self._trajectories: Dict[int, collections.deque] = {}
        self._last_seen_frame: Dict[int, int] = {}
        self._total_unique_tracks = 0
        self._seen_track_ids = set()

        self._init_bytetrack()

    def _init_bytetrack(self) -> None:
        """Initialize the underlying ByteTrack algorithm."""
        from ultralytics.trackers.byte_tracker import BYTETracker

        args = SimpleNamespace(
            track_high_thresh=self.config.track_high_thresh,
            track_low_thresh=self.config.track_low_thresh,
            new_track_thresh=self.config.new_track_thresh,
            track_buffer=self.config.track_buffer,
            match_thresh=self.config.match_thresh,
            fuse_score=True,
        )
        self._tracker = BYTETracker(args)
        logger.info(
            f"ByteTrack initialized with buffer={self.config.track_buffer}, "
            f"match_thresh={self.config.match_thresh}"
        )

    def reset(self) -> None:
        """Reset tracker state and clear trajectory history."""
        self._trajectories.clear()
        self._last_seen_frame.clear()
        self._seen_track_ids.clear()
        self._total_unique_tracks = 0
        self._init_bytetrack()
        logger.info("ByteTrackTracker reset successfully.")

    @property
    def total_unique_tracks(self) -> int:
        """Total number of distinct tracking IDs observed since initialization."""
        return len(self._seen_track_ids)

    def update(
        self,
        detections: Union[DetectionResult, List[Detection]],
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> TrackingResult:
        """
        Update tracking state using detections from current frame.

        Args:
            detections: DetectionResult or List[Detection] from detector.
            frame_index: Sequential index of frame.
            timestamp: Unix timestamp.

        Returns:
            TrackingResult with active Track objects including trajectory history.
        """
        if isinstance(detections, DetectionResult):
            raw_dets = detections.detections
            frame_index = detections.frame_index
            timestamp = detections.timestamp
        else:
            raw_dets = detections

        # Filter strictly for target classes (e.g. 'person')
        target_classes_lower = {c.lower() for c in self.config.target_classes}
        filtered_dets = [
            d for d in raw_dets if d.class_name.lower() in target_classes_lower
        ]

        if not filtered_dets:
            # Pass empty adapter to advance tracker internal Kalman states
            empty_adapter = _ByteTrackAdapter(
                np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
            )
            raw_tracks = self._tracker.update(empty_adapter)
        else:
            # Convert BoundingBoxes to center xywh format [x_center, y_center, w, h]
            xywh_list = []
            conf_list = []
            cls_list = []
            for d in filtered_dets:
                cx, cy = d.bbox.center
                xywh_list.append([cx, cy, d.bbox.width, d.bbox.height])
                conf_list.append(d.confidence)
                cls_list.append(d.class_id)

            adapter = _ByteTrackAdapter(
                np.array(xywh_list, dtype=np.float32),
                np.array(conf_list, dtype=np.float32),
                np.array(cls_list, dtype=np.float32),
            )
            raw_tracks = self._tracker.update(adapter)

        # Build mapping from class_id to metadata
        class_meta: Dict[int, Tuple[str, str]] = {
            0: ("person", "person"),
            2: ("car", "vehicle"),
            3: ("motorcycle", "vehicle"),
            5: ("bus", "vehicle"),
            7: ("truck", "vehicle"),
        }
        for d in filtered_dets:
            class_meta[d.class_id] = (d.class_name, getattr(d, "object_type", "person"))

        # Parse raw tracks: [x1, y1, x2, y2, track_id, score, cls, idx]
        active_tracks: List[Track] = []
        current_active_ids = set()

        if len(raw_tracks) > 0:
            for row in raw_tracks:
                if len(row) < 7:
                    continue
                x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                track_id = int(round(float(row[4])))
                score = float(row[5])
                cls_id = int(round(float(row[6])))

                current_active_ids.add(track_id)
                self._seen_track_ids.add(track_id)
                self._last_seen_frame[track_id] = frame_index

                bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
                feet_pt = bbox.feet_point

                # Update trajectory history
                if track_id not in self._trajectories:
                    self._trajectories[track_id] = collections.deque(
                        maxlen=self.config.max_trajectory_length
                    )
                self._trajectories[track_id].append(feet_pt)

                class_name, obj_type = class_meta.get(cls_id, ("person", "person"))
                track_obj = Track(
                    track_id=track_id,
                    class_id=cls_id,
                    class_name=class_name,
                    confidence=score,
                    bbox=bbox,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    trajectory=list(self._trajectories[track_id]),
                    object_type=obj_type,
                )
                active_tracks.append(track_obj)

        # Clean up stale trajectories for tracks absent longer than track_buffer
        stale_ids = [
            tid
            for tid, last_frame in self._last_seen_frame.items()
            if (frame_index - last_frame) > self.config.track_buffer
        ]
        for tid in stale_ids:
            self._trajectories.pop(tid, None)
            self._last_seen_frame.pop(tid, None)

        return TrackingResult(
            frame_index=frame_index,
            timestamp=timestamp,
            tracks=active_tracks,
        )

    def annotate_frame(
        self,
        frame: np.ndarray,
        tracking_result: TrackingResult,
        draw_trails: bool = True,
        draw_feet: bool = True,
        fps: Optional[float] = None,
    ) -> np.ndarray:
        """
        Draw high-contrast tactical tracking annotations on video frame:
        - Bounding box with persistent Track ID & confidence
        - Movement trajectory polyline trail behind each target
        - Ground-plane contact crosshair (feet point)
        - Tactical Command & Control HUD telemetry overlay
        """
        annotated = frame.copy()

        for track in tracking_result.tracks:
            color = get_track_color(track.track_id)
            x1, y1, x2, y2 = track.bbox.as_int_tuple()

            # 1. Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # 2. Movement trajectory trail (fading or line connecting feet points)
            if draw_trails and len(track.trajectory) > 1:
                pts = np.array(
                    [[int(pt[0]), int(pt[1])] for pt in track.trajectory],
                    dtype=np.int32,
                )
                cv2.polylines(annotated, [pts], isClosed=False, color=color, thickness=2, lineType=cv2.LINE_AA)

            # 3. Feet ground anchor crosshair
            if draw_feet:
                fx, fy = int(track.feet_point[0]), int(track.feet_point[1])
                cv2.circle(annotated, (fx, fy), 4, (0, 0, 255), -1)
                cv2.line(annotated, (fx - 8, fy), (fx + 8, fy), (0, 0, 255), 1)
                cv2.line(annotated, (fx, fy - 8), (fx, fy + 8), (0, 0, 255), 1)

            # 4. Target ID & Confidence Tag
            if getattr(track, "object_type", "person") == "vehicle":
                tag = f"{track.class_name.upper()} #{track.track_id} | {track.confidence:.2f}"
            else:
                tag = f"ID: #{track.track_id} | {track.confidence:.2f}"
            (w, h), baseline = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)

            tag_y1 = max(0, y1 - h - 6)
            tag_y2 = max(0, y1)
            cv2.rectangle(annotated, (x1, tag_y1), (x1 + w + 8, tag_y2), (20, 20, 20), -1)
            cv2.rectangle(annotated, (x1, tag_y1), (x1 + w + 8, tag_y2), color, 1)
            cv2.putText(
                annotated,
                tag,
                (x1 + 4, max(h + 2, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # 5. Tactical C2 Telemetry HUD Banner (Top-Right)
        hud_lines = [
            f"TRACKER: BYTETRACK [ACTIVE: {tracking_result.active_count}]",
            f"TOTAL UNIQUE IDS: {self.total_unique_tracks}",
        ]
        if fps is not None:
            hud_lines.append(f"PIPELINE SPEED: {fps:.1f} FPS")

        banner_x = annotated.shape[1] - 330
        banner_y = 20
        cv2.rectangle(
            annotated,
            (banner_x - 10, banner_y - 15),
            (annotated.shape[1] - 15, banner_y + len(hud_lines) * 22 + 5),
            (15, 15, 15),
            -1,
        )
        cv2.rectangle(
            annotated,
            (banner_x - 10, banner_y - 15),
            (annotated.shape[1] - 15, banner_y + len(hud_lines) * 22 + 5),
            (0, 255, 200),
            1,
        )

        for i, line in enumerate(hud_lines):
            line_color = (0, 255, 200) if "SPEED" in line else ((0, 215, 255) if tracking_result.active_count > 0 else (180, 180, 180))
            cv2.putText(
                annotated,
                line,
                (banner_x, banner_y + i * 22 + 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                line_color,
                1,
                cv2.LINE_AA,
            )

        return annotated
