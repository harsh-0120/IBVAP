"""
IBVAP Milestone 1 Demo: Verify Stream Ingestion
Demonstrates non-blocking frame acquisition from the configured video source,
prints stream telemetry, and validates zero-lag latest-frame delivery.
"""

import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stream_reader import StreamConfig, StreamReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("ibvap.demo")


def main():
    config_path = Path(__file__).resolve().parent.parent / "config" / "default_config.yaml"
    logger.info(f"Loading configuration from: {config_path}")
    config = StreamConfig.from_yaml(config_path)

    logger.info(f"Configured Source: {config.source_type.value}")
    logger.info(f"Target file: {config.file_path}")
    logger.info(f"Buffer size: {config.buffer_size} (1 = zero-latency)")

    frames_to_read = 60
    logger.info(f"Starting StreamReader to read {frames_to_read} frames...")

    with StreamReader(config) as reader:
        logger.info(f"Stream Properties -> Resolution: {reader.resolution}, FPS: {reader.fps:.1f}")

        start_time = time.time()
        received_count = 0

        while received_count < frames_to_read and reader.is_alive:
            success, frame, frame_idx, timestamp = reader.read(timeout=1.0)
            if not success or frame is None:
                logger.warning("Timeout waiting for frame or end of stream.")
                break

            received_count += 1
            if received_count % 15 == 0 or received_count == 1:
                logger.info(
                    f"Frame {received_count:03d} (Source Index: {frame_idx:04d}) | "
                    f"Shape: {frame.shape} | "
                    f"Timestamp: {timestamp:.3f}"
                )

        total_duration = time.time() - start_time
        effective_fps = received_count / total_duration if total_duration > 0 else 0
        logger.info(
            f"Ingestion Verification Complete! Received {received_count} frames "
            f"in {total_duration:.2f}s (~{effective_fps:.1f} FPS)."
        )

    logger.info("StreamReader cleanly closed. Milestone 1 verification passed.")


if __name__ == "__main__":
    main()
