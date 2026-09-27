"""
IBVAP Milestone 2 Demo: AI Person Detection with YOLO11n
Integrates StreamReader with PersonDetector, executes real-time person detection,
renders tactical HUD bounding boxes with confidence scores, and measures pipeline FPS.
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
from core.stream_reader import StreamConfig, StreamReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ibvap.demo_detector")


def run_person_detection_demo(
    config_path: str = "config/default_config.yaml",
    max_frames: Optional[int] = None,
    headless: bool = False,
    save_snapshot: bool = True,
    save_video_path: Optional[str] = None,
) -> None:
    """Run the person detection demo pipeline."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file.resolve()}")

    # Load stream and detector configurations
    stream_cfg = StreamConfig.from_yaml(cfg_file)
    detector_cfg = DetectorConfig.from_yaml(cfg_file)

    logger.info("Initializing IBVAP Person Detection Pipeline...")
    logger.info(f"Video Source: {stream_cfg.get_source_target()}")
    logger.info(
        f"Detector Config -> Model: {detector_cfg.model_name} | "
        f"Conf Threshold: {detector_cfg.conf_threshold} | ImgSz: {detector_cfg.imgsz}"
    )

    # Initialize Person Detector
    detector = PersonDetector(detector_cfg)
    logger.info(f"Detector initialized using computing device: '{detector.device}'")

    video_writer = None
    if save_video_path:
        out_p = Path(save_video_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

    # Metrics counters
    total_processed = 0
    total_detections_count = 0
    total_inference_time_ms = 0.0
    start_time = time.time()
    fps_history = []
    last_frame_time = time.time()
    snapshot_saved = False

    logger.info("Starting video stream reading...")
    try:
        with StreamReader(stream_cfg) as reader:
            logger.info(f"Stream active: {reader.resolution} @ {reader.fps:.1f} FPS")

            # Setup video writer if requested
            if save_video_path:
                w, h = reader.resolution
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                video_writer = cv2.VideoWriter(save_video_path, fourcc, 30.0, (w, h))

            while reader.is_alive:
                if max_frames and total_processed >= max_frames:
                    logger.info(f"Reached specified max_frames limit ({max_frames}). Stopping.")
                    break

                success, frame, frame_idx, timestamp = reader.read(timeout=1.0)
                if not success or frame is None:
                    if not reader.is_alive:
                        logger.info("Stream ended.")
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

                # Run Person Detection
                result = detector.detect(frame, frame_index=frame_idx)
                total_detections_count += result.count
                total_inference_time_ms += result.inference_time_ms

                # Annotate Frame with Tactical HUD & Bounding Boxes
                annotated = detector.annotate_frame(frame, result, draw_feet=True, fps=avg_fps)

                # Write to video if configured
                if video_writer:
                    video_writer.write(annotated)

                # Save a sample verification snapshot
                if save_snapshot and not snapshot_saved and result.person_count > 0:
                    snap_dir = Path("data/snapshots")
                    snap_dir.mkdir(parents=True, exist_ok=True)
                    snap_file = snap_dir / "milestone2_detection_verification.jpg"
                    cv2.imwrite(str(snap_file), annotated)
                    logger.info(f"Saved verification snapshot with detections to: {snap_file}")
                    snapshot_saved = True

                # Periodic console telemetry
                if total_processed % 15 == 0 or total_processed == 1:
                    conf_str = (
                        f" (Confs: {[round(d.confidence, 2) for d in result.detections]})"
                        if result.count > 0
                        else ""
                    )
                    logger.info(
                        f"Frame {total_processed:04d} (Source: {frame_idx:04d}) | "
                        f"Detections: {result.person_count}{conf_str} | "
                        f"Inference: {result.inference_time_ms:.1f}ms | "
                        f"Pipeline FPS: {avg_fps:.1f}"
                    )

                # Display GUI if not headless
                if not headless:
                    try:
                        cv2.imshow("IBVAP - AI Border Surveillance (Press 'q' to quit)", annotated)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord("q") or key == 27:  # 'q' or ESC
                            logger.info("User requested quit via keyboard. Exiting cleanly...")
                            break
                    except cv2.error:
                        # Fallback for headless environments without DISPLAY
                        headless = True

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Terminating...")
    finally:
        if not headless:
            cv2.destroyAllWindows()
        if video_writer:
            video_writer.release()

    # Final summary telemetry
    total_time = time.time() - start_time
    effective_fps = total_processed / total_time if total_time > 0 else 0.0
    avg_inference_ms = (
        total_inference_time_ms / total_processed if total_processed > 0 else 0.0
    )

    logger.info("=" * 65)
    logger.info("IBVAP MILESTONE 2: AI PERSON DETECTION EXECUTION SUMMARY")
    logger.info("=" * 65)
    logger.info(f"Model:                 {detector.model_name}")
    logger.info(f"Computing Device:      {detector.device.upper()}")
    logger.info(f"Total Frames Scanned:  {total_processed}")
    logger.info(f"Total Detections:      {total_detections_count}")
    logger.info(f"Avg Inference Latency: {avg_inference_ms:.2f} ms per frame")
    logger.info(f"Pipeline Running Time: {total_time:.2f} s")
    logger.info(f"Overall Processing FPS:{effective_fps:.2f} FPS")
    logger.info("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="IBVAP Person Detection Demo")
    parser.add_argument(
        "--config",
        default="config/default_config.yaml",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum frames to process (useful for automated testing/benchmarking)",
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

    run_person_detection_demo(
        config_path=args.config,
        max_frames=args.max_frames,
        headless=args.headless,
        save_video_path=args.save_video,
    )


if __name__ == "__main__":
    main()
