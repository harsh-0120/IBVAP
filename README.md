# IBVAP — Intelligent Border Video Analytics Platform

> **Problem Statement 26187 (SIH 2026)**: *AI-Based Intelligent Video Analytics Platform for Border Surveillance using existing CCTV Infrastructure.*

IBVAP is a software-defined surveillance intelligence platform that transforms existing legacy CCTV / RTSP video streams into an automated border perimeter intrusion detection system without requiring expensive proprietary smart cameras.

---

## Milestone 1: Video Ingestion Layer

Milestone 1 delivers the modular, non-blocking video ingestion layer supporting local video files, webcams, and RTSP IP camera streams.

### Key Features Implemented (Milestones 1 to 6A)
- **Modular Stream Reader (`core/stream_reader.py`)**: Unified abstraction across file, webcam, and RTSP video sources with a zero-latency latest-frame ring buffer (queue size = 1) dropping stale backlog frames.
- **Modular AI Person Detector (`core/detector.py`)**: `BaseDetector` abstraction implemented with Ultralytics `YOLO11n` (`yolo11n.pt`). Filters strictly for COCO class 0 (`person`).
- **Hardware-Agnostic Device Auto-Detection**: Dynamically checks CUDA availability (`torch.cuda.is_available()`) and falls back cleanly to CPU execution.
- **Multi-Object Tracking with ByteTrack (`core/tracker.py`)**: `BaseTracker` abstraction with ByteTrack engine maintaining persistent tracking IDs and trajectory histories.
- **Spatial Analytics Engine (`core/spatial_engine.py`)**: Decoupled computational geometry engine using Shapely for polygon zones (virtual fences) and directional linear tripwires.
- **Ground-Contact Feet Point Anchoring**: Evaluates person location based on bottom-center $(x_{mid}, y_{max})$ rather than bounding box center, avoiding false alarms from leaning or arm waving.
- **Incident Management & Forensics (`core/incident_manager.py`)**: Converts confirmed spatial breaches into structured security incident records with deterministic JPEG snapshots.
- **SQLite Database Persistence (`server/database.py`)**: SQLAlchemy ORM schema with indexes on `timestamp`, `event_type`, `camera_id`, and `track_id` supporting fast forensic audit queries.
- **FastAPI Backend REST API (`server/app.py`, `server/routes.py`, `server/schemas.py`)**: High-performance REST interface exposing health, events, stats, camera status, spatial zones, and snapshot downloads with Swagger docs at `/docs`.
- **Real-Time WebSocket Event Stream (`server/websocket_manager.py`, `/ws/events`)**: Asynchronous WebSocket event broadcasting channel delivering live breach alerts and forensic metadata to connected dashboard clients.
- **Automated Test Suite (`tests/`)**: 59 automated pytest unit and integration tests covering WebSocket streams, connection lifecycle, multi-client broadcast, REST endpoints, database persistence, spatial analytics, ByteTrack tracking, and video ingestion.

---

## Real-Time WebSocket Event Stream (`/ws/events`)

The platform streams live incident alerts to connected clients over WebSockets.

### Connection Handshake:
Upon connecting to `ws://127.0.0.1:8000/ws/events`, the server sends:
```json
{
  "message_type": "CONNECTED",
  "service": "IBVAP",
  "active_clients": 1
}
```

### Heartbeat:
Clients can send `"ping"` and will receive `"pong"` to verify stream liveness.

### Real-Time Incident Message Format:
When a boundary breach occurs, connected clients receive an alert payload:
```json
{
  "message_type": "NEW_INCIDENT",
  "id": 15,
  "incident_id": 15,
  "timestamp": 1725624944.37,
  "iso_timestamp": "2026-09-06T14:45:44.370000Z",
  "camera_id": "CAM-01",
  "event_type": "TRIPWIRE_CROSSING",
  "track_id": 4,
  "object_type": "person",
  "zone_id": "perimeter_tripwire_01",
  "zone_name": "Perimeter Demarcation Wire",
  "direction": "RIGHT_TO_LEFT",
  "confidence": 0.89,
  "frame_index": 63,
  "feet_point": [799.5, 357.68],
  "snapshot_path": "data/snapshots/2026-09-06_144544_CAM-01_track-4_tripwire_003.jpg"
}
```

### Running the Live WebSocket Demonstration:
```powershell
.\.venv\Scripts\python.exe scripts/demo_websocket_events.py --max-frames 120
```

---

## Starting the FastAPI Server (REST + WebSocket)

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger API documentation is accessible at:  
👉 **http://127.0.0.1:8000/docs**  
WebSocket Stream Endpoint:  
👉 **ws://127.0.0.1:8000/ws/events**

## Quickstart (Milestone 1)

### 1. Environment Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Sample Surveillance Footage
```powershell
.\.venv\Scripts\python.exe scripts/generate_sample_video.py
```
This produces `data/sample_videos/border_perimeter_demo.mp4` (1280x720 @ 30 FPS).

### 3. Run Ingestion Verification Demo
```powershell
.\.venv\Scripts\python.exe scripts/demo_stream_reader.py
```

### 4. Run Automated Tests
```powershell
.\.venv\Scripts\python.exe -m pytest -v tests/
```

---

## Configuration Reference (`config/default_config.yaml`)

```yaml
video:
  source_type: "file"       # "file", "webcam", or "rtsp"
  file_path: "data/sample_videos/border_perimeter_demo.mp4"
  webcam_index: 0           # Hardware device index
  rtsp_url: "rtsp://..."    # IP camera RTSP endpoint
  loop: true                # Loop video file continuously
  buffer_size: 1            # 1 = Zero-lag (drops stale frames)
  reconnect_delay_sec: 2.0  # Retry delay on connection drop
```
