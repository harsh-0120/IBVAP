"""
CAM-01 Vehicle Detection Recall & Quality Controlled A/B Evaluation
Compares detection recall, ByteTrack association, and FPS across:
- Config A:  conf=0.25, imgsz=640 (Production Baseline)
- Config B:  conf=0.18, imgsz=640
- Config C:  conf=0.25, imgsz=960
- Config D1: conf=0.18, imgsz=800
- Config D2: conf=0.18, imgsz=960
- Config E:  conf=0.18, imgsz=800 with tracker new_track_thresh=0.18, track_high_thresh=0.18 (Tracker Sensitivity Variant)
"""

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from core.camera_registry import get_camera
from core.detector import (
    ALL_SURVEILLANCE_CLASS_IDS,
    COCO_VEHICLE_CLASSES,
    DetectorConfig,
    YOLODetector,
)
from core.overlay_renderer import OverlayConfig, OverlayRenderer
from core.tracker import ByteTrackTracker, TrackerConfig


@dataclass
class ExpConfig:
    name: str
    label: str
    conf_threshold: float
    imgsz: int
    iou_threshold: float = 0.45
    tracker_new_thresh: float = 0.25
    tracker_high_thresh: float = 0.25
    tracker_low_thresh: float = 0.10


def run_experiment(
    video_path: str,
    configs: List[ExpConfig],
    max_frames: int = 150,
    save_frame_indices: Optional[List[int]] = None,
    output_dir: str = "data/validation_snapshots",
) -> Dict[str, Any]:
    if save_frame_indices is None:
        save_frame_indices = [30, 75, 120]

    os.makedirs(output_dir, exist_ok=True)

    # Read the 150 frames into memory once to ensure identical inputs and eliminate disk read variance
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video at {video_path}")

    frames: List[np.ndarray] = []
    for _ in range(max_frames):
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        frames.append(frame)
    cap.release()

    total_frames = len(frames)
    print(f"Loaded {total_frames} frames from {video_path} into memory for evaluation.")

    results: Dict[str, Any] = {}

    # Initialize shared overlay renderer
    overlay_renderer = OverlayRenderer(OverlayConfig(show_box=True, show_track_id=True, show_confidence=True))

    for exp in configs:
        print(f"\n========================================================")
        print(f"Evaluating {exp.name}: {exp.label}")
        print(f"Params: conf={exp.conf_threshold}, imgsz={exp.imgsz}, "
              f"tracker_new_thresh={exp.tracker_new_thresh}, tracker_high_thresh={exp.tracker_high_thresh}")
        print(f"========================================================")

        det_cfg = DetectorConfig(
            model_name="yolo11n.pt",
            conf_threshold=exp.conf_threshold,
            iou_threshold=exp.iou_threshold,
            imgsz=exp.imgsz,
            device="auto",
            target_classes=ALL_SURVEILLANCE_CLASS_IDS,
        )
        detector = YOLODetector(det_cfg, target_classes=ALL_SURVEILLANCE_CLASS_IDS)

        trk_cfg = TrackerConfig(
            track_high_thresh=exp.tracker_high_thresh,
            track_low_thresh=exp.tracker_low_thresh,
            new_track_thresh=exp.tracker_new_thresh,
            track_buffer=30,
            match_thresh=0.80,
            target_classes=["person", "car", "motorcycle", "bus", "truck"],
        )
        tracker = ByteTrackTracker(trk_cfg)

        # Metrics accumulators
        raw_person_count = 0
        raw_car_count = 0
        raw_motorcycle_count = 0
        raw_bus_count = 0
        raw_truck_count = 0
        raw_vehicle_count = 0
        raw_dets_below_025 = 0

        tracked_vehicle_counts_per_frame: List[int] = []
        active_track_ids_seen: set = set()
        active_vehicle_track_ids_seen: set = set()
        active_person_track_ids_seen: set = set()

        inference_times_ms: List[float] = []
        total_frame_times_ms: List[float] = []

        # Warm up detector with frame 0
        detector.detect(frames[0], frame_index=0)

        for idx, frame in enumerate(frames):
            t_start = time.perf_counter()

            # 1. Detection
            det_result = detector.detect(frame, frame_index=idx)
            t_det_end = time.perf_counter()

            # Raw detection tally
            for det in det_result.detections:
                cname = det.class_name.lower()
                if det.confidence < 0.25:
                    raw_dets_below_025 += 1

                if cname == "person":
                    raw_person_count += 1
                elif cname == "car":
                    raw_car_count += 1
                    raw_vehicle_count += 1
                elif cname == "motorcycle":
                    raw_motorcycle_count += 1
                    raw_vehicle_count += 1
                elif cname == "bus":
                    raw_bus_count += 1
                    raw_vehicle_count += 1
                elif cname == "truck":
                    raw_truck_count += 1
                    raw_vehicle_count += 1

            # 2. Tracking
            trk_result = tracker.update(det_result, frame_index=idx, timestamp=idx / 60.0)
            t_frame_end = time.perf_counter()

            inf_ms = (t_det_end - t_start) * 1000.0
            tot_ms = (t_frame_end - t_start) * 1000.0
            inference_times_ms.append(inf_ms)
            total_frame_times_ms.append(tot_ms)

            # Tracked tallies
            veh_in_frame = 0
            for trk in trk_result.tracks:
                active_track_ids_seen.add(trk.track_id)
                if getattr(trk, "object_type", "person") == "vehicle":
                    veh_in_frame += 1
                    active_vehicle_track_ids_seen.add(trk.track_id)
                else:
                    active_person_track_ids_seen.add(trk.track_id)

            tracked_vehicle_counts_per_frame.append(veh_in_frame)

            # Visual verification snapshots
            if idx in save_frame_indices:
                annotated = overlay_renderer.render(
                    frame=frame,
                    tracks=trk_result.tracks,
                    fps=1000.0 / np.mean(total_frame_times_ms),
                    camera_id="CAM-01",
                )
                # Stamp config name on bottom left
                cv2.putText(
                    annotated,
                    f"{exp.name}: conf={exp.conf_threshold}, imgsz={exp.imgsz} | Frame {idx}",
                    (20, annotated.shape[0] - 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                save_path = os.path.join(output_dir, f"{exp.name}_frame_{idx:03d}.jpg")
                cv2.imwrite(save_path, annotated)

        mean_inf_ms = float(np.mean(inference_times_ms))
        mean_tot_ms = float(np.mean(total_frame_times_ms))
        pipeline_fps = 1000.0 / mean_tot_ms if mean_tot_ms > 0 else 0.0
        inf_fps = 1000.0 / mean_inf_ms if mean_inf_ms > 0 else 0.0

        avg_active_vehicles = float(np.mean(tracked_vehicle_counts_per_frame))

        res_dict = {
            "name": exp.name,
            "label": exp.label,
            "conf_threshold": exp.conf_threshold,
            "imgsz": exp.imgsz,
            "tracker_new_thresh": exp.tracker_new_thresh,
            "tracker_high_thresh": exp.tracker_high_thresh,
            "frames_processed": total_frames,
            "raw_person_detections": raw_person_count,
            "raw_car_detections": raw_car_count,
            "raw_motorcycle_detections": raw_motorcycle_count,
            "raw_bus_detections": raw_bus_count,
            "raw_truck_detections": raw_truck_count,
            "raw_total_vehicle_detections": raw_vehicle_count,
            "raw_detections_in_018_025_band": raw_dets_below_025,
            "distinct_vehicle_track_ids": len(active_vehicle_track_ids_seen),
            "distinct_person_track_ids": len(active_person_track_ids_seen),
            "distinct_total_track_ids": len(active_track_ids_seen),
            "avg_active_vehicles_per_frame": round(avg_active_vehicles, 2),
            "mean_inference_ms": round(mean_inf_ms, 1),
            "inference_fps": round(inf_fps, 1),
            "mean_total_frame_ms": round(mean_tot_ms, 1),
            "pipeline_fps": round(pipeline_fps, 1),
        }
        results[exp.name] = res_dict

        print(f"Results for {exp.name}:")
        print(f"  Raw Vehicle Detections: {raw_vehicle_count} (Car: {raw_car_count}, Moto: {raw_motorcycle_count}, Bus: {raw_bus_count}, Truck: {raw_truck_count})")
        print(f"  Raw Person Detections:  {raw_person_count}")
        print(f"  Detections in [0.18, 0.25) band: {raw_dets_below_025}")
        print(f"  Distinct Vehicle Track IDs: {len(active_vehicle_track_ids_seen)}")
        print(f"  Avg Active Vehicles/Frame:  {avg_active_vehicles:.2f}")
        print(f"  Inference FPS: {inf_fps:.1f} | Pipeline FPS: {pipeline_fps:.1f}")

    return results


if __name__ == "__main__":
    video_file = "data/sample_videos/15300538-hd_1920_1080_60fps.mp4"
    if not os.path.exists(video_file):
        cam = get_camera("CAM-01")
        if cam:
            video_file = cam.file_path

    # Define the configurations specified by the user
    configs = [
        ExpConfig(name="Config_A", label="Production Baseline (conf=0.25, imgsz=640)", conf_threshold=0.25, imgsz=640),
        ExpConfig(name="Config_B", label="Moderate Conf Lowering (conf=0.18, imgsz=640)", conf_threshold=0.18, imgsz=640),
        ExpConfig(name="Config_C", label="Higher Resolution (conf=0.25, imgsz=960)", conf_threshold=0.25, imgsz=960),
        ExpConfig(name="Config_D1", label="Moderate Conf + Mid Res (conf=0.18, imgsz=800)", conf_threshold=0.18, imgsz=800),
        ExpConfig(name="Config_D2", label="Moderate Conf + High Res (conf=0.18, imgsz=960)", conf_threshold=0.18, imgsz=960),
        # Condition E: Tracker Threshold Variant to address Adjustment #2
        ExpConfig(
            name="Config_E",
            label="Tracker Tuned (conf=0.18, imgsz=800, trk_new=0.18, trk_high=0.18)",
            conf_threshold=0.18,
            imgsz=800,
            tracker_new_thresh=0.18,
            tracker_high_thresh=0.18,
        ),
    ]

    out_json = "data/cam01_recall_experiment_results.json"
    print(f"Starting controlled evaluation across {len(configs)} configurations on {video_file}...")
    summary = run_experiment(video_file, configs, max_frames=150, save_frame_indices=[30, 75, 120])

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nAll experiments complete. Summary written to {out_json}.")
