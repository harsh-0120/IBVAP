"""
IBVAP Milestone 4 Demo: Spatial Analytics (Virtual Fences & Directional Tripwires)
Full Pipeline Integration:
StreamReader -> PersonDetector (YOLO11n) -> ByteTrackTracker -> SpatialEngine.
Renders polygon restricted zones, directional tripwires, feet points,
breach alert highlights, and real-time perimeter status.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import cv2

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.detector import DetectorConfig, PersonDetector
from core.spatial_engine import SpatialConfig, SpatialEngine, SpatialEventType
from core.stream_reader import StreamConfig, StreamReader
from core.tracker import ByteTrackTracker, TrackerConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ibvap.demo_spatial")


def run_spatial_analytics_demo(
    config_path: str = "config/default_config.yaml",
    max_frames: Optional[int] = None,
    headless: bool = False,
    save_snapshot: bool = True,
    save_video_path: Optional[str] = None,
) -> None:
    """Execute the spatial analytics demonstration."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file.resolve()}")

    # Load all pipeline configurations
    stream_cfg = StreamConfig.from_yaml(cfg_file)
    detector_cfg = DetectorConfig.from_yaml(cfg_file)
    tracker_cfg = TrackerConfig.from_yaml(cfg_file)
    spatial_cfg = SpatialConfig.from_yaml(cfg_file)

    logger.info("Initializing IBVAP Integrated Spatial Analytics Pipeline...")
    logger.info(f"Video Source:  {stream_cfg.get_source_target()}")
    logger.info(f"AI Detector:   {detector_cfg.model_name} (device={detector_cfg.device})")
    logger.info(f"MOT Tracker:   {tracker_cfg.tracker_type.upper()}")
    logger.info(
        f"Spatial Engine: {len(spatial_cfg.zones)} Zones, {len(spatial_cfg.tripwires)} Tripwires "
        f"(cooldown={spatial_cfg.cooldown_sec}s)"
    )

    # Initialize all pipeline components
    detector = PersonDetector(detector_cfg)
    tracker = ByteTrackTracker(tracker_cfg)
    spatial_engine = SpatialEngine(spatial_cfg)

    logger.info(f"Computing Device: '{detector.device}'")

    video_writer = None
    if save_video_path:
        out_p = Path(save_video_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

    # Telemetry and event tracking
    total_processed = 0
    total_detections_count = 0
    active_tracks_sum = 0
    all_triggered_events = []
    directions_observed = set()
    fps_history = []
    last_frame_time = time.time()
    start_time = time.time()
    snapshot_saved = False

    logger.info("Starting video stream reading...")
    try:
        with StreamReader(stream_cfg) as reader:
            logger.info(f"Stream active: {reader.resolution} @ {reader.fps:.1f} FPS")

            if save_video_path:
                w, h = reader.resolution
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                video_writer = cv2.VideoWriter(save_video_path, fourcc, 25.0, (w, h))

            while reader.is_alive:
                if max_frames and total_processed >= max_frames:
                    logger.info(f"Reached limit of {max_frames} frames. Stopping.")
                    break

                success, frame, frame_idx, timestamp = reader.read(timeout=1.0)
                if not success or frame is None:
                    if not reader.is_alive:
                        break
                    continue

                total_processed += 1
                now = time.time()
                dt = now - last_frame_time
                last_frame_time = now
                current_fps = 1.0 / dt if dt > 0 else 30.0
                fps_history.append(current_fps)
                if len(fps_history) > 30:
                    fps_history.pop(0)
                avg_fps = sum(fps_history) / len(fps_history)

                # 1. Detection
                det_result = detector.detect(frame, frame_index=frame_idx)
                total_detections_count += det_result.count

                # 2. Tracking
                trk_result = tracker.update(
                    det_result, frame_index=frame_idx, timestamp=timestamp
                )
                active_tracks_sum += trk_result.active_count

                # 3. Spatial Analytics
                events, active_states = spatial_engine.process_tracks(
                    trk_result.tracks, frame_index=frame_idx, timestamp=timestamp
                )

                if events:
                    for ev in events:
                        all_triggered_events.append(ev)
                        if ev.direction:
                            directions_observed.add(ev.direction.value)
                        logger.info(f"==> SECURITY EVENT: {ev.to_dict()}")

                # 4. Comprehensive Tactical Visualization
                # First annotate tracks (boxes, IDs, trails)
                annotated = tracker.annotate_frame(
                    frame,
                    trk_result,
                    draw_trails=True,
                    draw_feet=True,
                    fps=avg_fps,
                )
                # Then overlay spatial polygons, tripwires, breach banners, and counters
                annotated = spatial_engine.annotate_frame(
                    annotated,
                    trk_result.tracks,
                    events,
                    active_states,
                )

                if video_writer:
                    video_writer.write(annotated)

                # Save verification snapshot
                if save_snapshot and not snapshot_saved and (events or total_processed >= 30):
                    snap_dir = Path("data/snapshots")
                    snap_dir.mkdir(parents=True, exist_ok=True)
                    snap_file = snap_dir / "milestone4_spatial_verification.jpg"
                    cv2.imwrite(str(snap_file), annotated)
                    logger.info(f"Saved spatial analytics verification snapshot to: {snap_file}")
                    snapshot_saved = True

                # Periodic console telemetry
                if total_processed % 15 == 0 or total_processed == 1:
                    logger.info(
                        f"Frame {total_processed:04d} (Source: {frame_idx:04d}) | "
                        f"Active Tracks: {trk_result.active_count} | "
                        f"Intrusions: {spatial_engine.total_intrusions} | "
                        f"Crossings: {spatial_engine.total_crossings} | "
                        f"Pipeline FPS: {avg_fps:.1f}"
                    )

                # Interactive display window
                if not headless:
                    try:
                        cv2.imshow(
                            "IBVAP - Tactical Spatial Analytics (Press 'q' to quit)",
                            annotated,
                        )
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord("q") or key == 27:
                            logger.info("User requested quit. Exiting cleanly...")
                            break
                    except cv2.error:
                        headless = True

    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting...")
    finally:
        if not headless:
            cv2.destroyAllWindows()
        if video_writer:
            video_writer.release()

    # Final summary telemetry
    total_time = time.time() - start_time
    effective_fps = total_processed / total_time if total_time > 0 else 0.0
    avg_active_tracks = (
        active_tracks_sum / total_processed if total_processed > 0 else 0.0
    )

    logger.info("=" * 70)
    logger.info("IBVAP MILESTONE 4: SPATIAL ANALYTICS EXECUTION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Detector Model:          {detector.model_name}")
    logger.info(f"Computing Device:        {detector.device.upper()}")
    logger.info(f"Tracker Backend:         {tracker.config.tracker_type.upper()}")
    logger.info(f"Total Frames Processed:  {total_processed}")
    logger.info(f"Total Raw Detections:    {total_detections_count}")
    logger.info(f"Average Active Tracks:   {avg_active_tracks:.2f} targets/frame")
    logger.info(f"Total Zone Intrusions:   {spatial_engine.total_intrusions}")
    logger.info(f"Total Tripwire Crossings:{spatial_engine.total_crossings}")
    logger.info(f"Crossing Directions:     {list(directions_observed) if directions_observed else 'None'}")
    logger.info(f"Pipeline Running Time:   {total_time:.2f} s")
    logger.info(f"Measured Overall FPS:    {effective_fps:.2f} FPS")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="IBVAP Spatial Analytics Demo")
    parser.add_argument(
        "--config",
        default="config/default_config.yaml",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum frames to process before stopping",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI window display",
    )
    parser.add_argument(
        "--save-video",
        type=str,
        default=None,
        help="Optional path to save annotated output MP4 video",
    )
    args = parser.parse_args()

    run_spatial_analytics_demo(
        config_path=args.config,
        max_frames=args.max_frames,
        headless=args.headless,
        save_video_path=args.save_video,
    )


if __name__ == "__main__":
    main()
