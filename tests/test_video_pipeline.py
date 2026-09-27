"""
Unit tests for IBVAP AnnotatedVideoPipeline (Milestone 7B).
Validates pipeline initialization, single frame processing, JPEG encoding,
and multipart stream generator iteration with clean resource cleanup.
"""

import cv2
import numpy as np
import pytest

from core.video_pipeline import AnnotatedVideoPipeline


def test_video_pipeline_initialization():
    """Verify pipeline initializes all stages from default configuration."""
    pipeline = AnnotatedVideoPipeline()
    assert pipeline.detector is not None
    assert pipeline.tracker is not None
    assert pipeline.overlay_renderer is not None
    assert pipeline.camera_id == "CAM-01"


def test_video_pipeline_process_single_frame():
    """Verify offline single frame processing through detector, tracker, and overlay."""
    pipeline = AnnotatedVideoPipeline()
    test_frame = np.full((720, 1280, 3), 40, dtype=np.uint8)

    annotated, jpeg_bytes, tracks = pipeline.process_single_frame(
        frame=test_frame,
        frame_index=1,
        timestamp=100.0,
    )

    assert annotated.shape == (720, 1280, 3)
    assert annotated.dtype == np.uint8
    assert isinstance(jpeg_bytes, bytes)
    assert jpeg_bytes[:3] == b"\xff\xd8\xff"
    assert isinstance(tracks, list)
    assert pipeline.processed_count >= 1


def test_video_pipeline_stream_mjpeg_generator():
    """Verify MJPEG multipart stream generator emits valid boundary frames and stops cleanly."""
    pipeline = AnnotatedVideoPipeline()
    generator = pipeline.stream_mjpeg()

    # Extract first multipart frame
    first_chunk = next(generator)
    assert isinstance(first_chunk, bytes)
    assert b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" in first_chunk

    # Extract JPEG payload from chunk
    header = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    header_idx = first_chunk.find(header)
    assert header_idx >= 0
    jpeg_data = first_chunk[header_idx + len(header) : -2]  # strip trailing \r\n
    assert jpeg_data[:3] == b"\xff\xd8\xff"

    # Decode with OpenCV to confirm integrity
    nparr = np.frombuffer(jpeg_data, np.uint8)
    decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (720, 1280, 3)

    # Cleanly close generator to trigger finally block and release StreamReader
    generator.close()
