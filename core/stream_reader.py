"""
IBVAP Video Ingestion Layer: Stream Reader
Provides non-blocking, zero-latency frame ingestion with support for local MP4 files,
USB/system webcams, and RTSP IP camera streams.
"""

import enum
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import cv2
import numpy as np
import yaml

logger = logging.getLogger("ibvap.stream_reader")


class StreamSourceType(str, enum.Enum):
    """Supported video input source types."""
    FILE = "file"
    WEBCAM = "webcam"
    RTSP = "rtsp"


@dataclass
class StreamConfig:
    """Configuration specification for a video input stream."""
    source_type: StreamSourceType = StreamSourceType.FILE
    file_path: Optional[str] = None
    webcam_index: int = 0
    rtsp_url: Optional[str] = None
    loop: bool = True
    buffer_size: int = 1
    reconnect_delay_sec: float = 2.0
    target_fps: Optional[float] = None

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "StreamConfig":
        """Load stream configuration from a YAML file."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        video_cfg: Dict[str, Any] = data.get("video", {})
        source_type_str = video_cfg.get("source_type", "file").lower()

        try:
            source_type = StreamSourceType(source_type_str)
        except ValueError:
            valid_sources = [s.value for s in StreamSourceType]
            raise ValueError(
                f"Invalid source_type '{source_type_str}'. Allowed values: {valid_sources}"
            )

        return cls(
            source_type=source_type,
            file_path=video_cfg.get("file_path"),
            webcam_index=int(video_cfg.get("webcam_index", 0)),
            rtsp_url=video_cfg.get("rtsp_url"),
            loop=bool(video_cfg.get("loop", True)),
            buffer_size=max(1, int(video_cfg.get("buffer_size", 1))),
            reconnect_delay_sec=float(video_cfg.get("reconnect_delay_sec", 2.0)),
            target_fps=video_cfg.get("target_fps"),
        )

    def get_source_target(self) -> Union[str, int]:
        """Resolve the OpenCV VideoCapture target parameter."""
        if self.source_type == StreamSourceType.FILE:
            if not self.file_path:
                raise ValueError("file_path must be specified when source_type is 'file'")
            resolved_path = Path(self.file_path)
            if not resolved_path.exists():
                raise FileNotFoundError(f"Video file does not exist: {resolved_path.resolve()}")
            return str(resolved_path.resolve())

        elif self.source_type == StreamSourceType.WEBCAM:
            return self.webcam_index

        elif self.source_type == StreamSourceType.RTSP:
            if not self.rtsp_url:
                raise ValueError("rtsp_url must be specified when source_type is 'rtsp'")
            return self.rtsp_url

        raise ValueError(f"Unsupported source type: {self.source_type}")


class StreamReader:
    """
    Non-blocking, threaded video stream reader.

    Implements a zero-lag latest-frame ring buffer strategy to ensure downstream
    AI inference components always process the most recent available frame without
    accumulating a backlog delay.
    """

    def __init__(self, config: StreamConfig):
        self.config = config
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()

        # Thread-safe ring buffer: capacity is fixed (default 1 for latest frame)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=self.config.buffer_size)

        # Stream metadata
        self._width: int = 0
        self._height: int = 0
        self._fps: float = 30.0
        self._total_frames: int = -1
        self._frame_index: int = 0
        self._last_frame_time: float = 0.0
        self._eof_reached: bool = False

        # Lock for thread-safe state inspection
        self._lock = threading.Lock()

    @property
    def is_alive(self) -> bool:
        """Returns True if the reader thread is actively running and stream is open."""
        return self._running and not self._eof_reached

    @property
    def resolution(self) -> Tuple[int, int]:
        """Returns (width, height) of the video feed."""
        return self._width, self._height

    @property
    def fps(self) -> float:
        """Returns nominal frames per second of the source."""
        return self._fps

    @property
    def total_frames(self) -> int:
        """Returns total frame count for files (-1 for live streams)."""
        return self._total_frames

    @property
    def current_frame_index(self) -> int:
        """Returns the sequential index of the latest read frame."""
        return self._frame_index

    @property
    def source_description(self) -> str:
        """Human-readable description of current video source."""
        if self.config.source_type == StreamSourceType.FILE:
            return f"File({self.config.file_path})"
        elif self.config.source_type == StreamSourceType.WEBCAM:
            return f"Webcam(Index: {self.config.webcam_index})"
        elif self.config.source_type == StreamSourceType.RTSP:
            return f"RTSP({self.config.rtsp_url})"
        return "Unknown"

    def _open_capture(self) -> bool:
        """Open the cv2.VideoCapture instance according to configuration."""
        target = self.config.get_source_target()
        logger.info(f"Opening video source: {self.source_description}")

        if self.config.source_type == StreamSourceType.RTSP:
            # Set transport hints for RTSP (TCP preferred to prevent packet drop)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

        self._cap = cv2.VideoCapture(target)

        if not self._cap.isOpened():
            logger.error(f"Failed to open video source: {self.source_description}")
            return False

        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        nominal_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._fps = nominal_fps if nominal_fps > 0 else 30.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logger.info(
            f"Stream connected successfully: {self.source_description} | "
            f"Resolution: {self._width}x{self._height} | FPS: {self._fps:.1f} | "
            f"Total Frames: {self._total_frames}"
        )
        return True

    def start(self) -> "StreamReader":
        """Start the background ingestion thread."""
        with self._lock:
            if self._running:
                logger.warning("StreamReader is already running.")
                return self

            if not self._open_capture():
                raise RuntimeError(f"Unable to initialize stream source: {self.source_description}")

            self._stop_event.clear()
            self._running = True
            self._eof_reached = False
            self._frame_index = 0

            self._thread = threading.Thread(
                target=self._worker_loop,
                name=f"StreamReader-{self.config.source_type.value}",
                daemon=True,
            )
            self._thread.start()
            logger.info("StreamReader background thread started.")
            return self

    def _worker_loop(self) -> None:
        """
        Background worker loop: continuously reads frames from source
        and maintains a zero-lag latest-frame queue.
        """
        frame_interval = 1.0 / self.config.target_fps if self.config.target_fps else (1.0 / self._fps if self.config.source_type == StreamSourceType.FILE else 0.0)

        while not self._stop_event.is_set():
            loop_start_time = time.time()

            if self._cap is None or not self._cap.isOpened():
                if self.config.source_type in (StreamSourceType.RTSP, StreamSourceType.WEBCAM):
                    logger.warning(
                        f"Stream disconnected. Retrying in {self.config.reconnect_delay_sec}s..."
                    )
                    time.sleep(self.config.reconnect_delay_sec)
                    if not self._open_capture():
                        continue
                else:
                    break

            success, frame = self._cap.read()

            if not success or frame is None:
                # End of Stream reached
                if self.config.source_type == StreamSourceType.FILE and self.config.loop:
                    logger.debug("End of video reached. Looping back to frame 0.")
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.info(f"Stream reached End-Of-File (EOF): {self.source_description}")
                    self._eof_reached = True
                    break

            self._frame_index += 1
            timestamp = time.time()
            package = (True, frame, self._frame_index, timestamp)

            # Latest-frame strategy: if queue full, drop stale frame
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass

            try:
                self._frame_queue.put_nowait(package)
            except queue.Full:
                pass

            # Throttle frame rate for local video files to mimic real-time camera speed
            if frame_interval > 0:
                elapsed = time.time() - loop_start_time
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        self._running = False
        logger.info("StreamReader worker loop terminated.")

    def read(self, timeout: float = 1.0) -> Tuple[bool, Optional[np.ndarray], int, float]:
        """
        Retrieve the latest frame from the buffer.

        Returns:
            Tuple: (success: bool, frame: Optional[np.ndarray], frame_index: int, timestamp: float)
        """
        try:
            return self._frame_queue.get(block=True, timeout=timeout)
        except queue.Empty:
            if self._eof_reached or not self._running:
                return False, None, self._frame_index, time.time()
            return False, None, self._frame_index, time.time()

    def stop(self) -> None:
        """Gracefully stop the worker thread and release hardware/file resources."""
        with self._lock:
            if not self._running and self._cap is None:
                return

            logger.info("Stopping StreamReader...")
            self._stop_event.set()
            self._running = False

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

            if self._cap is not None:
                self._cap.release()
                self._cap = None

            # Drain any remaining frames in queue
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break

            logger.info("StreamReader stopped and resources released.")

    def __enter__(self) -> "StreamReader":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
