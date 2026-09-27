"""
IBVAP Sample Video Generator & Transcoder
Prepares a realistic border surveillance video clip with real pedestrians
and border security OSD demarcation lines.
"""

import os
from pathlib import Path
import cv2
import numpy as np


def prepare_border_demo_video(
    source_avi: str = "data/sample_videos/vtest.avi",
    output_mp4: str = "data/sample_videos/border_perimeter_demo.mp4",
    target_width: int = 1280,
    target_height: int = 720,
    max_frames: int = 300,
    fps: float = 25.0,
) -> str:
    """
    Transcodes outdoor surveillance footage into a high-definition border
    surveillance demonstration video with tactical border patrol OSD overlays.
    """
    source_path = Path(source_avi)
    out_path = Path(output_mp4)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        import urllib.request
        url = "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/vtest.avi"
        print(f"[IBVAP] Downloading surveillance sample from: {url}")
        urllib.request.urlretrieve(url, str(source_path))

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source video: {source_path}")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (target_width, target_height))

    if not writer.isOpened():
        raise RuntimeError(f"Cannot create MP4 video writer: {out_path}")

    print(f"[IBVAP] Transcoding border surveillance demo to {out_path} ({max_frames} frames)...")
    frame_count = 0

    while frame_count < max_frames:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        frame_count += 1
        # Upscale to standard 720p HD surveillance resolution
        resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

        # Tactical OSD overlays
        cv2.putText(
            resized,
            "IBVAP TACTICAL SURVEILLANCE [CAM-01 / SECTOR CHARLIE]",
            (30, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 200),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            resized,
            f"LIVE FEED | FRAME: {frame_count:04d}/{max_frames:04d}",
            (30, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 255),
            1,
            cv2.LINE_AA,
        )

        # Virtual border line indicator across ground
        fence_x = int(target_width * 0.5)
        cv2.line(
            resized,
            (fence_x, 150),
            (fence_x, target_height - 60),
            (0, 140, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            resized,
            "PERIMETER DEMARCATION LINE",
            (fence_x - 120, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 180, 255),
            1,
            cv2.LINE_AA,
        )

        writer.write(resized)

    cap.release()
    writer.release()
    print(f"[IBVAP] Successfully created {out_path} with {frame_count} frames.")
    return str(out_path)


def generate_border_surveillance_video(
    output_path: str = "data/sample_videos/border_perimeter_demo.mp4",
    duration_sec: int = 10,
    fps: int = 30,
    width: int = 1280,
    height: int = 720,
) -> str:
    """Helper preserving original signature for test fixtures."""
    return prepare_border_demo_video(
        output_mp4=output_path,
        target_width=width,
        target_height=height,
        max_frames=duration_sec * fps,
        fps=float(fps),
    )


if __name__ == "__main__":
    prepare_border_demo_video()
