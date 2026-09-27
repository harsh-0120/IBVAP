"""
Tests for IBVAP Stream Ingestion Layer.
"""

import time
from pathlib import Path
import pytest
import numpy as np

from core.stream_reader import StreamConfig, StreamReader, StreamSourceType
from scripts.generate_sample_video import generate_border_surveillance_video


@pytest.fixture(scope="session")
def sample_video_path(tmp_path_factory) -> str:
    """Fixture providing a guaranteed sample video file for tests."""
    temp_dir = tmp_path_factory.mktemp("video_data")
    video_file = temp_dir / "test_surveillance.mp4"
    generate_border_surveillance_video(
        output_path=str(video_file),
        duration_sec=2,
        fps=30,
        width=640,
        height=360,
    )
    return str(video_file)


def test_config_validation(tmp_path):
    """Test StreamConfig validation rules."""
    # Non-existent file should raise FileNotFoundError when resolving target
    cfg = StreamConfig(
        source_type=StreamSourceType.FILE,
        file_path="non_existent_file_path_12345.mp4"
    )
    with pytest.raises(FileNotFoundError):
        cfg.get_source_target()

    # Missing RTSP url
    rtsp_cfg = StreamConfig(source_type=StreamSourceType.RTSP, rtsp_url=None)
    with pytest.raises(ValueError, match="rtsp_url must be specified"):
        rtsp_cfg.get_source_target()

    # Missing file path
    file_cfg = StreamConfig(source_type=StreamSourceType.FILE, file_path=None)
    with pytest.raises(ValueError, match="file_path must be specified"):
        file_cfg.get_source_target()


def test_config_from_yaml(tmp_path):
    """Test loading configuration from YAML."""
    yaml_content = """
video:
  source_type: "file"
  file_path: "some_video.mp4"
  loop: false
  buffer_size: 1
"""
    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    cfg = StreamConfig.from_yaml(yaml_file)
    assert cfg.source_type == StreamSourceType.FILE
    assert cfg.file_path == "some_video.mp4"
    assert cfg.loop is False
    assert cfg.buffer_size == 1


def test_stream_reader_read_frames(sample_video_path):
    """Test reading valid frames from a video file."""
    config = StreamConfig(
        source_type=StreamSourceType.FILE,
        file_path=sample_video_path,
        loop=True,
        buffer_size=1,
    )

    with StreamReader(config) as reader:
        assert reader.is_alive
        width, height = reader.resolution
        assert width == 640
        assert height == 360
        assert reader.fps == 30.0

        frames_read = 0
        for _ in range(10):
            success, frame, idx, ts = reader.read(timeout=1.0)
            assert success is True
            assert frame is not None
            assert isinstance(frame, np.ndarray)
            assert frame.shape == (360, 640, 3)
            assert idx > 0
            assert ts > 0
            frames_read += 1

        assert frames_read == 10

    # Reader should be stopped after exiting context
    assert not reader.is_alive


def test_stream_reader_latest_frame_strategy(sample_video_path):
    """
    Test zero-lag latest-frame drop behavior.
    When consumer pauses, backlog frames must be discarded,
    and subsequent read should yield an advanced frame index.
    """
    config = StreamConfig(
        source_type=StreamSourceType.FILE,
        file_path=sample_video_path,
        loop=True,
        buffer_size=1,
    )

    with StreamReader(config) as reader:
        # Read first frame
        success1, frame1, idx1, _ = reader.read(timeout=1.0)
        assert success1 is True

        # Simulate heavy downstream processing (150ms delay @ 30fps = ~4-5 frames produced)
        time.sleep(0.18)

        # Next read should skip frames and return latest
        success2, frame2, idx2, _ = reader.read(timeout=1.0)
        assert success2 is True
        assert idx2 > idx1 + 1, f"Expected frame skipping due to latest-frame buffer, got {idx1} -> {idx2}"


def test_stream_reader_eof_non_looping(sample_video_path):
    """Test clean EOF handling when loop=False."""
    config = StreamConfig(
        source_type=StreamSourceType.FILE,
        file_path=sample_video_path,
        loop=False,
        buffer_size=1,
    )

    with StreamReader(config) as reader:
        count = 0
        start_t = time.time()
        while reader.is_alive and (time.time() - start_t < 5.0):
            success, frame, idx, _ = reader.read(timeout=0.2)
            if success:
                count += 1
            time.sleep(0.01)

        assert not reader.is_alive
        # Subsequent read returns False
        success, frame, _, _ = reader.read(timeout=0.1)
        assert success is False
        assert frame is None
