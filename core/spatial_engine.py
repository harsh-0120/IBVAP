"""
IBVAP Spatial Analytics Engine
Evaluates spatial relationships between tracked targets (using ground-plane feet points)
and configured virtual boundaries (polygon restricted zones and directional tripwires).
Decoupled from server, UI, and database layers.
"""

import enum
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import cv2
import numpy as np
import yaml
from shapely.geometry import LineString, Point, Polygon

from core.tracker import Track

logger = logging.getLogger("ibvap.spatial")


class SpatialEventType(str, enum.Enum):
    """Types of spatial boundary violation events."""
    ZONE_INTRUSION = "ZONE_INTRUSION"
    TRIPWIRE_CROSSING = "TRIPWIRE_CROSSING"


class ZoneState(str, enum.Enum):
    """Spatial presence state relative to a restricted zone."""
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"


class CrossingDirection(str, enum.Enum):
    """Direction of linear tripwire boundary crossing."""
    LEFT_TO_RIGHT = "LEFT_TO_RIGHT"
    RIGHT_TO_LEFT = "RIGHT_TO_LEFT"
    UNKNOWN = "UNKNOWN"


@dataclass
class PolygonZone:
    """Configurable polygon restricted area."""
    id: str
    name: str
    points: List[Tuple[float, float]]
    _polygon: Polygon = field(init=False, repr=False)

    def __post_init__(self):
        if len(self.points) < 3:
            raise ValueError(f"Polygon zone '{self.id}' must have at least 3 points.")
        self._polygon = Polygon(self.points)

    def contains_point(self, pt: Tuple[float, float]) -> bool:
        """
        Check if ground-contact point is inside or touching the polygon boundary.
        Uses Shapely for precision computational geometry.
        """
        p = Point(pt[0], pt[1])
        # intersects checks interior and boundary (covers contains and touches)
        return bool(self._polygon.intersects(p))


@dataclass
class Tripwire:
    """Configurable directional linear tripwire."""
    id: str
    name: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    _line: LineString = field(init=False, repr=False)

    def __post_init__(self):
        self._line = LineString([self.start, self.end])

    def check_crossing(
        self,
        p_prev: Tuple[float, float],
        p_curr: Tuple[float, float],
    ) -> Tuple[bool, CrossingDirection]:
        """
        Determine if target trajectory segment (p_prev -> p_curr) crossed the tripwire,
        and calculate the crossing direction relative to directed vector start -> end.
        """
        traj_line = LineString([p_prev, p_curr])

        # Fast geometric segment intersection test
        if not self._line.intersects(traj_line):
            return False, CrossingDirection.UNKNOWN

        # Vector cross-product orientation test relative to directed vector AB (start -> end)
        # cross(AB, AP) = (Bx - Ax) * (Py - Ay) - (By - Ay) * (Px - Ax)
        ax, ay = self.start
        bx, by = self.end
        dx = bx - ax
        dy = by - ay

        cross_prev = dx * (p_prev[1] - ay) - dy * (p_prev[0] - ax)
        cross_curr = dx * (p_curr[1] - ay) - dy * (p_curr[0] - ax)

        # Left to Right: started on the left of vector AB (>0), crossed to right (<=0)
        if cross_prev > 0 and cross_curr <= 0:
            return True, CrossingDirection.LEFT_TO_RIGHT
        # Right to Left: started on the right of vector AB (<0), crossed to left (>=0)
        elif cross_prev < 0 and cross_curr >= 0:
            return True, CrossingDirection.RIGHT_TO_LEFT
        elif cross_prev == 0 and cross_curr != 0:
            direction = CrossingDirection.LEFT_TO_RIGHT if cross_curr < 0 else CrossingDirection.RIGHT_TO_LEFT
            return True, direction
        elif cross_curr == 0 and cross_prev != 0:
            direction = CrossingDirection.LEFT_TO_RIGHT if cross_prev > 0 else CrossingDirection.RIGHT_TO_LEFT
            return True, direction

        return True, CrossingDirection.UNKNOWN


@dataclass
class SpatialEvent:
    """Structured security event generated upon perimeter breach."""
    event_type: SpatialEventType
    track_id: int
    zone_id: str
    zone_name: str
    object_type: str = "person"
    frame_index: int = 0
    timestamp: float = 0.0
    feet_point: Tuple[float, float] = (0.0, 0.0)
    direction: Optional[CrossingDirection] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to structured dictionary."""
        return {
            "event_type": self.event_type.value,
            "track_id": int(self.track_id),
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "object_type": self.object_type,
            "frame_index": int(self.frame_index),
            "timestamp": round(float(self.timestamp), 3),
            "feet_point": [round(self.feet_point[0], 2), round(self.feet_point[1], 2)],
            "direction": self.direction.value if self.direction else None,
        }


@dataclass
class SpatialConfig:
    """Configuration for spatial analytics engine."""
    enabled: bool = True
    cooldown_sec: float = 5.0
    min_track_frames: int = 2
    zones: List[PolygonZone] = field(default_factory=list)
    tripwires: List[Tripwire] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "SpatialConfig":
        """Load spatial configuration from YAML."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        sp_cfg: Dict[str, Any] = data.get("spatial", {})
        enabled = bool(sp_cfg.get("enabled", True))
        cooldown_sec = float(sp_cfg.get("cooldown_sec", 5.0))
        min_track_frames = int(sp_cfg.get("min_track_frames", 2))

        zones = []
        for z in sp_cfg.get("zones", []):
            pts = [(float(p[0]), float(p[1])) for p in z.get("points", [])]
            zones.append(PolygonZone(id=z["id"], name=z.get("name", z["id"]), points=pts))

        tripwires = []
        for t in sp_cfg.get("tripwires", []):
            start = (float(t["start"][0]), float(t["start"][1]))
            end = (float(t["end"][0]), float(t["end"][1]))
            tripwires.append(
                Tripwire(id=t["id"], name=t.get("name", t["id"]), start=start, end=end)
            )

        return cls(
            enabled=enabled,
            cooldown_sec=cooldown_sec,
            min_track_frames=min_track_frames,
            zones=zones,
            tripwires=tripwires,
        )


class SpatialEngine:
    """
    Spatial reasoning engine for border surveillance.
    Operates on Track objects, maintains per-track zone presence state machines,
    debounces events, and generates breach alerts for polygon intrusions and tripwire crossings.
    """

    def __init__(self, config: Optional[SpatialConfig] = None):
        self.config = config or SpatialConfig()
        self.zones: List[PolygonZone] = list(self.config.zones)
        self.tripwires: List[Tripwire] = list(self.config.tripwires)

        # State tracking: (track_id, zone_id) -> ZoneState
        self._zone_states: Dict[Tuple[int, str], ZoneState] = {}

        # Cooldown timer: (track_id, boundary_id) -> last_event_timestamp
        self._last_event_timestamps: Dict[Tuple[int, str], float] = {}

        # Previous feet point: track_id -> (x, y)
        self._previous_feet_points: Dict[int, Tuple[float, float]] = {}

        # Consecutive frame confirmation count: track_id -> frame_count
        self._track_lifespans: Dict[int, int] = {}

        # Event counters
        self.total_intrusions = 0
        self.total_crossings = 0

    def add_zone(self, zone: PolygonZone) -> None:
        """Add a polygon restricted zone dynamically."""
        self.zones.append(zone)

    def add_tripwire(self, tripwire: Tripwire) -> None:
        """Add a tripwire dynamically."""
        self.tripwires.append(tripwire)

    def clear_boundaries(self) -> None:
        """Remove all configured zones and tripwires."""
        self.zones.clearVelocity = []
        self.zones.clear()
        self.tripwires.clear()
        self.reset()

    def reset(self) -> None:
        """Reset internal tracking state and debounce timers."""
        self._zone_states.clear()
        self._last_event_timestamps.clear()
        self._previous_feet_points.clear()
        self._track_lifespans.clear()
        self.total_intrusions = 0
        self.total_crossings = 0

    def cleanup_disappeared_tracks(self, active_track_ids: Set[int]) -> None:
        """Remove state for tracks that have vanished from the camera view."""
        stale_zone_keys = [k for k in self._zone_states if k[0] not in active_track_ids]
        for k in stale_zone_keys:
            del self._zone_states[k]

        stale_timer_keys = [k for k in self._last_event_timestamps if k[0] not in active_track_ids]
        for k in stale_timer_keys:
            del self._last_event_timestamps[k]

        stale_feet_keys = [tid for tid in self._previous_feet_points if tid not in active_track_ids]
        for tid in stale_feet_keys:
            del self._previous_feet_points[tid]

        stale_lifespan_keys = [tid for tid in self._track_lifespans if tid not in active_track_ids]
        for tid in stale_lifespan_keys:
            del self._track_lifespans[tid]

    def process_tracks(
        self,
        tracks: List[Track],
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> Tuple[List[SpatialEvent], Dict[int, Dict[str, ZoneState]]]:
        """
        Evaluate all active tracks against configured polygon zones and tripwires.

        Returns:
            Tuple of:
            - List[SpatialEvent]: New security breach events triggered this frame.
            - Dict[int, Dict[str, ZoneState]]: Active zone membership status per track.
        """
        if not self.config.enabled:
            return [], {}

        events: List[SpatialEvent] = []
        active_states: Dict[int, Dict[str, ZoneState]] = {}
        current_active_ids = {t.track_id for t in tracks}

        for track in tracks:
            tid = track.track_id
            feet_pt = track.feet_point  # Bottom-center ground contact point

            # Track lifespan confirmation
            self._track_lifespans[tid] = self._track_lifespans.get(tid, 0) + 1
            lifespan = self._track_lifespans[tid]
            active_states[tid] = {}

            # -------------------------------------------------------------
            # 1. EVALUATE POLYGON RESTRICTED ZONES
            # -------------------------------------------------------------
            for zone in self.zones:
                is_inside = zone.contains_point(feet_pt)
                current_state = ZoneState.INSIDE if is_inside else ZoneState.OUTSIDE
                active_states[tid][zone.id] = current_state

                prev_state = self._zone_states.get((tid, zone.id), ZoneState.OUTSIDE)

                # INTRUSION TRANSITION: Generate event ONLY when OUTSIDE -> INSIDE
                if prev_state == ZoneState.OUTSIDE and current_state == ZoneState.INSIDE:
                    if lifespan >= self.config.min_track_frames:
                        last_event_ts = self._last_event_timestamps.get((tid, zone.id))
                        if last_event_ts is None or (timestamp - last_event_ts) >= self.config.cooldown_sec:
                            event = SpatialEvent(
                                event_type=SpatialEventType.ZONE_INTRUSION,
                                track_id=tid,
                                zone_id=zone.id,
                                zone_name=zone.name,
                                object_type=getattr(track, "class_name", "person"),
                                frame_index=frame_index,
                                timestamp=timestamp,
                                feet_point=feet_pt,
                                direction=None,
                            )
                            events.append(event)
                            self.total_intrusions += 1
                            self._last_event_timestamps[(tid, zone.id)] = timestamp
                            logger.warning(
                                f"BREACH ALERT: Track #{tid} ({event.object_type}) intruded into Zone '{zone.name}' "
                                f"at feet position {feet_pt} (Frame: {frame_index})"
                            )

                # Update zone presence state
                self._zone_states[(tid, zone.id)] = current_state

            # -------------------------------------------------------------
            # 2. EVALUATE LINEAR TRIPWIRES
            # -------------------------------------------------------------
            prev_feet = self._previous_feet_points.get(tid)
            if prev_feet is not None:
                for tripwire in self.tripwires:
                    crossed, direction = tripwire.check_crossing(prev_feet, feet_pt)
                    if crossed:
                        last_cross_ts = self._last_event_timestamps.get((tid, tripwire.id))
                        if last_cross_ts is None or (timestamp - last_cross_ts) >= self.config.cooldown_sec:
                            event = SpatialEvent(
                                event_type=SpatialEventType.TRIPWIRE_CROSSING,
                                track_id=tid,
                                zone_id=tripwire.id,
                                zone_name=tripwire.name,
                                object_type=getattr(track, "class_name", "person"),
                                frame_index=frame_index,
                                timestamp=timestamp,
                                feet_point=feet_pt,
                                direction=direction,
                            )
                            events.append(event)
                            self.total_crossings += 1
                            self._last_event_timestamps[(tid, tripwire.id)] = timestamp
                            logger.warning(
                                f"TRIPWIRE CROSSED: Track #{tid} ({event.object_type}) crossed '{tripwire.name}' "
                                f"Direction: {direction.value} at {feet_pt} (Frame: {frame_index})"
                            )

            # Record current feet point for trajectory analysis on next frame
            self._previous_feet_points[tid] = feet_pt

        # Clean up memory for targets that exited the frame
        self.cleanup_disappeared_tracks(current_active_ids)

        return events, active_states

    def annotate_frame(
        self,
        frame: np.ndarray,
        tracks: List[Track],
        events: List[SpatialEvent],
        active_states: Dict[int, Dict[str, ZoneState]],
        recent_event_banner_duration_sec: float = 3.0,
    ) -> np.ndarray:
        """
        Draw comprehensive tactical spatial boundaries, intruder alerts,
        and HUD status on the surveillance video canvas.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # 1. Draw Polygon Zones
        for zone in self.zones:
            pts = np.array([[int(p[0]), int(p[1])] for p in zone.points], dtype=np.int32)

            # Check if any active track is inside this zone
            is_breached = any(
                states.get(zone.id) == ZoneState.INSIDE
                for states in active_states.values()
            )

            # Tactical color: Crimson Red if breached, Amber/Green if secure
            fill_color = (0, 0, 180) if is_breached else (40, 120, 40)
            border_color = (0, 0, 255) if is_breached else (60, 220, 60)

            # Draw semi-transparent filled polygon
            overlay = annotated.copy()
            cv2.fillPoly(overlay, [pts], fill_color)
            cv2.addWeighted(overlay, 0.25, annotated, 0.75, 0, annotated)

            # Outline
            cv2.polylines(annotated, [pts], isClosed=True, color=border_color, thickness=2, lineType=cv2.LINE_AA)

            # Label banner on top of polygon
            min_y = min(p[1] for p in zone.points)
            avg_x = sum(p[0] for p in zone.points) / len(zone.points)
            status_text = f"ZONE: {zone.name.upper()} [{'BREACH' if is_breached else 'SECURE'}]"
            cv2.putText(
                annotated,
                status_text,
                (int(avg_x - 130), int(min_y + 25)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                border_color,
                1,
                cv2.LINE_AA,
            )

        # 2. Draw Tripwires
        for tripwire in self.tripwires:
            sx, sy = int(tripwire.start[0]), int(tripwire.start[1])
            ex, ey = int(tripwire.end[0]), int(tripwire.end[1])

            # Vibrant Cyan/Orange line with endpoint markers
            line_color = (0, 140, 255)
            cv2.line(annotated, (sx, sy), (ex, ey), line_color, 2, cv2.LINE_AA)
            cv2.circle(annotated, (sx, sy), 5, (0, 255, 255), -1)
            cv2.circle(annotated, (ex, ey), 5, (0, 255, 255), -1)

            mid_x, mid_y = (sx + ex) // 2, (sy + ey) // 2
            cv2.putText(
                annotated,
                f"TRIPWIRE: {tripwire.name.upper()}",
                (mid_x - 90, mid_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                line_color,
                1,
                cv2.LINE_AA,
            )

        # 3. Highlight Intruder Tracks
        for track in tracks:
            tid = track.track_id
            states = active_states.get(tid, {})
            is_intruder = any(st == ZoneState.INSIDE for st in states.values())

            if is_intruder:
                # Highlight bounding box in Red
                x1, y1, x2, y2 = track.bbox.as_int_tuple()
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)

                alert_tag = f"ALERT: INTRUDER #{tid} [RESTRICTED]"
                (tw, th), _ = cv2.getTextSize(alert_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, max(0, y1)), (0, 0, 255), -1)
                cv2.putText(
                    annotated,
                    alert_tag,
                    (x1 + 4, max(th + 2, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        # 4. Live Breach Flash Banner for Frame Events
        if events:
            top_event = events[0]
            banner_bg = (0, 0, 200)
            cv2.rectangle(annotated, (0, 0), (w, 40), banner_bg, -1)
            if top_event.event_type == SpatialEventType.ZONE_INTRUSION:
                msg = f"*** SECURITY ALARM: ZONE INTRUSION DETECTED | PERSON #{top_event.track_id} IN {top_event.zone_name.upper()} ***"
            else:
                msg = f"*** PERIMETER BREACH: TRIPWIRE CROSSED | PERSON #{top_event.track_id} ({top_event.direction.value}) ***"
            cv2.putText(
                annotated,
                msg,
                (int(w * 0.08), 26),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        # 5. OSD Summary Counters at Bottom-Left
        summary_y = h - 50
        cv2.rectangle(annotated, (20, summary_y - 15), (320, h - 15), (20, 20, 20), -1)
        cv2.rectangle(annotated, (20, summary_y - 15), (320, h - 15), (0, 160, 255), 1)
        cv2.putText(
            annotated,
            f"ZONE INTRUSIONS: {self.total_intrusions}",
            (30, summary_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 100, 255) if self.total_intrusions > 0 else (200, 200, 200),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"TRIPWIRE CROSSINGS: {self.total_crossings}",
            (30, summary_y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 220, 255) if self.total_crossings > 0 else (200, 200, 200),
            1,
            cv2.LINE_AA,
        )

        return annotated
