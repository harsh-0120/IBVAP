"""
Validation Script: Real-World Moving Vehicle CCTV Validation (Milestone 8)
Processes bounded segments (200 frames) of the 3 newly provided videos through the
full existing Milestone 8 pipeline without architectural changes.
"""

import os
import sys
import time
import json
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np

# Ensure workspace root is in python path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.detector import YOLODetector, DetectorConfig, ALL_SURVEILLANCE_CLASS_IDS
from core.tracker import ByteTrackTracker, TrackerConfig
from core.spatial_engine import SpatialEngine, SpatialConfig
from core.incident_manager import IncidentManager, IncidentConfig
from core.overlay_renderer import OverlayRenderer, OverlayConfig

def inspect_video_properties(video_path: str):
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    dur = frames / fps if fps > 0 else 0
    return {
        "path": video_path,
        "width": w,
        "height": h,
        "resolution": f"{w}x{h}",
        "aspect": "landscape (16:9)" if w > h else "portrait (9:16)",
        "fps": round(fps, 2),
        "total_frames": frames,
        "duration_sec": round(dur, 2),
    }

def validate_video(
    video_path: str,
    video_index: int,
    max_frames: int = 200,
    db_path: str = "data/validation_events.db",
    snapshot_dir: str = "data/validation_snapshots",
):
    print(f"\n==================================================")
    print(f"STARTING VALIDATION ON VIDEO {video_index}: {video_path}")
    print(f"==================================================")

    # 1. Pipeline initialization with existing default configs
    det_cfg = DetectorConfig.from_yaml("config/default_config.yaml")
    trk_cfg = TrackerConfig.from_yaml("config/default_config.yaml")
    spat_cfg = SpatialConfig.from_yaml("config/default_config.yaml")
    over_cfg = OverlayConfig.from_yaml("config/default_config.yaml")

    detector = YOLODetector(config=det_cfg, target_classes=ALL_SURVEILLANCE_CLASS_IDS)
    tracker = ByteTrackTracker(config=trk_cfg)
    spatial_engine = SpatialEngine(config=spat_cfg)
    
    inc_cfg = IncidentConfig(
        camera_id=f"CCTV-TEST-{video_index:02d}",
        db_path=db_path,
        snapshot_dir=snapshot_dir,
        jpeg_quality=90,
    )
    incident_mgr = IncidentManager(config=inc_cfg)
    overlay_renderer = OverlayRenderer(config=over_cfg)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Output video writer (scaled to 1280x720 for fast playback and reasonable size)
    out_video_path = f"data/sample_videos/annotated_output_vid{video_index}.mp4"
    out_w, out_h = 1280, 720
    if w < h: # Portrait orientation
        out_w, out_h = 720, 1280
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_video_path, fourcc, min(30.0, src_fps), (out_w, out_h))

    # Metric accumulators
    frame_count = 0
    total_det_time = 0.0
    total_trk_time = 0.0
    total_pipeline_time = 0.0

    person_detections = 0
    vehicle_detections = 0
    vehicle_class_counts = defaultdict(int)

    # Tracking metrics
    vehicle_track_lifespans = defaultdict(int)
    vehicle_track_classes = {}
    vehicle_track_trajectories = defaultdict(list)
    active_vehicles_per_frame = []
    
    # ID switch and stability analysis
    # Store position of tracks per frame
    frame_track_map = {} # frame_idx -> {track_id: (bbox, class_name)}

    # Incidents
    generated_incidents = []
    
    # Representative snapshots to save
    saved_snapshot_frames = []

    t_start_total = time.perf_counter()

    while frame_count < max_frames:
        t_frame_start = time.perf_counter()
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        current_frame_idx = frame_count
        current_ts = current_frame_idx / src_fps

        # 1. YOLO11n Single-Pass Detection
        t0 = time.perf_counter()
        det_result = detector.detect(frame, frame_index=current_frame_idx)
        t_det = time.perf_counter() - t0
        total_det_time += t_det

        person_detections += det_result.person_count
        vehicle_detections += det_result.vehicle_count
        for cname, cnt in det_result.vehicle_counts_by_class.items():
            vehicle_class_counts[cname] += cnt

        # 2. ByteTrack Tracking
        t1 = time.perf_counter()
        trk_result = tracker.update(det_result, frame_index=current_frame_idx, timestamp=current_ts)
        t_trk = time.perf_counter() - t1
        total_trk_time += t_trk

        active_vehicles = [t for t in trk_result.tracks if getattr(t, "object_type", "person") == "vehicle"]
        active_vehicles_per_frame.append(len(active_vehicles))

        frame_track_map[current_frame_idx] = {}
        for t in active_vehicles:
            vehicle_track_lifespans[t.track_id] += 1
            vehicle_track_classes[t.track_id] = t.class_name
            vehicle_track_trajectories[t.track_id].append(t.feet_point)
            frame_track_map[current_frame_idx][t.track_id] = (t.bbox, t.class_name)

        # 3. Spatial Analytics
        events, active_states = spatial_engine.process_tracks(
            tracks=trk_result.tracks,
            frame_index=current_frame_idx,
            timestamp=current_ts,
        )

        # 4. Incident Management
        for event in events:
            assoc_track = next((t for t in trk_result.tracks if t.track_id == event.track_id), None)
            inc_record = incident_mgr.process_event(event=event, frame=frame, track=assoc_track)
            generated_incidents.append(inc_record)
            print(f"  [ALERT] Frame {current_frame_idx}: {event.event_type.value} by {inc_record.object_type.upper()} #{event.track_id} in {event.zone_name}")

        # 5. Tactical Overlay Rendering
        current_fps = 1.0 / (time.perf_counter() - t_frame_start) if (time.perf_counter() - t_frame_start) > 0 else 0.0
        annotated_frame = overlay_renderer.render(
            frame=frame,
            tracks=trk_result.tracks,
            fps=current_fps,
            camera_id=inc_cfg.camera_id,
        )

        # Write to video
        resized_annotated = cv2.resize(annotated_frame, (out_w, out_h))
        writer.write(resized_annotated)

        # Save representative snapshots at frame 50, 100, 150
        if current_frame_idx in [50, 100, 150] or (current_frame_idx == 30 and len(saved_snapshot_frames) == 0):
            snap_path = f"data/sample_videos/validation_snapshot_vid{video_index}_f{current_frame_idx}.jpg"
            cv2.imwrite(snap_path, annotated_frame)
            saved_snapshot_frames.append(snap_path)

        frame_count += 1
        total_pipeline_time += (time.perf_counter() - t_frame_start)

    cap.release()
    writer.release()
    total_elapsed = time.perf_counter() - t_start_total

    # Post-analysis of tracking stability
    distinct_vehicle_ids = len(vehicle_track_lifespans)
    stable_tracks_15f = sum(1 for dur in vehicle_track_lifespans.values() if dur >= 15)
    stable_tracks_30f = sum(1 for dur in vehicle_track_lifespans.values() if dur >= 30)
    longest_duration_frames = max(vehicle_track_lifespans.values()) if vehicle_track_lifespans else 0
    longest_duration_sec = longest_duration_frames / src_fps if src_fps > 0 else 0.0

    # Calculate average track displacement (moving verification)
    moving_tracks_count = 0
    stationary_tracks_count = 0
    for tid, traj in vehicle_track_trajectories.items():
        if len(traj) >= 5:
            # Distance between first and last point
            p_first = np.array(traj[0])
            p_last = np.array(traj[-1])
            disp = np.linalg.norm(p_last - p_first)
            if disp > 30.0:  # Moved more than 30 pixels
                moving_tracks_count += 1
            else:
                stationary_tracks_count += 1

    # Analysis of ID fragmentation:
    # Check if multiple tracks appeared in very close spatial proximity immediately after one vanished
    avg_active_tracks = sum(active_vehicles_per_frame) / len(active_vehicles_per_frame) if active_vehicles_per_frame else 0.0

    report = {
        "video_index": video_index,
        "video_path": video_path,
        "resolution": f"{w}x{h}",
        "src_fps": round(src_fps, 2),
        "frames_processed": frame_count,
        "elapsed_seconds": round(total_elapsed, 2),
        "effective_fps": round(frame_count / total_elapsed, 2) if total_elapsed > 0 else 0.0,
        "avg_detection_time_ms": round((total_det_time / frame_count) * 1000.0, 2) if frame_count else 0,
        "avg_tracking_time_ms": round((total_trk_time / frame_count) * 1000.0, 2) if frame_count else 0,
        "person_detections": person_detections,
        "total_vehicle_detections": vehicle_detections,
        "car_detections": vehicle_class_counts["car"],
        "motorcycle_detections": vehicle_class_counts["motorcycle"],
        "bus_detections": vehicle_class_counts["bus"],
        "truck_detections": vehicle_class_counts["truck"],
        "distinct_vehicle_ids": distinct_vehicle_ids,
        "avg_active_vehicles_per_frame": round(avg_active_tracks, 2),
        "longest_vehicle_track_frames": longest_duration_frames,
        "longest_vehicle_track_sec": round(longest_duration_sec, 2),
        "stable_tracks_ge_15_frames": stable_tracks_15f,
        "stable_tracks_ge_30_frames": stable_tracks_30f,
        "moving_vehicle_tracks": moving_tracks_count,
        "stationary_vehicle_tracks": stationary_tracks_count,
        "annotated_video_output": out_video_path,
        "snapshots_saved": saved_snapshot_frames,
        "incidents_count": len(generated_incidents),
        "incidents": [
            {
                "id": inc.id,
                "event_type": inc.event_type,
                "track_id": inc.track_id,
                "object_type": inc.object_type,
                "zone_name": inc.zone_name,
                "confidence": inc.confidence,
                "snapshot_path": inc.snapshot_path,
            }
            for inc in generated_incidents[:5]
        ],
    }

    print(f"COMPLETED VIDEO {video_index} IN {total_elapsed:.2f}s ({frame_count / total_elapsed:.2f} FPS)")
    print(f"Vehicle Detections: {vehicle_detections} | Distinct IDs: {distinct_vehicle_ids}")
    print(f"Breakdown: Car={vehicle_class_counts['car']}, Moto={vehicle_class_counts['motorcycle']}, Bus={vehicle_class_counts['bus']}, Truck={vehicle_class_counts['truck']}")
    return report

def main():
    videos = [
        "data/sample_videos/15300538-hd_1920_1080_60fps.mp4",
        "data/sample_videos/13650838_3840_2160_30fps.mp4",
        "data/sample_videos/12205172_2160_3840_60fps.mp4",
    ]

    # Clean old validation db if exists
    db_file = Path("data/validation_events.db")
    if db_file.exists():
        try:
            os.remove(db_file)
        except Exception:
            pass

    Path("data/validation_snapshots").mkdir(parents=True, exist_ok=True)

    all_reports = []
    for idx, v in enumerate(videos, 1):
        info = inspect_video_properties(v)
        report = validate_video(
            video_path=v,
            video_index=idx,
            max_frames=200,
            db_path="data/validation_events.db",
            snapshot_dir="data/validation_snapshots",
        )
        report["properties"] = info
        all_reports.append(report)

    with open("data/sample_videos/validation_report.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)

    print("\n==================================================")
    print("ALL 3 VIDEOS VALIDATED. SUMMARY SAVED TO data/sample_videos/validation_report.json")
    print("==================================================")

if __name__ == "__main__":
    main()
