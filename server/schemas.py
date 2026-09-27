"""
IBVAP API Schemas (Pydantic models)
Provides structured request and response contracts for the FastAPI REST interface.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response contract."""
    status: str = Field(default="online", description="Service health state")
    service: str = Field(default="IBVAP", description="Platform service name")
    version: str = Field(default="0.1.0", description="API version")


class IncidentResponse(BaseModel):
    """Structured security breach incident payload."""
    id: int = Field(..., description="Unique incident ID")
    timestamp: float = Field(..., description="Unix epoch timestamp")
    iso_timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    camera_id: str = Field(..., description="Originating camera node identifier")
    event_type: str = Field(..., description="Security event classification (ZONE_INTRUSION / TRIPWIRE_CROSSING)")
    track_id: int = Field(..., description="Persistent tracking ID of the target")
    object_type: str = Field(default="person", description="Detected object class")
    zone_id: str = Field(..., description="Identifier of the breached boundary")
    zone_name: str = Field(..., description="Human-readable boundary name")
    direction: Optional[str] = Field(default=None, description="Crossing orientation (LEFT_TO_RIGHT / RIGHT_TO_LEFT)")
    confidence: Optional[float] = Field(default=None, description="Detector confidence score")
    frame_index: int = Field(..., description="Sequential video frame index")
    feet_point: List[float] = Field(..., description="[x, y] ground-contact feet coordinate")
    snapshot_path: str = Field(..., description="Filesystem path to the forensic snapshot JPEG")


class IncidentListResponse(BaseModel):
    """Paginated collection of security incidents."""
    total: int = Field(..., description="Total matching records count")
    limit: int = Field(..., description="Pagination page limit")
    offset: int = Field(..., description="Pagination page offset")
    incidents: List[IncidentResponse] = Field(default_factory=list, description="List of incidents")


class StatsResponse(BaseModel):
    """Surveillance telemetry and historical summary statistics."""
    total_incidents: int = Field(..., description="Total recorded security incidents")
    zone_intrusions: int = Field(..., description="Total polygon restricted zone breaches")
    tripwire_crossings: int = Field(..., description="Total linear tripwire crossings")
    active_camera_count: int = Field(default=1, description="Number of active surveillance camera streams")
    camera_id: str = Field(..., description="Primary camera node identifier")


class CameraResponse(BaseModel):
    """Surveillance camera stream metadata."""
    camera_id: str = Field(..., description="Unique camera node identifier")
    name: Optional[str] = Field(default=None, description="Human-readable camera label")
    source_type: str = Field(..., description="Video stream type (file, webcam, rtsp)")
    status: str = Field(..., description="Operational status (online, offline, standby, ready)")
    operational_status: Optional[str] = Field(default=None, description="Detailed display status (ONLINE / PROCESSING, READY, OFFLINE, ERROR)")
    resolution: Optional[str] = Field(default=None, description="Camera native resolution")
    source_fps: Optional[float] = Field(default=None, description="Native source FPS")
    processing_fps: Optional[float] = Field(default=None, description="Live AI processing FPS")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Stream technical properties")


class TelemetryPayload(BaseModel):
    """Real-time system and camera telemetry broadcast."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message_type: str = Field(default="TELEMETRY")
    camera_id: str
    camera_name: str
    camera_status: str
    processing_fps: float
    source_fps: float
    active_tracks: int
    persons: int
    vehicles: int
    cars: int
    motorcycles: int
    buses: int
    trucks: int
    total_incidents: int
    zone_intrusions: int
    tripwire_crossings: int
    loop_count: Optional[int] = 0



class PolygonZoneSchema(BaseModel):
    """Polygon restricted area definition."""
    id: str = Field(..., description="Unique zone identifier")
    name: str = Field(..., description="Human-readable zone label")
    points: List[List[float]] = Field(..., description="List of [x, y] boundary vertices")


class TripwireSchema(BaseModel):
    """Linear directional tripwire definition."""
    id: str = Field(..., description="Unique tripwire identifier")
    name: str = Field(..., description="Human-readable tripwire label")
    start: List[float] = Field(..., description="[x, y] segment start coordinate")
    end: List[float] = Field(..., description="[x, y] segment end coordinate")


class ZoneResponse(BaseModel):
    """Configured spatial virtual boundaries."""
    zones: List[PolygonZoneSchema] = Field(default_factory=list)
    tripwires: List[TripwireSchema] = Field(default_factory=list)


class ZoneCreateRequest(BaseModel):
    """Request payload to register a new spatial boundary."""
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str = Field(..., description="'polygon' or 'tripwire'")
    points: Optional[List[List[float]]] = None
    start: Optional[List[float]] = None
    end: Optional[List[float]] = None


class RealtimeEvent(BaseModel):
    """Real-time security event payload streamed to WebSocket clients."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message_type: str = Field(default="NEW_INCIDENT", description="Notification classification")
    id: Optional[int] = Field(default=None, description="Database record ID if persisted")
    incident_id: Optional[int] = Field(default=None, description="Database record ID")
    timestamp: float = Field(..., description="Unix epoch timestamp")
    iso_timestamp: Optional[str] = Field(default=None, description="ISO 8601 UTC timestamp")
    camera_id: str = Field(..., description="Camera identifier")
    event_type: str = Field(..., description="Breach classification (ZONE_INTRUSION / TRIPWIRE_CROSSING)")
    track_id: int = Field(..., description="Persistent tracking ID of target")
    object_type: str = Field(default="person", description="Detected object class")
    zone_id: str = Field(..., description="Breached zone/tripwire identifier")
    zone_name: str = Field(..., description="Human-readable boundary name")
    direction: Optional[str] = Field(default=None, description="Crossing direction if tripwire")
    confidence: Optional[float] = Field(default=None, description="Detector confidence score")
    frame_index: int = Field(..., description="Video frame index")
    feet_point: List[float] = Field(..., description="[x, y] ground contact coordinate")
    snapshot_path: str = Field(..., description="Path to forensic snapshot file")

