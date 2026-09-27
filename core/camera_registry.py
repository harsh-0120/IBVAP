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
    is_protected: bool = False
    zones: List[Dict[str, Any]] = field(default_factory=list)
    tripwires: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def exists_on_disk(self) -> bool:
        """Verify video presence (True for rtsp, checks file for files)."""
        if self.source_type == "rtsp":
            return True
        return Path(self.file_path).exists()

    def to_dict(self) -> Dict[str, Any]:
        """Convert camera definition to JSON serializable dictionary."""
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "file_path": self.file_path,
            "resolution": self.resolution,
            "source_fps": self.source_fps,
            "source_type": self.source_type,
            "aspect_ratio": self.aspect_ratio,
            "is_protected": self.is_protected,
            "zones": self.zones,
            "tripwires": self.tripwires,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraDefinition":
        """Instantiate camera definition from serialized dictionary."""
        return cls(
            camera_id=data["camera_id"],
            name=data.get("name", data["camera_id"]),
            file_path=data["file_path"],
            resolution=data.get("resolution", "1280x720"),
            source_fps=float(data.get("source_fps", 25.0)),
            source_type=data.get("source_type", "file"),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            is_protected=bool(data.get("is_protected", False)),
            zones=data.get("zones", []),
            tripwires=data.get("tripwires", []),
        )


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
        is_protected=True,
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
        zones=[],
        tripwires=[],
    ),
}

import json
import logging

logger = logging.getLogger("ibvap.camera_registry")

PERSISTENCE_FILE = Path("data/registered_cameras.json")
DYNAMIC_CAMERAS: Dict[str, CameraDefinition] = {}


def load_persisted_cameras(filepath: Path = PERSISTENCE_FILE) -> Dict[str, CameraDefinition]:
    """Load dynamically registered cameras from persistent JSON file."""
    p = Path(filepath)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            items = json.load(f)
            loaded = {}
            for item in items:
                cam = CameraDefinition.from_dict(item)
                loaded[cam.camera_id.upper()] = cam
            return loaded
    except Exception as exc:
        logger.warning(f"Failed to read camera persistence file '{p}': {exc}")
        return {}


def save_persisted_cameras(filepath: Path = PERSISTENCE_FILE) -> None:
    """Save dynamically registered cameras to JSON file."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump([cam.to_dict() for cam in DYNAMIC_CAMERAS.values()], f, indent=2)
    except Exception as exc:
        logger.warning(f"Failed to save camera persistence file '{p}': {exc}")


def register_camera(cam: CameraDefinition, persist: bool = True) -> CameraDefinition:
    """Register a new dynamic camera (uploaded video or RTSP stream)."""
    DYNAMIC_CAMERAS[cam.camera_id.upper()] = cam
    if persist:
        save_persisted_cameras()
    logger.info(f"Registered dynamic camera: {cam.camera_id} ({cam.name})")
    return cam


def remove_camera(camera_id: str, delete_file: bool = False, persist: bool = True) -> bool:
    """
    Remove a dynamically registered camera.
    Refuses deletion of baseline protected cameras (e.g. CAM-01).
    """
    cid = camera_id.upper()
    if cid in DEMO_CAMERAS:
        raise ValueError(f"Cannot remove protected baseline camera '{camera_id}'")
    cam = DYNAMIC_CAMERAS.pop(cid, None)
    if not cam:
        return False
    if delete_file and cam.source_type == "file":
        try:
            fp = Path(cam.file_path)
            if fp.exists():
                fp.unlink()
                logger.info(f"Removed uploaded footage on disk: {fp}")
        except Exception as exc:
            logger.warning(f"Failed to delete video file '{cam.file_path}': {exc}")
    if persist:
        save_persisted_cameras()
    return True


def get_camera(camera_id: str) -> Optional[CameraDefinition]:
    """Retrieve camera definition by ID (case-insensitive) from demo or dynamic cameras."""
    cid = camera_id.upper()
    cam = DEMO_CAMERAS.get(cid)
    if cam:
        if cam.camera_id == "CAM-01":
            file_path, resolution, fps = _get_cam01_source()
            cam.file_path = file_path
            cam.resolution = resolution
            cam.source_fps = fps
        return cam
    return DYNAMIC_CAMERAS.get(cid)


def list_cameras() -> List[CameraDefinition]:
    """List all registered surveillance camera definitions (demo baseline + dynamic)."""
    cam01 = DEMO_CAMERAS.get("CAM-01")
    if cam01:
        file_path, resolution, fps = _get_cam01_source()
        cam01.file_path = file_path
        cam01.resolution = resolution
        cam01.source_fps = fps

    return list(DEMO_CAMERAS.values()) + list(DYNAMIC_CAMERAS.values())


# Load any previously registered cameras on startup
DYNAMIC_CAMERAS.update(load_persisted_cameras())
