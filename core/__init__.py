"""IBVAP Core Package: Video Analytics & Streaming Components."""
from core.stream_reader import StreamReader, StreamConfig, StreamSourceType
from core.detector import (
    BaseDetector,
    PersonDetector,
    DetectorConfig,
    BoundingBox,
    Detection,
    DetectionResult,
)
from core.tracker import (
    BaseTracker,
    ByteTrackTracker,
    TrackerConfig,
    Track,
    TrackingResult,
    get_track_color,
)
from core.spatial_engine import (
    SpatialEngine,
    SpatialConfig,
    PolygonZone,
    Tripwire,
    SpatialEvent,
    SpatialEventType,
    ZoneState,
    CrossingDirection,
)
from core.incident_manager import (
    IncidentManager,
    IncidentRecord,
    IncidentConfig,
)

__all__ = [
    "StreamReader",
    "StreamConfig",
    "StreamSourceType",
    "BaseDetector",
    "PersonDetector",
    "DetectorConfig",
    "BoundingBox",
    "Detection",
    "DetectionResult",
    "BaseTracker",
    "ByteTrackTracker",
    "TrackerConfig",
    "Track",
    "TrackingResult",
    "get_track_color",
    "SpatialEngine",
    "SpatialConfig",
    "PolygonZone",
    "Tripwire",
    "SpatialEvent",
    "SpatialEventType",
    "ZoneState",
    "CrossingDirection",
    "IncidentManager",
    "IncidentRecord",
    "IncidentConfig",
]
