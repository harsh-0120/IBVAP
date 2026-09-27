"""
IBVAP REST API Endpoints
Provides clean HTTP routing for health checks, incident retrieval,
historical statistics, camera status, spatial boundaries, and forensic snapshots.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import yaml

from server.database import IncidentDatabase, IncidentModel
from server.schemas import (
    AnalyticsResponse,
    CameraResponse,
    HealthResponse,
    IncidentListResponse,
    IncidentResponse,
    PolygonZoneSchema,
    StatsResponse,
    TripwireSchema,
    VideoUploadResponse,
    ZoneCreateRequest,
    ZoneResponse,
)

logger = logging.getLogger("ibvap.routes")

router = APIRouter(prefix="/api", tags=["IBVAP Surveillance API"])


def get_database(request: Request) -> IncidentDatabase:
    """Dependency provider for the IncidentDatabase instance."""
    if hasattr(request.app.state, "db") and request.app.state.db is not None:
        return request.app.state.db
    # Fallback to default
    return IncidentDatabase("data/events.db")


def get_config(request: Request) -> Dict[str, Any]:
    """Dependency provider for system configuration dictionary."""
    if hasattr(request.app.state, "config") and request.app.state.config is not None:
        return request.app.state.config

    cfg_path = Path("config/default_config.yaml")
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# --------------------------------------------------------------------------
# 1. Health Endpoint
# --------------------------------------------------------------------------
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
    description="Returns current operational status of the IBVAP platform.",
)
def get_health() -> HealthResponse:
    return HealthResponse(status="online", service="IBVAP", version="0.1.0")


# --------------------------------------------------------------------------
# 2. Incident & Event Endpoints
# --------------------------------------------------------------------------
@router.get(
    "/events",
    response_model=IncidentListResponse,
    summary="Query Security Incidents",
    description="Retrieve paginated security incident records with optional filters for event type and camera.",
)
def list_events(
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type (e.g. ZONE_INTRUSION)"),
    camera_id: Optional[str] = Query(default=None, description="Filter by camera identifier"),
    db: IncidentDatabase = Depends(get_database),
) -> IncidentListResponse:
    if event_type:
        records = db.get_incidents_by_event_type(event_type=event_type, limit=limit)
        total = len(records)
    elif camera_id:
        records = db.get_incidents_by_camera(camera_id=camera_id, limit=limit)
        total = len(records)
    else:
        records = db.get_recent_incidents(limit=limit, offset=offset)
        total = db.count_incidents()

    items = [
        IncidentResponse(
            id=r.id,
            timestamp=r.timestamp,
            iso_timestamp=r.iso_timestamp,
            camera_id=r.camera_id,
            event_type=r.event_type,
            track_id=r.track_id,
            object_type=r.object_type,
            zone_id=r.zone_id,
            zone_name=r.zone_name,
            direction=r.direction,
            confidence=r.confidence,
            frame_index=r.frame_index,
            feet_point=[r.feet_x, r.feet_y],
            snapshot_path=r.snapshot_path,
        )
        for r in records
    ]

    return IncidentListResponse(total=total, limit=limit, offset=offset, incidents=items)


@router.get(
    "/events/{event_id}",
    response_model=IncidentResponse,
    summary="Get Incident By ID",
    description="Retrieve full details for a single recorded security incident.",
)
def get_event_by_id(
    event_id: int,
    db: IncidentDatabase = Depends(get_database),
) -> IncidentResponse:
    if event_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event ID: {event_id}. Must be a positive integer.",
        )

    record = db.get_incident_by_id(event_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Security incident with ID #{event_id} was not found.",
        )

    return IncidentResponse(
        id=record.id,
        timestamp=record.timestamp,
        iso_timestamp=record.iso_timestamp,
        camera_id=record.camera_id,
        event_type=record.event_type,
        track_id=record.track_id,
        object_type=record.object_type,
        zone_id=record.zone_id,
        zone_name=record.zone_name,
        direction=record.direction,
        confidence=record.confidence,
        frame_index=record.frame_index,
        feet_point=[record.feet_x, record.feet_y],
        snapshot_path=record.snapshot_path,
    )


@router.get(
    "/events/{event_id}/snapshot",
    summary="Download Forensic Snapshot",
    description="Retrieve the physical JPEG snapshot image associated with a security incident.",
)
def get_event_snapshot(
    event_id: int,
    db: IncidentDatabase = Depends(get_database),
    config: Dict[str, Any] = Depends(get_config),
) -> FileResponse:
    record = db.get_incident_by_id(event_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident #{event_id} not found.",
        )

    snapshot_file = Path(record.snapshot_path).resolve()
    if not snapshot_file.exists() or not snapshot_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot file for incident #{event_id} not found on disk.",
        )

    # Security check: Ensure file resides within authorized data directory
    configured_dir = Path(config.get("incident", {}).get("snapshot_dir", "data/snapshots")).resolve()
    # Permit if inside configured snapshot dir or data dir
    try:
        data_root = Path("data").resolve()
        snapshot_file.relative_to(data_root)
    except ValueError:
        try:
            snapshot_file.relative_to(configured_dir)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to requested snapshot path is restricted.",
            )

    return FileResponse(
        path=str(snapshot_file),
        media_type="image/jpeg",
        filename=snapshot_file.name,
    )


# --------------------------------------------------------------------------
# 3. Statistics Endpoint
# --------------------------------------------------------------------------
@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Surveillance System Statistics",
    description="Aggregated incident counts, active cameras, and platform metrics.",
)
def get_stats(
    db: IncidentDatabase = Depends(get_database),
    config: Dict[str, Any] = Depends(get_config),
) -> StatsResponse:
    total = db.count_incidents()
    type_counts = db.count_by_event_type()
    zone_intrusions = type_counts.get("ZONE_INTRUSION", 0)
    tripwire_crossings = type_counts.get("TRIPWIRE_CROSSING", 0)

    cam_id = config.get("incident", {}).get("camera_id", "CAM-01")

    return StatsResponse(
        total_incidents=total,
        zone_intrusions=zone_intrusions,
        tripwire_crossings=tripwire_crossings,
        active_camera_count=1,
        camera_id=cam_id,
    )


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Surveillance Analytics Summary",
    description="Returns aggregated incident analytics, time series distribution, and camera status for a specified time range (24h, 7d, all).",
)
def get_analytics(
    time_range: str = Query(
        default="all",
        pattern="^(24h|7d|all)$",
        description="Aggregation time window: 24h, 7d, or all",
    ),
    db: IncidentDatabase = Depends(get_database),
) -> AnalyticsResponse:
    summary = db.get_analytics_summary(time_range=time_range)

    try:
        from core.camera_registry import list_cameras as get_registered_cameras
        from core.live_stream_manager import live_stream_manager

        registered = get_registered_cameras()
        statuses = live_stream_manager.get_all_camera_statuses()
        active_id = live_stream_manager.active_camera_id or "CAM-01"

        cam_status_dist: Dict[str, int] = {}
        online_count = 0
        for cam in registered:
            exists = cam.exists_on_disk
            is_active = (cam.camera_id == active_id) and exists
            if not exists:
                stat = "offline"
            elif is_active:
                stat = "online"
                online_count += 1
            else:
                stat = "ready"
            cam_status_dist[stat] = cam_status_dist.get(stat, 0) + 1

        summary["camera_status_distribution"] = cam_status_dist
        summary["total_cameras"] = len(registered)
        summary["online_cameras"] = online_count
    except Exception as exc:
        logger.warning(f"Could not retrieve camera status for analytics: {exc}")

    return AnalyticsResponse(**summary)


# --------------------------------------------------------------------------
# 4. Cameras Endpoint
# --------------------------------------------------------------------------
@router.get(
    "/cameras",
    response_model=List[CameraResponse],
    summary="List Surveillance Cameras",
    description="Returns metadata and operational status for all configured camera feeds.",
)
def list_cameras() -> List[CameraResponse]:
    from core.camera_registry import list_cameras as get_registered_cameras
    from core.live_stream_manager import live_stream_manager

    active_id = live_stream_manager.active_camera_id or "CAM-01"
    telemetry = live_stream_manager.get_latest_telemetry()
    statuses = live_stream_manager.get_all_camera_statuses()
    registered = get_registered_cameras()
    result = []

    for cam in registered:
        exists = cam.exists_on_disk
        status_label = statuses.get(cam.camera_id, "READY")
        is_active = (cam.camera_id == active_id) and exists

        if not exists:
            stat = "offline"
            op_stat = "OFFLINE"
        elif is_active:
            stat = "online"
            op_stat = "ONLINE / PROCESSING"
        else:
            stat = "online"
            op_stat = "READY"

        proc_fps = telemetry.get("processing_fps") if is_active else None

        result.append(
            CameraResponse(
                camera_id=cam.camera_id,
                name=cam.name,
                source_type=cam.source_type,
                status=stat,
                operational_status=op_stat,
                resolution=cam.resolution,
                source_fps=cam.source_fps,
                processing_fps=proc_fps,
                details={
                    "name": cam.name,
                    "resolution": cam.resolution,
                    "source_fps": cam.source_fps,
                    "aspect_ratio": cam.aspect_ratio,
                    "operational_status": op_stat,
                    "source": cam.file_path,
                    "loop": True,
                    "buffer_size": 1,
                },
            )
        )
    return result


@router.post(
    "/cameras/{camera_id}/select",
    response_model=CameraResponse,
    summary="Select Active Surveillance Camera",
    description="Switches live AI inference to the specified camera and starts processing.",
)
def select_camera(camera_id: str) -> CameraResponse:
    from core.camera_registry import get_camera
    from core.live_stream_manager import live_stream_manager

    cam = get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' is not registered.",
        )
    if not cam.exists_on_disk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera source '{camera_id}' is offline on disk.",
        )

    success = live_stream_manager.switch_camera(cam.camera_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate surveillance pipeline for '{camera_id}'.",
        )

    return CameraResponse(
        camera_id=cam.camera_id,
        name=cam.name,
        source_type=cam.source_type,
        status="online",
        operational_status="ONLINE / PROCESSING",
        resolution=cam.resolution,
        source_fps=cam.source_fps,
        details={
            "name": cam.name,
            "resolution": cam.resolution,
            "source_fps": cam.source_fps,
            "operational_status": "ONLINE / PROCESSING",
        },
    )


# --------------------------------------------------------------------------
# 5. Spatial Zones Endpoints
# --------------------------------------------------------------------------
@router.get(
    "/zones",
    response_model=ZoneResponse,
    summary="Get Configured Boundaries",
    description="Retrieve active polygon restricted zones and directional tripwires.",
)
def get_zones(
    camera_id: Optional[str] = None,
    config: Dict[str, Any] = Depends(get_config),
) -> ZoneResponse:
    from core.camera_registry import get_camera

    if isinstance(camera_id, str) and camera_id.strip():
        cam = get_camera(camera_id)
        if cam and (cam.zones or cam.tripwires):

            zones = [
                PolygonZoneSchema(
                    id=z["id"],
                    name=z.get("name", z["id"]),
                    points=[[float(p[0]), float(p[1])] for p in z.get("points", [])],
                )
                for z in cam.zones
            ]
            tripwires = [
                TripwireSchema(
                    id=t["id"],
                    name=t.get("name", t["id"]),
                    start=[float(t["start"][0]), float(t["start"][1])],
                    end=[float(t["end"][0]), float(t["end"][1])],
                )
                for t in cam.tripwires
            ]
            return ZoneResponse(zones=zones, tripwires=tripwires)

    spatial_cfg = config.get("spatial", {})

    zones = []
    for z in spatial_cfg.get("zones", []):
        zones.append(
            PolygonZoneSchema(
                id=z["id"],
                name=z.get("name", z["id"]),
                points=[[float(p[0]), float(p[1])] for p in z.get("points", [])],
            )
        )

    tripwires = []
    for t in spatial_cfg.get("tripwires", []):
        tripwires.append(
            TripwireSchema(
                id=t["id"],
                name=t.get("name", t["id"]),
                start=[float(t["start"][0]), float(t["start"][1])],
                end=[float(t["end"][0]), float(t["end"][1])],
            )
        )

    return ZoneResponse(zones=zones, tripwires=tripwires)


@router.post(
    "/zones",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Spatial Boundary",
    description="Add or update a virtual fence polygon or directional tripwire.",
)
def create_zone(
    payload: ZoneCreateRequest,
    config: Dict[str, Any] = Depends(get_config),
) -> ZoneResponse:
    spatial_cfg = config.setdefault("spatial", {})

    if payload.type.lower() == "polygon":
        if not payload.points or len(payload.points) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A polygon zone requires at least 3 vertices [x, y].",
            )
        zones = spatial_cfg.setdefault("zones", [])
        # Replace if ID exists, else append
        zones = [z for z in zones if z["id"] != payload.id]
        zones.append({
            "id": payload.id,
            "name": payload.name,
            "type": "polygon",
            "points": payload.points,
        })
        spatial_cfg["zones"] = zones

    elif payload.type.lower() == "tripwire":
        if not payload.start or not payload.end or len(payload.start) != 2 or len(payload.end) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A tripwire requires valid 'start' and 'end' coordinates [x, y].",
            )
        tripwires = spatial_cfg.setdefault("tripwires", [])
        tripwires = [t for t in tripwires if t["id"] != payload.id]
        tripwires.append({
            "id": payload.id,
            "name": payload.name,
            "type": "tripwire",
            "start": payload.start,
            "end": payload.end,
        })
        spatial_cfg["tripwires"] = tripwires
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported zone type '{payload.type}'. Must be 'polygon' or 'tripwire'.",
        )

    return get_zones(config=config)


# --------------------------------------------------------------------------
# 6. Real-time WebSocket Event Endpoint
# --------------------------------------------------------------------------
from fastapi import WebSocket, WebSocketDisconnect
from server.websocket_manager import ws_manager

ws_router = APIRouter(tags=["IBVAP Real-time WebSocket"])


@ws_router.websocket("/ws/events")
@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket event stream delivering live surveillance incidents to connected clients.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Maintain active connection and respond to client heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client connection ended: {e}")
        await ws_manager.disconnect(websocket)


# --------------------------------------------------------------------------
# 7. Demo Surveillance Video Stream (Strictly Read-Only)
# --------------------------------------------------------------------------
@router.get(
    "/video/demo",
    summary="Stream Demo Surveillance Video",
    description="Strictly read-only stream of the pre-configured sample surveillance video footage.",
)
def get_demo_video() -> FileResponse:
    """Stream the configured demo video file strictly without accepting client paths."""
    video_path = Path("data/sample_videos/border_perimeter_demo.mp4").resolve()
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sample surveillance video not found on disk.",
        )
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename="border_perimeter_demo.mp4",
    )


# --------------------------------------------------------------------------
# 8. Real-Time Annotated Video Stream (YOLO11n + ByteTrack Overlays)
# --------------------------------------------------------------------------
@router.get(
    "/video/annotated",
    summary="Stream Real-Time Annotated Surveillance Video",
    description="Streams real-time video feed with YOLO11n detection bounding boxes and ByteTrack tracking overlays as an MJPEG multipart stream.",
)
def get_annotated_video(
    config: Dict[str, Any] = Depends(get_config),
) -> StreamingResponse:
    """
    Stream server-annotated MJPEG frames.
    Strictly read-only, serving pre-configured demo surveillance video without client path parameters.
    """
    from core.video_pipeline import AnnotatedVideoPipeline

    cam_id = config.get("incident", {}).get("camera_id", "CAM-01")
    pipeline = AnnotatedVideoPipeline(
        config_path="config/default_config.yaml",
        camera_id=cam_id,
    )

    return StreamingResponse(
        pipeline.stream_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# --------------------------------------------------------------------------
# 9. Live Managed AI Surveillance Video Stream
# --------------------------------------------------------------------------
@router.get(
    "/video/live/{camera_id}",
    summary="Live AI-Annotated Surveillance Stream",
    description="Streams real-time MJPEG frames actively processed through YOLO11n multi-class detection, ByteTrack tracking, spatial analytics, and tactical overlay rendering.",
)
def get_live_video(camera_id: str) -> StreamingResponse:
    """
    Stream real-time server-annotated MJPEG frames for the selected camera.
    Underlying manager guarantees single-camera active execution on CPU.
    """
    from core.camera_registry import get_camera
    from core.live_stream_manager import live_stream_manager

    cam = get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' is not registered.",
        )
    if not cam.exists_on_disk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video stream source for camera '{camera_id}' is not available on disk.",
        )

    return StreamingResponse(
        live_stream_manager.subscribe(cam.camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# --------------------------------------------------------------------------
# 10. Video Upload & Surveillance Pipeline Ingestion
# --------------------------------------------------------------------------
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB in bytes
CHUNK_SIZE = 1024 * 1024  # 1 MB chunk streaming


def validate_video_signature(header_bytes: bytes) -> Tuple[bool, str]:
    """
    Validate binary magic bytes for supported video containers.
    Returns (is_valid, detected_format_name).
    """
    if len(header_bytes) < 12:
        return False, "unknown"

    # Check for MP4 / MOV (ISO Base Media File Format: b'ftyp' within first 64 bytes)
    if b"ftyp" in header_bytes[:64]:
        return True, "mp4"

    # Check for AVI (RIFF + AVI )
    if header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"AVI ":
        return True, "avi"

    # Check for Matroska / WebM (EBML: 0x1A 0x45 0xDF 0xA3)
    if header_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return True, "mkv"

    return False, "unsupported"


@router.post(
    "/videos/upload",
    response_model=VideoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Recorded Surveillance Video",
    description="Uploads and validates a recorded video file, streams chunks to disk with 500 MB limit, probes video container, and registers as a selectable surveillance camera feed.",
)
async def upload_video(
    file: UploadFile = File(..., description="Recorded video file (MP4, AVI, MOV, MKV, WebM)"),
    camera_name: Optional[str] = Form(default=None, description="Custom camera label for this video source"),
) -> VideoUploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not be empty.",
        )

    # 1. Sanitize filename and prevent path traversal
    raw_filename = Path(file.filename).name
    clean_stem = "".join(c for c in Path(raw_filename).stem if c.isalnum() or c in ("-", "_")).strip()
    if not clean_stem:
        clean_stem = "footage"

    ext = Path(raw_filename).suffix.lower()
    if not ext:
        ext = ".mp4"

    upload_dir = Path("data/uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    unique_suffix = uuid.uuid4().hex[:6].upper()
    camera_id = f"CAM-UP-{unique_suffix}"
    saved_filename = f"{camera_id.lower()}_{clean_stem}{ext}"
    target_path = (upload_dir / saved_filename).resolve()

    # Security check: verify path resolution stays within data/uploads/
    try:
        target_path.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename or path traversal detected.",
        )

    bytes_written = 0
    header_bytes = b""
    is_header_validated = False

    try:
        with open(target_path, "wb") as out_f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                bytes_written += len(chunk)

                # In-flight size limit check
                if bytes_written > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Uploaded video exceeds the 500 MB limit.",
                    )

                # Accumulate initial header for magic byte verification
                if not is_header_validated:
                    header_bytes += chunk[: 64 - len(header_bytes)]
                    if len(header_bytes) >= 12 or len(chunk) < CHUNK_SIZE:
                        is_valid_sig, detected_fmt = validate_video_signature(header_bytes)
                        if not is_valid_sig:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Invalid video file signature. Supported formats: MP4, AVI, MOV, MKV, WebM.",
                            )
                        is_header_validated = True

                out_f.write(chunk)

        # Empty file check
        if bytes_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        # 2. Probe video with OpenCV to verify container and stream integrity
        cap = cv2.VideoCapture(str(target_path))
        if not cap.isOpened():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is corrupted or could not be decoded as a video.",
            )

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        if src_w <= 0 or src_h <= 0 or frame_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid video dimensions or frame count detected.",
            )

        duration_sec = round(frame_count / max(src_fps, 1.0), 2)
        res_str = f"{src_w}x{src_h}"

        # 3. Register camera in camera_registry
        disp_name = camera_name.strip() if camera_name and camera_name.strip() else f"Uploaded: {clean_stem}"
        rel_path = f"data/uploads/{saved_filename}"

        # Default calibrated virtual perimeter boundary for uploaded footage
        default_zones = [
            {
                "id": f"{camera_id}-zone-01",
                "name": "Restricted Perimeter Sector",
                "points": [
                    [int(src_w * 0.35), int(src_h * 0.35)],
                    [int(src_w * 0.95), int(src_h * 0.35)],
                    [int(src_w * 0.95), int(src_h * 0.85)],
                    [int(src_w * 0.35), int(src_h * 0.85)],
                ],
            }
        ]
        default_tripwires = [
            {
                "id": f"{camera_id}-wire-01",
                "name": "Perimeter Demarcation Wire",
                "start": [int(src_w * 0.20), int(src_h * 0.60)],
                "end": [int(src_w * 0.85), int(src_h * 0.60)],
            }
        ]

        from core.camera_registry import CameraDefinition, register_camera

        cam_def = CameraDefinition(
            camera_id=camera_id,
            name=disp_name,
            file_path=rel_path,
            resolution=res_str,
            source_fps=src_fps,
            source_type="file",
            aspect_ratio="16:9",
            is_protected=False,
            zones=default_zones,
            tripwires=default_tripwires,
        )
        register_camera(cam_def, persist=True)

        logger.info(
            f"Successfully processed upload: {camera_id} ({disp_name}) | "
            f"Res: {res_str} | FPS: {src_fps} | Frames: {frame_count} | Size: {bytes_written} bytes"
        )

        return VideoUploadResponse(
            camera_id=camera_id,
            name=disp_name,
            file_path=rel_path,
            resolution=res_str,
            source_fps=round(src_fps, 2),
            frame_count=frame_count,
            duration_sec=duration_sec,
            file_size_bytes=bytes_written,
            message="Video uploaded and registered successfully.",
        )

    except HTTPException:
        # Clean up partial / invalid file
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove invalid file {target_path}: {e}")
        raise
    except Exception as exc:
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove partial file {target_path}: {e}")
        logger.error(f"Unexpected error processing video upload: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process video upload: {str(exc)}",
        )



