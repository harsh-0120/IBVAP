"""
IBVAP Milestone 6B Demo: Real-time WebSocket Event Stream.
Connects to the IBVAP WebSocket stream (/ws/events) and demonstrates
live telemetry delivery as intrusions and tripwire crossings occur.

Pipeline Architecture:
StreamReader -> PersonDetector -> ByteTrackTracker -> SpatialEngine -> IncidentManager -> WebSocketManager -> WebSocket Client
"""

import argparse
import json
import logging
from pathlib import Path
import sys
import threading
import time
from typing import Optional

import uvicorn
from websockets.sync.client import connect

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.detector import DetectorConfig, PersonDetector
from core.incident_manager import IncidentConfig, IncidentManager, IncidentRecord
from core.spatial_engine import SpatialConfig, SpatialEngine
from core.stream_reader import StreamConfig, StreamReader
from core.tracker import ByteTrackTracker, TrackerConfig
from server.app import app
from server.database import IncidentDatabase
from server.websocket_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ibvap.demo_ws")


def start_server_in_thread(host: str = "127.0.0.1", port: int = 8000) -> uvicorn.Server:
    """Start uvicorn server in a background daemon thread."""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until server reports started
    for _ in range(30):
        if server.started:
            break
        time.sleep(0.1)

    logger.info(f"Uvicorn server running on http://{host}:{port}")
    return server


def websocket_listener_client(
    ws_url: str,
    stop_event: threading.Event,
    received_events_list: list,
) -> None:
    """Background WebSocket client thread that listens and logs real-time events."""
    logger.info(f"[WS CLIENT] Connecting to WebSocket: {ws_url}")
    try:
        with connect(ws_url) as websocket:
            # Receive initial handshake
            handshake = websocket.recv()
            handshake_data = json.loads(handshake)
            logger.info(f"[WS CLIENT] Handshake received: {handshake_data}")

            # Listen continuously until stopped
            while not stop_event.is_set():
                try:
                    # Non-blocking poll with short timeout
                    message = websocket.recv(timeout=0.5)
                    data = json.loads(message)
                    received_events_list.append(data)

                    mtype = data.get("message_type", "EVENT")
                    inc_id = data.get("id") or data.get("incident_id")
                    etype = data.get("event_type", "UNKNOWN")
                    cam = data.get("camera_id", "N/A")
                    track = data.get("track_id", "N/A")
                    zone = data.get("zone_name", "N/A")
                    direction = data.get("direction")
                    dir_str = f" | Dir: {direction}" if direction else ""
                    snap = data.get("snapshot_path", "")

                    logger.info(
                        f"[WS LIVE ALERT] [{mtype}] Inc #{inc_id} | {etype} | "
                        f"Cam: {cam} | Target: Track #{track} | Zone: {zone}{dir_str} | "
                        f"Snapshot: {snap}"
                    )
                except TimeoutError:
                    continue
                except Exception as ex:
                    if not stop_event.is_set():
                        logger.debug(f"[WS CLIENT] Recv error: {ex}")
                    break
    except Exception as e:
        logger.error(f"[WS CLIENT] Failed to connect or maintain session with {ws_url}: {e}")


def run_pipeline_with_websocket(
    config_path: str = "config/default_config.yaml",
    max_frames: int = 150,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the 5-stage pipeline and broadcast real-time events over WebSocket."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file.resolve()}")

    # 1. Start Server
    server = start_server_in_thread(host=host, port=port)
    ws_url = f"ws://{host}:{port}/ws/events"

    # 2. Start WebSocket client listener thread
    stop_event = threading.Event()
    received_events = []
    listener_thread = threading.Thread(
        target=websocket_listener_client,
        args=(ws_url, stop_event, received_events),
        daemon=True,
    )
    listener_thread.start()
    time.sleep(0.5)  # Allow client connection to establish

    # 3. Load configurations
    stream_cfg = StreamConfig.from_yaml(cfg_file)
    detector_cfg = DetectorConfig.from_yaml(cfg_file)
    tracker_cfg = TrackerConfig.from_yaml(cfg_file)
    spatial_cfg = SpatialConfig.from_yaml(cfg_file)
    incident_cfg = IncidentConfig.from_yaml(cfg_file)

    logger.info("==================================================================")
    logger.info("IBVAP REAL-TIME WEBSOCKET EVENT DEMO (MILESTONE 6B)")
    logger.info("==================================================================")
    logger.info(f"Video Source:        {stream_cfg.get_source_target()}")
    logger.info(f"WebSocket Endpoint:  {ws_url}")
    logger.info(f"Active WS Clients:   {ws_manager.active_count}")
    logger.info(f"Frame Limit:         {max_frames} frames")
    logger.info("==================================================================")

    # 4. Initialize Pipeline Components
    reader = StreamReader(stream_cfg)
    detector = PersonDetector(detector_cfg)
    tracker = ByteTrackTracker(tracker_cfg)
    spatial = SpatialEngine(spatial_cfg)

    # Define callback bridging incident creation to WebSocket broadcast
    def on_incident_created(record: IncidentRecord) -> None:
        payload = {
            "message_type": "NEW_INCIDENT",
            **record.to_dict(),
        }
        ws_manager.broadcast_sync(payload)

    db = IncidentDatabase(incident_cfg.db_path)
    incident_mgr = IncidentManager(
        config=incident_cfg,
        database=db,
        on_incident=on_incident_created,
    )

    processed_frames = 0
    start_time = time.perf_counter()

    try:
        reader.start()
        logger.info("Video stream ingestion started. Processing frames...")

        while processed_frames < max_frames and reader.is_alive:
            success, frame, frame_idx, ts = reader.read(timeout=1.0)
            if not success or frame is None:
                if not reader.is_alive:
                    break
                continue

            # Stage 2: Detection
            det_res = detector.detect(frame, frame_index=frame_idx)

            # Stage 3: Tracking
            track_res = tracker.update(det_res, frame_index=frame_idx, timestamp=ts)

            # Stage 4: Spatial Analytics
            events, _ = spatial.process_tracks(track_res.tracks, frame_index=frame_idx, timestamp=ts)

            # Stage 5: Incident Management & WebSocket Broadcasting
            if events:
                tracks_by_id = {t.track_id: t for t in track_res.tracks}
                for ev in events:
                    target_track = tracks_by_id.get(ev.track_id)
                    incident_mgr.process_event(
                        event=ev,
                        frame=frame,
                        track=target_track,
                    )

            processed_frames += 1
            if processed_frames % 25 == 0:
                fps = processed_frames / (time.perf_counter() - start_time)
                logger.info(f"Processed {processed_frames}/{max_frames} frames ({fps:.1f} FPS) | Incidents broadcast: {len(received_events)}")

    finally:
        reader.stop()

    # Allow client to receive any buffered messages
    time.sleep(1.0)
    stop_event.set()
    server.should_exit = True
    listener_thread.join(timeout=2.0)

    elapsed = time.perf_counter() - start_time
    logger.info("==================================================================")
    logger.info("DEMO RUN COMPLETED")
    logger.info(f"Total Frames Processed: {processed_frames}")
    logger.info(f"Average Pipeline FPS:   {processed_frames / elapsed:.1f}")
    logger.info(f"Events Received by WS:  {len(received_events)}")
    logger.info("==================================================================")


def listen_only_mode(ws_url: str) -> None:
    """Connect to an existing running IBVAP server and listen for live events."""
    logger.info(f"Listening to live IBVAP WebSocket stream at: {ws_url}")
    logger.info("Press Ctrl+C to terminate.")
    try:
        with connect(ws_url) as ws:
            handshake = ws.recv()
            print(f"\nConnected! Handshake: {handshake}\n")
            while True:
                msg = ws.recv()
                data = json.loads(msg)
                print(f"[LIVE INCIDENT] {json.dumps(data, indent=2)}")
    except KeyboardInterrupt:
        print("\nExiting WebSocket listener.")
    except Exception as e:
        print(f"Connection failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IBVAP Real-time WebSocket Demo")
    parser.add_argument("--listen-only", action="store_true", help="Connect to existing server without running pipeline")
    parser.add_argument("--ws-url", type=str, default="ws://127.0.0.1:8000/ws/events", help="WebSocket URL for listen mode")
    parser.add_argument("--config", type=str, default="config/default_config.yaml", help="Path to config file")
    parser.add_argument("--max-frames", type=int, default=120, help="Maximum frames to process in demo")
    parser.add_argument("--port", type=int, default=8000, help="Port to host server on for demo")

    args = parser.parse_args()

    if args.listen_only:
        listen_only_mode(args.ws_url)
    else:
        run_pipeline_with_websocket(
            config_path=args.config,
            max_frames=args.max_frames,
            port=args.port,
        )
