"""
IBVAP Real-Time Annotated Video Streaming Pipeline
Coordinates StreamReader -> PersonDetector (YOLO11n) -> ByteTrackTracker -> OverlayRenderer -> MJPEG generation.
Strictly decoupled from IncidentManager / database persistence.
"""

from collections import deque
import logging
from pathlib import Path
import time
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import cv2
import numpy as np

from core.detector import ALL_SURVEILLANCE_CLASS_IDS, DetectorConfig, PersonDetector, YOLODetector
from core.overlay_renderer import OverlayConfig, OverlayRenderer
from core.stream_reader import StreamConfig, StreamReader
from core.tracker import ByteTrackTracker, Track, TrackerConfig

logger = logging.getLogger("ibvap.video_pipeline")


class AnnotatedVideoPipeline:
    """
    Server-side computer vision video processing pipeline.
    Produces live annotated MJPEG frames with YOLO11n detection and ByteTrack tracking overlays.
    """

    def __init__(
        self,
        config_path: Union[str, Path] = "config/default_config.yaml",
        camera_id: str = "CAM-01",
    ):
        self.config_path = Path(config_path)
        self.camera_id = camera_id

        # 1. Load component configurations
        if self.config_path.exists():
            self.stream_cfg = StreamConfig.from_yaml(self.config_path)
            self.detector_cfg = DetectorConfig.from_yaml(self.config_path)
            self.tracker_cfg = TrackerConfig.from_yaml(self.config_path)
            self.overlay_cfg = OverlayConfig.from_yaml(self.config_path)
        else:
            self.stream_cfg = StreamConfig()
            self.detector_cfg = DetectorConfig()
            self.tracker_cfg = TrackerConfig()
            self.overlay_cfg = OverlayConfig()

        # 2. Instantiate pipeline stages (Single-pass multi-class YOLO detection)
        target_classes = self.detector_cfg.target_classes or ALL_SURVEILLANCE_CLASS_IDS
        self.detector = YOLODetector(self.detector_cfg, target_classes=target_classes)
        self.tracker = ByteTrackTracker(self.tracker_cfg)
        self.overlay_renderer = OverlayRenderer(self.overlay_cfg)

        # Performance monitoring
        self._fps_history = deque(maxlen=30)
        self._last_frame_time = time.perf_counter()
        self._processed_frames = 0
        self._last_fps = 0.0

    @property
    def current_fps(self) -> float:
        """Rolling average processing FPS."""
        return self._last_fps

    @property
    def processed_count(self) -> int:
        """Total frames processed by this pipeline instance."""
        return self._processed_frames

    def process_single_frame(
        self,
        frame: np.ndarray,
        frame_index: int = 0,
        timestamp: Optional[float] = None,
    ) -> Tuple[np.ndarray, bytes, List[Track]]:
        """
        Process a single image frame through Detection -> Tracking -> Overlay -> JPEG encoding.
        Non-streaming method suitable for unit testing and offline inspection.

        Returns:
            Tuple of (annotated_frame, jpeg_bytes, active_tracks)
        """
        ts = timestamp if timestamp is not None else time.time()

        # 1. Detect persons with YOLO11n
        det_result = self.detector.detect(frame, frame_index=frame_index)

        # 2. Update ByteTrack tracker
        trk_result = self.tracker.update(det_result, frame_index=frame_index, timestamp=ts)

        # 3. Calculate rolling FPS
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        if dt > 0:
            self._fps_history.append(1.0 / dt)
            self._last_fps = sum(self._fps_history) / len(self._fps_history)

        self._processed_frames += 1

        # 4. Render overlay annotations
        annotated = self.overlay_renderer.render(
            frame=frame,
            tracks=trk_result.tracks,
            fps=self._last_fps,
            camera_id=self.camera_id,
        )

        # 5. Compress to JPEG
        jpeg_bytes = self.overlay_renderer.encode_jpeg(annotated)

        return annotated, jpeg_bytes, trk_result.tracks

    def stream_mjpeg(self) -> Generator[bytes, None, None]:
        """
        Continuous generator producing multipart/x-mixed-replace MJPEG stream chunks.
        Safely starts StreamReader on demand and releases all video resources upon client disconnect.
        """
        reader = StreamReader(self.stream_cfg)
        reader.start()
        logger.info("Annotated video streaming pipeline started.")

        try:
            while reader.is_alive:
                success, frame, frame_idx, ts = reader.read(timeout=1.0)
                if not success or frame is None:
                    if not reader.is_alive:
                        break
                    time.sleep(0.01)
                    continue

                _, jpeg_bytes, _ = self.process_single_frame(
                    frame=frame,
                    frame_index=frame_idx,
                    timestamp=ts,
                )

                # HTTP multipart boundary chunk
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )

        except (GeneratorExit, ConnectionResetError) as e:
            logger.debug(f"Client disconnected from annotated stream: {e}")
        except Exception as e:
            logger.warning(f"Error in annotated video stream generator: {e}")
        finally:
            reader.stop()
            logger.info("Annotated video streaming pipeline stopped and resources released.")
