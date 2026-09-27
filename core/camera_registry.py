"""
IBVAP Camera Registry
Provides metadata, filesystem sources, and calibrated spatial boundaries for demo surveillance nodes.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class CameraDefinition:
    """Surveillance camera node metadata and spatial configuration."""
    camera_id: str
    name: str
    file_path: str
    resolution: str
    source_fps: float
    source_type: str = "file"
    aspect_ratio: str = "16:9"
    zones: List[Dict[str, Any]] = field(default_factory=list)
    tripwires: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def exists_on_disk(self) -> bool:
        """Verify video file presence."""
        return Path(self.file_path).exists()


def _get_cam01_source() -> Tuple[str, str, float]:
    """Retrieve CAM-01 video file path, resolution, and source FPS from config or defaults."""
    cfg_path = Path("config/default_config.yaml")
    file_path = "data/sample_videos/border_perimeter_demo.mp4"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                configured_file = cfg.get("video", {}).get("file_path")
                if configured_file and Path(configured_file).exists():
                    file_path = configured_file
        except Exception:
            pass

    if "vtest.avi" in file_path.lower():
        return file_path, "768x576", 10.0
    return file_path, "1280x720", 25.0


_cam01_path, _cam01_res, _cam01_fps = _get_cam01_source()

# Surveillance CCTV demo cameras with calibrated spatial boundaries
DEMO_CAMERAS: Dict[str, CameraDefinition] = {
    "CAM-01": CameraDefinition(
        camera_id="CAM-01",
        name="Border Perimeter",
        file_path=_cam01_path,
        resolution=_cam01_res,
        source_fps=_cam01_fps,
        source_type="file",
        aspect_ratio="16:9",
        zones=[
            {
                "id": "CAM-01-zone-01",
                "name": "Restricted Sector Bravo",
                "points": [(750, 260), (1220, 260), (1220, 560), (750, 560)],
            }
        ],
        tripwires=[
            {
                "id": "CAM-01-wire-01",
                "name": "Perimeter Demarcation Wire",
                "start": (800, 250),
                "end": (800, 570),
            }
        ],
    ),
    "CAM-02": CameraDefinition(
        camera_id="CAM-02",
        name="Highway Surveillance",
        file_path="data/sample_videos/13650838_3840_2160_30fps.mp4",
        resolution="3840x2160",
        source_fps=30.0,
        source_type="file",
        aspect_ratio="16:9",
        zones=[
            {
                "id": "CAM-02-zone-01",
                "name": "Highway Inspection Sector",
                "points": [(1000, 1300), (2800, 1300), (2800, 1900), (1000, 1900)],
            }
        ],
        tripwires=[
            {
                "id": "CAM-02-wire-01",
                "name": "Highway Checkpoint Wire",
                "start": (2000, 1200),
                "end": (2000, 2000),
            }
        ],
    ),
    "CAM-03": CameraDefinition(
        camera_id="CAM-03",
        name="Overhead Traffic",
        file_path="data/sample_videos/12205172_2160_3840_60fps.mp4",
        resolution="2160x3840",
        source_fps=60.0,
        source_type="file",
        aspect_ratio="9:16",
        # Spatial boundaries disabled for CAM-03 per user instruction
        # since steep overhead queue angle lacks clear demarcation boundaries
        zones=[],
        tripwires=[],
    ),
}


def get_camera(camera_id: str) -> Optional[CameraDefinition]:
    """Retrieve camera definition by ID (case-insensitive)."""
    cam = DEMO_CAMERAS.get(camera_id.upper())
    if cam and cam.camera_id == "CAM-01":
        file_path, resolution, fps = _get_cam01_source()
        cam.file_path = file_path
        cam.resolution = resolution
        cam.source_fps = fps
    return cam


def list_cameras() -> List[CameraDefinition]:
    """List all registered demo camera definitions in order."""
    cam01 = DEMO_CAMERAS.get("CAM-01")
    if cam01:
        file_path, resolution, fps = _get_cam01_source()
        cam01.file_path = file_path
        cam01.resolution = resolution
        cam01.source_fps = fps
    return list(DEMO_CAMERAS.values())
