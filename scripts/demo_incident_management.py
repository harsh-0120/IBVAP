"""
IBVAP Milestone 5 Demo: Incident Management & SQLite Event Logging
Full 5-Stage Pipeline:
StreamReader -> PersonDetector -> ByteTrackTracker -> SpatialEngine -> IncidentManager -> SQLite & Snapshots.
"""

import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Optional

import cv2

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.detector import DetectorConfig, PersonDetector
from core.incident_manager import IncidentConfig, IncidentManager
from core.spatial_engine import SpatialConfig, SpatialEngine
from core.stream_reader import StreamConfig, StreamReader
from core.tracker import ByteTrackTracker, TrackerConfig
from server.database import IncidentDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ibvap.demo_incident")


def run_incident_pipeline(
    config_path: str = "config/default_config.yaml",
    max_frames: Optional[int] = None,
    headless: bool = False,
    save_video_path: Optional[str] = None,
) -> None:
    """Execute the end-to-end incident management pipeline."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file.resolve()}")

    # 1. Load Configurations
    stream_cfg = StreamConfig.from_yaml(cfg_file)
    detector_cfg = DetectorConfig.from_yaml(cfg_file)
    tracker_cfg = TrackerConfig.from_yaml(cfg_file)
    spatial_cfg = SpatialConfig.from_yaml(cfg_file)
    incident_cfg = IncidentConfig.from_yaml(cfg_file)

    logger.info("==================================================================")
    logger.info("IBVAP FULL SURVEILLANCE PIPELINE (MILESTONES 1 TO 5)")
    logger.info("==================================================================")
    logger.info(f"Camera Node ID:      {incident_cfg.camera_id}")
    logger.info(f"Video Ingestion:     {stream_cfg.get_source_target()}")
    logger.info(f"Object Detector:     {detector_cfg.model_name} on {detector_cfg.device}")
    logger.info(f"Multi-Object Tracker:{tracker_cfg.tracker_type.upper()}")
    logger.info(f"Spatial Boundaries:  {len(spatial_cfg.zones)} Zones, {len(spatial_cfg.tripwires)} Tripwires")
    logger.info(f"SQLite Event DB:     {incident_cfg.db_path}")
    logger.info(f"Snapshot Storage:    {incident_cfg.snapshot_dir}")
    logger.info("==================================================================")

    # 2. Instantiate Components
    db = IncidentDatabase(incident_cfg.db_path)
    initial_db_count = db.count_incidents()
    logger.info(f"Existing incidents in database before run: {initial_db_count}")

    detector = PersonDetector(detector_cfg)
    tracker = ByteTrackTracker(tracker_cfg)
    spatial_engine = SpatialEngine(spatial_cfg)
    incident_mgr = IncidentManager(config=incident_cfg, database=db)

    video_writer = None
    if save_video_path:
        out_p = Path(save_video_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

    # Performance and telemetry metrics
    total_frames = 0
    total_detections = 0
    incidents_logged_this_run = []
    fps_history = []
    last_frame_time = time.time()
    start_time = time.time()

    logger.info("Starting video stream processing...")
    try:
        with StreamReader(stream_cfg) as reader:
            logger.info(f"Connected to stream: {reader.resolution} @ {reader.fps:.1f} FPS")

            if save_video_path:
                w, h = reader.resolution
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                video_writer = cv2.VideoWriter(save_video_path, fourcc, 25.0, (w, h))

            while reader.is_alive:
                if max_frames and total_frames >= max_frames:
                    logger.info(f"Reached max_frames limit of {max_frames}. Concluding run.")
                    break

                success, frame, frame_idx, timestamp = reader.read(timeout=1.0)
                if not success or frame is None:
                    if not reader.is_alive:
                        break
                    continue

                total_frames += 1
                now = time.time()
                dt = now - last_frame_time
                last_frame_time = now
                current_fps = 1.0 / dt if dt > 0 else 30.0
                fps_history.append(current_fps)
                if len(fps_history) > 30:
                    fps_history.pop(0)
                avg_fps = sum(fps_history) / len(fps_history)

                # Stage 1: AI Person Detection
                det_result = detector.detect(frame, frame_index=frame_idx)
                total_detections += det_result.count

                # Stage 2: Multi-Object Tracking
                trk_result = tracker.update(
                    det_result, frame_index=frame_idx, timestamp=timestamp
                )

                # Stage 3: Spatial Boundary Analytics
                events, active_states = spatial_engine.process_tracks(
                    trk_result.tracks, frame_index=frame_idx, timestamp=timestamp
                )

                # Stage 4 & 5: Incident Management & SQLite Persistence
                if events:
                    tracks_by_id = {t.track_id: t for t in trk_result.tracks}
                    for ev in events:
                        matched_track = tracks_by_id.get(ev.track_id)
                        # Process, annotate snapshot, and insert into SQLite
                        incident = incident_mgr.process_event(
                            event=ev,
                            frame=frame,
                            track=matched_track,
                        )
                        incidents_logged_this_run.append(incident)

                        # Structured console alert
                        conf_str = (
                            f"{incident.confidence:.2f}"
                            if incident.confidence is not None
                            else "N/A"
                        )
                        dir_str = incident.direction if incident.direction else "N/A"
                        print("\n" + "=" * 62)
                        print(f"[ALERT] SECURITY INCIDENT LOGGED -> DATABASE ID: #{incident.id}")
                        print(f"Event Type:  {incident.event_type}")
                        print(f"Camera:      {incident.camera_id}")
                        print(f"Track ID:    #{incident.track_id}")
                        print(f"Boundary:    {incident.zone_name} ({incident.zone_id})")
                        print(f"Direction:   {dir_str}")
                        print(f"Confidence:  {conf_str}")
                        print(f"Feet Point:  {incident.feet_point}")
                        print(f"Snapshot:    {incident.snapshot_path}")
                        print("=" * 62 + "\n")

                # Tactical Visual Annotation
                annotated = tracker.annotate_frame(
                    frame,
                    trk_result,
                    draw_trails=True,
                    draw_feet=True,
                    fps=avg_fps,
                )
                annotated = spatial_engine.annotate_frame(
                    annotated,
                    trk_result.tracks,
                    events,
                    active_states,
                )

                if video_writer:
                    video_writer.write(annotated)

                # Periodic Telemetry
                if total_frames % 25 == 0 or total_frames == 1:
                    logger.info(
                        f"Frame {total_frames:04d} (Source: {frame_idx:04d}) | "
                        f"Tracks: {trk_result.active_count} | "
                        f"Run Incidents: {len(incidents_logged_this_run)} | "
                        f"Total DB Incidents: {db.count_incidents()} | "
                        f"Pipeline FPS: {avg_fps:.1f}"
                    )

                # Interactive window
                if not headless:
                    try:
                        cv2.imshow(
                            "IBVAP - Incident Management System (Press 'q' to quit)",
                            annotated,
                        )
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord("q") or key == 27:
                            logger.info("User requested quit. Terminating cleanly...")
                            break
                    except cv2.error:
                        headless = True

    except KeyboardInterrupt:
        logger.info("Interrupted by user. Cleaning up...")
    finally:
        if not headless:
            cv2.destroyAllWindows()
        if video_writer:
            video_writer.release()

    total_time = time.time() - start_time
    effective_fps = total_frames / total_time if total_time > 0 else 0.0

    # ------------------------------------------------------------------
    # POST-RUN DATABASE & FORENSIC VERIFICATION AUDIT
    # ------------------------------------------------------------------
    final_db_count = db.count_incidents()
    counts_by_type = db.count_by_event_type()
    recent_db_records = db.get_recent_incidents(limit=len(incidents_logged_this_run) + 5)

    # Verify physical file existence for all generated snapshots
    valid_snapshots = 0
    missing_snapshots = 0
    for rec in incidents_logged_this_run:
        p = Path(rec.snapshot_path)
        if p.exists() and p.stat().st_size > 0:
            valid_snapshots += 1
        else:
            missing_snapshots += 1

    print("\n" + "=" * 70)
    print("IBVAP MILESTONE 5: DATABASE & FORENSIC AUDIT SUMMARY")
    print("=" * 70)
    print(f"Total Frames Processed:          {total_frames}")
    print(f"Total Raw Person Detections:     {total_detections}")
    print(f"Pipeline Running Time:           {total_time:.2f} s")
    print(f"Measured Pipeline FPS:           {effective_fps:.2f} FPS")
    print("-" * 70)
    print(f"Incidents Logged in This Run:    {len(incidents_logged_this_run)}")
    print(f"Total Incidents in SQLite DB:    {final_db_count}")
    print(f"Breakdown by Event Type:")
    for ev_type, count in counts_by_type.items():
        print(f"  • {ev_type}: {count}")
    print("-" * 70)
    print(f"Snapshots Verified on Disk:      {valid_snapshots} (Missing: {missing_snapshots})")
    print("Recent Incidents Sample from Database:")
    for inc in recent_db_records[:5]:
        dir_repr = f"({inc.direction})" if inc.direction else ""
        print(
            f"  [ID #{inc.id:03d}] {inc.iso_timestamp[:19]} | "
            f"Cam: {inc.camera_id} | {inc.event_type} {dir_repr} | "
            f"Track #{inc.track_id} | Snapshot: {Path(inc.snapshot_path).name}"
        )
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="IBVAP Incident Management Demo")
    parser.add_argument(
        "--config",
        default="config/default_config.yaml",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=180,
        help="Maximum frames to process before stopping (default: 180)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode without window display",
    )
    parser.add_argument(
        "--save-video",
        type=str,
        default=None,
        help="Optional path to save annotated output video",
    )
    args = parser.parse_args()

    run_incident_pipeline(
        config_path=args.config,
        max_frames=args.max_frames,
        headless=args.headless,
        save_video_path=args.save_video,
    )


if __name__ == "__main__":
    main()
