"""
IBVAP Live AI Video Streaming Manager
Coordinates active camera worker, single-pass YOLO11n multi-class inference,
ByteTrack tracking, spatial analytics, incident logging, and MJPEG multipart streaming.

Key Constraints:
- Exactly ONE camera pipeline runs active AI inference at any time to respect CPU constraints.
- A single shared YOLODetector instance is reused across camera switches to prevent memory bloat.
- Video looping resets tracker and spatial tracking states to eliminate ghost IDs.
- Honest telemetry: Source FPS and measured AI processing FPS are tracked and broadcast separately.
"""

from collections import deque
import logging
import queue
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Set

import cv2
import numpy as np

from core.camera_registry import DEMO_CAMERAS, CameraDefinition, get_camera
from core.detector import ALL_SURVEILLANCE_CLASS_IDS, DetectorConfig, YOLODetector
from core.incident_manager import IncidentConfig, IncidentManager, IncidentRecord
from core.overlay_renderer import OverlayConfig, OverlayRenderer
from core.spatial_engine import PolygonZone, SpatialConfig, SpatialEngine, Tripwire
from core.tracker import ByteTrackTracker, TrackerConfig
from server.websocket_manager import ws_manager

logger = logging.getLogger("ibvap.live_stream")


class LiveStreamManager:
    """
    Manages the lifecycle of live AI camera surveillance streams.
    Ensures single-camera active processing, thread safety, clean looping,
    real-time telemetry broadcasting, and multi-client MJPEG distribution.
    """

    def __init__(self, config_path: str = "config/default_config.yaml"):
        self.config_path = config_path

        # 1. Component configurations
        self.det_cfg = DetectorConfig.from_yaml(config_path)
        self.trk_cfg = TrackerConfig.from_yaml(config_path)
        self.over_cfg = OverlayConfig.from_yaml(config_path)

        # 2. Shared YOLO detector (loaded once in memory)
        target_classes = self.det_cfg.target_classes or ALL_SURVEILLANCE_CLASS_IDS
        self.detector = YOLODetector(self.det_cfg, target_classes=target_classes)

        # 3. Stream state
        self._lock = threading.Lock()
        self._active_camera_id: Optional[str] = None
        self._camera_status: Dict[str, str] = {cid: "READY" for cid in DEMO_CAMERAS}
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 4. Multi-client frame distribution
        self._condition = threading.Condition(self._lock)
        self._latest_jpeg: Optional[bytes] = None
        self._frame_seq: int = 0
        self._subscriber_count: int = 0
        self._last_subscriber_active: float = time.time()

        # 5. Telemetry state
        self._latest_telemetry: Dict[str, Any] = {}
        self._fps_history = deque(maxlen=20)
        self._last_processing_fps: float = 0.0

    @property
    def active_camera_id(self) -> Optional[str]:
        with self._lock:
            return self._active_camera_id

    def get_camera_status(self, camera_id: str) -> str:
        with self._lock:
            cid = camera_id.upper()
            cam = get_camera(cid)
            if not cam or not cam.exists_on_disk:
                return "OFFLINE"
            if self._active_camera_id == cid and self._worker_thread and self._worker_thread.is_alive():
                return "ONLINE / PROCESSING"
            return self._camera_status.get(cid, "READY")

    def get_all_camera_statuses(self) -> Dict[str, str]:
        with self._lock:
            statuses = {}
            for cid, cam in DEMO_CAMERAS.items():
                if not cam.exists_on_disk:
                    statuses[cid] = "OFFLINE"
                elif self._active_camera_id == cid and self._worker_thread and self._worker_thread.is_alive():
                    statuses[cid] = "ONLINE / PROCESSING"
                else:
                    statuses[cid] = self._camera_status.get(cid, "READY")
            return statuses

    def get_latest_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._latest_telemetry)

    def switch_camera(self, camera_id: str) -> bool:
        """
        Switch active processing to target camera.
        Safely stops any existing camera pipeline, releases VideoCapture,
        and launches the new pipeline.
        """
        cid = camera_id.upper()
        cam = get_camera(cid)
        if not cam:
            logger.warning(f"Requested camera {cid} not found in registry.")
            return False

        if not cam.exists_on_disk:
            logger.warning(f"Video file for camera {cid} missing: {cam.file_path}")
            with self._lock:
                self._camera_status[cid] = "OFFLINE"
            return False

        with self._lock:
            if self._active_camera_id == cid and self._worker_thread and self._worker_thread.is_alive():
                logger.info(f"Camera {cid} is already actively processing.")
                return True

            # Stop existing worker if active
            self._stop_current_worker_locked()

            # Prepare for new camera
            self._active_camera_id = cid
            self._stop_event.clear()
            self._camera_status[cid] = "ONLINE / PROCESSING"

            # Reset other statuses to READY
            for c in DEMO_CAMERAS:
                if c != cid and DEMO_CAMERAS[c].exists_on_disk:
                    self._camera_status[c] = "READY"

            # Start background processing worker
            self._worker_thread = threading.Thread(
                target=self._camera_worker_loop,
                args=(cam,),
                name=f"Worker-{cid}",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info(f"Started live AI surveillance pipeline for camera {cid} ({cam.name}).")
            return True

    def _stop_current_worker_locked(self) -> None:
        """Stop the currently active worker thread (must be called with self._lock acquired)."""
        if self._worker_thread and self._worker_thread.is_alive():
            prev_cam = self._active_camera_id
            logger.info(f"Stopping active surveillance worker for {prev_cam}...")
            self._stop_event.set()
            # Release lock briefly to allow worker to exit cleanly
            self._condition.notify_all()
            self._lock.release()
            try:
                self._worker_thread.join(timeout=2.0)
            finally:
                self._lock.acquire()

            if prev_cam:
                self._camera_status[prev_cam] = "READY"

        self._active_camera_id = None
        self._worker_thread = None
        self._latest_jpeg = None
        self._frame_seq = 0

    def subscribe(self, camera_id: str) -> Generator[bytes, None, None]:
        """
        Subscribe a client connection to the MJPEG frame stream.
        Automatically starts/switches camera processing if not active.
        """
        cid = camera_id.upper()
        # Activate camera stream
        self.switch_camera(cid)

        with self._lock:
            self._subscriber_count += 1
            self._last_subscriber_active = time.time()
            logger.debug(f"New client subscribed to {cid}. Total subscribers: {self._subscriber_count}")

        last_yielded_seq = -1

        try:
            while True:
                with self._lock:
                    # Check if worker stopped or camera switched
                    if self._active_camera_id != cid or self._stop_event.is_set():
                        break

                    # Wait for a fresh frame
                    while self._frame_seq == last_yielded_seq:
                        notified = self._condition.wait(timeout=0.2)
                        if not notified or self._stop_event.is_set() or self._active_camera_id != cid:
                            break

                    if self._latest_jpeg is None:
                        continue

                    frame_bytes = self._latest_jpeg
                    last_yielded_seq = self._frame_seq

                # Yield multipart MJPEG frame
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )

        except (GeneratorExit, ConnectionResetError, BrokenPipeError):
            logger.debug(f"Client disconnected from {cid} stream.")
        finally:
            with self._lock:
                self._subscriber_count = max(0, self._subscriber_count - 1)
                self._last_subscriber_active = time.time()
                logger.debug(f"Client unsubscribed from {cid}. Remaining subscribers: {self._subscriber_count}")

    def _camera_worker_loop(self, cam_def: CameraDefinition) -> None:
        """
        Continuous frame ingestion and AI surveillance loop for the selected camera.
        Executes:
        VideoCapture -> YOLO11n -> ByteTrack -> SpatialEngine -> IncidentManager -> OverlayRenderer -> JPEG
        """
        cid = cam_def.camera_id
        cap = cv2.VideoCapture(cam_def.file_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video source for {cid}: {cam_def.file_path}")
            with self._lock:
                self._camera_status[cid] = "ERROR"
            return

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        src_fps = float(cap.get(cv2.CAP_PROP_FPS) or cam_def.source_fps or 30.0)

        # Output frame resolution for network streaming (scaled proportionally to max 1280 wide/tall)
        max_dim = 1280
        scale = min(1.0, max_dim / max(src_w, src_h))
        out_w = int(src_w * scale)
        out_h = int(src_h * scale)

        # Initialize camera-specific spatial engine
        zones = [
            PolygonZone(id=z["id"], name=z["name"], points=z["points"])
            for z in cam_def.zones
        ]
        tripwires = [
            Tripwire(id=t["id"], name=t["name"], start=t["start"], end=t["end"])
            for t in cam_def.tripwires
        ]
        spat_cfg = SpatialConfig(
            enabled=True,
            cooldown_sec=3.0,
            min_track_frames=2,
            zones=zones,
            tripwires=tripwires,
        )

        def on_incident_callback(rec: IncidentRecord) -> None:
            """Broadcast confirmed incident to WebSocket subscribers."""
            payload = rec.to_dict()
            payload["message_type"] = "NEW_INCIDENT"
            ws_manager.broadcast_sync(payload)

        # Per-camera trackers and incident manager
        tracker = ByteTrackTracker(self.trk_cfg)
        spatial_engine = SpatialEngine(spat_cfg)
        incident_mgr = IncidentManager(
            config=IncidentConfig(camera_id=cid, db_path="data/events.db", snapshot_dir="data/snapshots"),
            on_incident=on_incident_callback,
        )
        overlay_renderer = OverlayRenderer(self.over_cfg)

        frame_idx = 0
        loop_iteration = 0
        fps_history = deque(maxlen=20)
        t_last_frame = time.perf_counter()
        t_last_telemetry = time.perf_counter()

        logger.info(f" সুর Surveillance loop active for {cid} ({src_w}x{src_h} @ {src_fps}fps)")

        try:
            while not self._stop_event.is_set():
                t0 = time.perf_counter()
                ret, frame = cap.read()

                # Handle EOF -> Clean Video Looping with State Resets
                if not ret or frame is None:
                    loop_iteration += 1
                    logger.info(
                        f"Video {cid} reached EOF. Looping iteration {loop_iteration}: "
                        f"Resetting ByteTrack and Spatial tracking states to prevent ghost IDs."
                    )
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame_idx = 0

                    # Reset tracking and spatial state so no stale IDs carry over
                    tracker = ByteTrackTracker(self.trk_cfg)
                    spatial_engine = SpatialEngine(spat_cfg)

                    ret, frame = cap.read()
                    if not ret or frame is None:
                        logger.warning(f"Could not read first frame after loop restart for {cid}.")
                        time.sleep(0.05)
                        continue

                current_ts = frame_idx / src_fps

                # 1. Single-Pass Multi-Class YOLO11n Detection
                det_result = self.detector.detect(frame, frame_index=frame_idx)

                # 2. Class-Aware Multi-Object ByteTrack Tracking
                trk_result = tracker.update(det_result, frame_index=frame_idx, timestamp=current_ts)

                # 3. Spatial Analytics Evaluation
                events, active_states = spatial_engine.process_tracks(
                    tracks=trk_result.tracks,
                    frame_index=frame_idx,
                    timestamp=current_ts,
                )

                # 4. Incident Management & Forensic Snapshots
                for ev in events:
                    assoc_track = next((t for t in trk_result.tracks if t.track_id == ev.track_id), None)
                    incident_mgr.process_event(event=ev, frame=frame, track=assoc_track)

                # 5. Measure Actual AI Processing FPS
                t_frame_end = time.perf_counter()
                dt = t_frame_end - t_last_frame
                t_last_frame = t_frame_end
                if dt > 0:
                    fps_history.append(1.0 / dt)
                    current_processing_fps = sum(fps_history) / len(fps_history)
                else:
                    current_processing_fps = 0.0
                self._last_processing_fps = current_processing_fps

                # 6. Extract Telemetry Counts
                active_tracks_count = len(trk_result.tracks)
                persons_count = sum(1 for t in trk_result.tracks if getattr(t, "object_type", "person") == "person")
                vehicles_count = sum(1 for t in trk_result.tracks if getattr(t, "object_type", "person") == "vehicle")
                cars_count = sum(1 for t in trk_result.tracks if getattr(t, "class_name", "") == "car")
                motorcycles_count = sum(1 for t in trk_result.tracks if getattr(t, "class_name", "") == "motorcycle")
                buses_count = sum(1 for t in trk_result.tracks if getattr(t, "class_name", "") == "bus")
                trucks_count = sum(1 for t in trk_result.tracks if getattr(t, "class_name", "") == "truck")

                # 7. Broadcast Real-Time WebSocket Telemetry (throttled to ~5-10 Hz)
                if (t_frame_end - t_last_telemetry) >= 0.12 or frame_idx % 2 == 0:
                    t_last_telemetry = t_frame_end
                    telemetry_data = {
                        "message_type": "TELEMETRY",
                        "camera_id": cid,
                        "camera_name": cam_def.name,
                        "camera_status": "ONLINE / PROCESSING",
                        "processing_fps": round(current_processing_fps, 1),
                        "source_fps": round(src_fps, 1),
                        "active_tracks": active_tracks_count,
                        "persons": persons_count,
                        "vehicles": vehicles_count,
                        "cars": cars_count,
                        "motorcycles": motorcycles_count,
                        "buses": buses_count,
                        "trucks": trucks_count,
                        "total_incidents": incident_mgr.db.count_incidents(),
                        "zone_intrusions": incident_mgr.db.count_by_event_type().get("ZONE_INTRUSION", 0),
                        "tripwire_crossings": incident_mgr.db.count_by_event_type().get("TRIPWIRE_CROSSING", 0),
                        "loop_count": loop_iteration,
                    }
                    with self._lock:
                        self._latest_telemetry = telemetry_data
                    ws_manager.broadcast_sync(telemetry_data)

                # 8. Render Tactical AI Overlay
                annotated = overlay_renderer.render(
                    frame=frame,
                    tracks=trk_result.tracks,
                    fps=current_processing_fps,
                    camera_id=cid,
                )
                if spatial_engine.zones or spatial_engine.tripwires:
                    annotated = spatial_engine.annotate_frame(
                        frame=annotated,
                        tracks=trk_result.tracks,
                        events=events,
                        active_states=active_states,
                    )

                # 9. Resize and Compress to JPEG
                if scale < 1.0:
                    annotated_out = cv2.resize(annotated, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                else:
                    annotated_out = annotated

                jpeg_bytes = overlay_renderer.encode_jpeg(annotated_out)

                # 10. Distribute Frame to Subscribers
                with self._lock:
                    self._latest_jpeg = jpeg_bytes
                    self._frame_seq += 1
                    self._condition.notify_all()

                frame_idx += 1

                # If no subscribers are connected for > 30 seconds, slow down loop to conserve CPU
                with self._lock:
                    has_subscribers = self._subscriber_count > 0
                if not has_subscribers:
                    time.sleep(0.05)

        except Exception as e:
            logger.error(f"Surveillance worker error for {cid}: {e}", exc_info=True)
            with self._lock:
                self._camera_status[cid] = "ERROR"
        finally:
            cap.release()
            logger.info(f"Surveillance worker for {cid} stopped and video capture released.")
            with self._lock:
                if self._active_camera_id == cid:
                    self._active_camera_id = None
                    self._camera_status[cid] = "READY"


# Global singleton instance for application use
live_stream_manager = LiveStreamManager()
