"""
IBVAP Real-Time Overlay Renderer
Modular computer vision annotation layer for surveillance video feeds.
Renders tactical bounding boxes, persistent ByteTrack IDs, detection confidence,
ground contact points, and trajectory trails while strictly preserving frame integrity.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import yaml

from core.tracker import Track, get_track_color

logger = logging.getLogger("ibvap.overlay")


@dataclass
class OverlayConfig:
    """Configuration for tactical video overlays."""
    show_box: bool = True
    show_track_id: bool = True
    show_confidence: bool = True
    show_feet: bool = True
    show_trajectory: bool = True
    max_trajectory_len: int = 20
    box_thickness: int = 2
    font_scale: float = 0.5
    jpeg_quality: int = 80

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "OverlayConfig":
        """Load overlay configuration from YAML file."""
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        cfg: Dict[str, Any] = data.get("overlay", {})
        return cls(
            show_box=bool(cfg.get("show_box", True)),
            show_track_id=bool(cfg.get("show_track_id", True)),
            show_confidence=bool(cfg.get("show_confidence", True)),
            show_feet=bool(cfg.get("show_feet", True)),
            show_trajectory=bool(cfg.get("show_trajectory", True)),
            max_trajectory_len=int(cfg.get("max_trajectory_len", 20)),
            box_thickness=int(cfg.get("box_thickness", 2)),
            font_scale=float(cfg.get("font_scale", 0.5)),
            jpeg_quality=int(cfg.get("jpeg_quality", 80)),
        )


class OverlayRenderer:
    """
    Modular surveillance overlay engine.
    Renders military/control-room style annotations on video frames.
    """

    def __init__(self, config: Optional[OverlayConfig] = None):
        self.config = config or OverlayConfig()

    def render(
        self,
        frame: np.ndarray,
        tracks: List[Track],
        fps: Optional[float] = None,
        camera_id: str = "CAM-01",
    ) -> np.ndarray:
        """
        Draw detection bounding boxes, tracking labels, and trajectory history.

        Args:
            frame: Input video frame (BGR format, dtype uint8).
            tracks: List of active Track objects from ByteTrack.
            fps: Optional processing frame rate for telemetry banner.
            camera_id: Camera identifier for on-screen HUD.

        Returns:
            Annotated BGR frame with identical dimensions and dtype.
        """
        if frame is None or frame.size == 0:
            return frame

        # Create a writable copy to preserve input immutability
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        for track in tracks:
            is_vehicle = getattr(track, "object_type", "person") == "vehicle"
            # Tactical Amber/Gold for vehicles, deterministic palette for persons
            color = (0, 180, 255) if is_vehicle else get_track_color(track.track_id)
            x1, y1, x2, y2 = track.bbox.as_int_tuple()

            # Clamp coordinates within frame boundaries
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            # 1. Trajectory breadcrumb trail
            if self.config.show_trajectory and track.trajectory:
                trail = track.trajectory[-self.config.max_trajectory_len:]
                if len(trail) > 1:
                    for i in range(1, len(trail)):
                        pt1 = (int(trail[i - 1][0]), int(trail[i - 1][1]))
                        pt2 = (int(trail[i][0]), int(trail[i][1]))
                        # Alpha fade: newer points are thicker
                        thickness = 1 if i < len(trail) // 2 else 2
                        cv2.line(annotated, pt1, pt2, color, thickness, cv2.LINE_AA)

            # 2. Bounding Box
            if self.config.show_box:
                cv2.rectangle(
                    annotated,
                    (x1, y1),
                    (x2, y2),
                    color,
                    self.config.box_thickness,
                    cv2.LINE_AA,
                )

                # Corner corner-brackets for high-contrast tactical feel
                corner_len = min(15, (x2 - x1) // 4, (y2 - y1) // 4)
                if corner_len > 3:
                    # Top-left
                    cv2.line(annotated, (x1, y1), (x1 + corner_len, y1), (255, 255, 255), 2)
                    cv2.line(annotated, (x1, y1), (x1, y1 + corner_len), (255, 255, 255), 2)
                    # Bottom-right
                    cv2.line(annotated, (x2, y2), (x2 - corner_len, y2), (255, 255, 255), 2)
                    cv2.line(annotated, (x2, y2), (x2, y2 - corner_len), (255, 255, 255), 2)

            # 3. Ground contact feet marker (bottom center)
            if self.config.show_feet:
                fx, fy = int(track.feet_point[0]), int(track.feet_point[1])
                fx = max(0, min(w - 1, fx))
                fy = max(0, min(h - 1, fy))
                marker_color = (0, 200, 255) if is_vehicle else (0, 255, 255)
                cv2.circle(annotated, (fx, fy), 4, marker_color, -1, cv2.LINE_AA)
                cv2.circle(annotated, (fx, fy), 7, marker_color, 1, cv2.LINE_AA)

            # 4. Identification Badge (CLASS #ID CONF%)
            class_label = (track.class_name if track.class_name else "PERSON").upper()
            badge_parts = [class_label]
            if self.config.show_track_id:
                badge_parts.append(f"#{track.track_id}")
            if self.config.show_confidence:
                badge_parts.append(f"{track.confidence:.0%}")
            label = " ".join(badge_parts)

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = self.config.font_scale
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 1)

            # Position badge above bounding box, or inside if near top edge
            badge_y2 = y1 if y1 - th - 8 >= 0 else y1 + th + 10
            badge_y1 = badge_y2 - th - 6
            badge_x2 = min(w, x1 + tw + 10)

            # Dark solid background for high text contrast
            cv2.rectangle(
                annotated,
                (x1, badge_y1),
                (badge_x2, badge_y2),
                (18, 24, 36),  # Dark charcoal
                cv2.FILLED,
            )
            # Accent left border on the badge
            cv2.rectangle(
                annotated,
                (x1, badge_y1),
                (x1 + 3, badge_y2),
                color,
                cv2.FILLED,
            )

            # Text
            cv2.putText(
                annotated,
                label,
                (x1 + 6, badge_y2 - 4),
                font,
                font_scale,
                (240, 240, 240),
                1,
                cv2.LINE_AA,
            )

        # 5. On-Screen Tactical HUD Watermark (Top Left)
        person_count = sum(1 for t in tracks if getattr(t, "object_type", "person") == "person")
        vehicle_count = sum(1 for t in tracks if getattr(t, "object_type", "person") == "vehicle")
        if vehicle_count > 0:
            hud_text = f"CAM: {camera_id} | AI: YOLO11n + ByteTrack | TARGETS: {len(tracks)} (P:{person_count} V:{vehicle_count})"
        else:
            hud_text = f"CAM: {camera_id} | AI: YOLO11n + ByteTrack | TARGETS: {len(tracks)}"

        if fps is not None and fps > 0:
            hud_text += f" | {fps:.1f} FPS"

        cv2.rectangle(annotated, (8, 8), (min(w - 8, 8 + len(hud_text) * 8 + 16), 30), (12, 16, 24), -1)
        cv2.rectangle(annotated, (8, 8), (min(w - 8, 8 + len(hud_text) * 8 + 16), 30), (40, 55, 80), 1)
        cv2.circle(annotated, (20, 19), 4, (0, 255, 0), -1)
        cv2.putText(
            annotated,
            hud_text,
            (30, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )

        return annotated

    def encode_jpeg(self, frame: np.ndarray) -> bytes:
        """
        Encode BGR frame as JPEG image bytes.

        Returns:
            bytes: Encoded JPEG image bytes.
        """
        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality],
        )
        if not success:
            raise RuntimeError("OpenCV JPEG encoding failed.")
        return encoded.tobytes()
