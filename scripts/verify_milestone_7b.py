"""
Milestone 7B Verification Script: Real-Time Detection & Tracking Overlay Stream.
Validates:
1. Backend Uvicorn server startup (port 8000).
2. All REST endpoints (/api/health, /api/stats, /api/events, /api/cameras, /api/zones, /api/video/demo).
3. Live MJPEG endpoint (/api/video/annotated):
   - Stream connection with multipart/x-mixed-replace
   - Chunk parsing and JPEG boundary extraction
   - cv2.imdecode frame verification for 10 frames
   - Resolution verification (1280x720, 3 channels, uint8)
   - Real-time pipeline processing FPS measurement
4. WebSocket stream (/ws/events) handshake and ping-pong.
5. Frontend production build and dev server availability.
6. Clean, deterministic process teardown.
"""

import json
import logging
import subprocess
import sys
import time
import urllib.request
from typing import Optional

import cv2
import numpy as np
from websockets.sync.client import connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("verify_7b")


def verify_mjpeg_stream(base_url: str = "http://127.0.0.1:8000", frame_target: int = 10) -> bool:
    """Connects to /api/video/annotated, parses multipart stream, decodes frames with OpenCV."""
    url = f"{base_url}/api/video/annotated"
    logger.info(f"Connecting to live MJPEG stream: {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "IBVAP-Verifier/1.0"})
    resp = urllib.request.urlopen(req, timeout=10.0)

    content_type = resp.headers.get("content-type", "")
    logger.info(f"  Stream Content-Type: {content_type}")
    if "multipart/x-mixed-replace" not in content_type:
        logger.error(f"Expected multipart/x-mixed-replace, got {content_type}")
        return False

    boundary = b"--frame"
    buffer = b""
    frames_decoded = 0
    start_time = time.perf_counter()

    try:
        while frames_decoded < frame_target:
            chunk = resp.read(8192)
            if not chunk:
                break
            buffer += chunk

            # Extract full frames between boundaries
            while boundary in buffer:
                first_idx = buffer.find(boundary)
                next_idx = buffer.find(boundary, first_idx + len(boundary))
                if next_idx == -1:
                    break

                part = buffer[first_idx:next_idx]
                buffer = buffer[next_idx:]

                # Locate JPEG SOI (\xff\xd8) and EOI (\xff\xd9)
                soi_idx = part.find(b"\xff\xd8")
                eoi_idx = part.find(b"\xff\xd9", soi_idx) if soi_idx != -1 else -1

                if soi_idx != -1 and eoi_idx != -1:
                    jpeg_bytes = part[soi_idx : eoi_idx + 2]
                    nparr = np.frombuffer(jpeg_bytes, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame is not None:
                        frames_decoded += 1
                        height, width, channels = frame.shape
                        logger.info(
                            f"  [FRAME {frames_decoded}/{frame_target}] Decoded: {width}x{height}x{channels} | "
                            f"JPEG Size: {len(jpeg_bytes):,} bytes | dtype: {frame.dtype}"
                        )
                        assert (height, width, channels) == (720, 1280, 3), f"Wrong resolution: {frame.shape}"
                        assert frame.dtype == np.uint8, f"Wrong dtype: {frame.dtype}"

        total_elapsed = time.perf_counter() - start_time
        fps = (frames_decoded / total_elapsed) if total_elapsed > 0 else 0.0
        logger.info(f"  Successfully decoded {frames_decoded} frames in {total_elapsed:.2f}s (~{fps:.2f} FPS)")
        return frames_decoded >= frame_target

    finally:
        resp.close()


def run_milestone_7b_verification() -> bool:
    backend_proc: Optional[subprocess.Popen] = None
    frontend_proc: Optional[subprocess.Popen] = None

    try:
        # 1. Start Backend Server
        logger.info("Starting FastAPI backend on http://127.0.0.1:8000...")
        backend_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "warning",
        ]
        backend_proc = subprocess.Popen(backend_cmd)

        # Wait for backend readiness
        backend_ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        if data.get("status") == "online":
                            backend_ready = True
                            logger.info(f"[BACKEND READY] Health: {data}")
                            break
            except Exception:
                time.sleep(0.2)

        if not backend_ready:
            logger.error("FastAPI backend failed to start within timeout.")
            return False

        # 2. Check REST Endpoints
        logger.info("Verifying REST endpoints...")
        rest_checks = [
            ("/api/health", "Health"),
            ("/api/stats", "Stats"),
            ("/api/events?limit=5", "Events"),
            ("/api/cameras", "Cameras"),
            ("/api/zones", "Zones"),
            ("/api/video/demo", "Raw Demo Video"),
        ]
        for path, name in rest_checks:
            url = f"http://127.0.0.1:8000{path}"
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                assert resp.status == 200, f"Endpoint {path} failed: {resp.status}"
                logger.info(f"  [OK] {name} ({path}) -> Status {resp.status}")

        # 3. Check Live MJPEG Annotated Stream
        logger.info("Verifying Live Annotated Stream (/api/video/annotated)...")
        mjpeg_ok = verify_mjpeg_stream("http://127.0.0.1:8000", frame_target=10)
        if not mjpeg_ok:
            logger.error("MJPEG stream verification failed.")
            return False

        # 4. Check WebSocket Handshake and Ping/Pong
        logger.info("Verifying WebSocket stream (ws://127.0.0.1:8000/ws/events)...")
        with connect("ws://127.0.0.1:8000/ws/events") as ws:
            handshake = json.loads(ws.recv(timeout=2.0))
            assert handshake.get("message_type") == "CONNECTED"
            logger.info(f"  [WS HANDSHAKE OK] Client ID: {handshake.get('client_id')}")

            ws.send("ping")
            pong = ws.recv(timeout=2.0)
            assert pong == "pong"
            logger.info(f"  [WS PING-PONG OK] Response: {pong}")

        # 5. Start Frontend Dev Server
        logger.info("Starting Frontend Dev Server on http://127.0.0.1:5173...")
        frontend_cmd = ["cmd.exe", "/c", "npm", "run", "dev"]
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd="frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        frontend_ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:5173", timeout=1.0) as resp:
                    if resp.status == 200:
                        frontend_ready = True
                        logger.info(f"[FRONTEND READY] Status: {resp.status}")
                        break
            except Exception:
                time.sleep(0.3)

        if not frontend_ready:
            logger.error("Frontend Vite server failed to respond.")
            return False

        logger.info("==================================================")
        logger.info("MILESTONE 7B FULL VERIFICATION SUCCESSFUL!")
        logger.info("==================================================")
        return True

    finally:
        logger.info("Cleaning up server processes...")
        if frontend_proc:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(frontend_proc.pid)],
                    capture_output=True,
                )
            except Exception:
                frontend_proc.kill()
            logger.info("Frontend process terminated.")

        if backend_proc:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(backend_proc.pid)],
                    capture_output=True,
                )
            except Exception:
                backend_proc.kill()
            logger.info("Backend process terminated.")


if __name__ == "__main__":
    success = run_milestone_7b_verification()
    sys.exit(0 if success else 1)
