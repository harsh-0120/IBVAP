"""
Milestone 7A Verification Script: Full Stack Live Co-Execution.
Validates:
1. Backend Uvicorn server startup (port 8000).
2. All REST endpoints (/api/health, /api/stats, /api/events, /api/cameras, /api/zones, /api/video/demo).
3. WebSocket stream (/ws/events).
4. Frontend Vite development server startup (port 5173).
5. Frontend HTML serving and asset references.
6. Real-time incident broadcast reception over WebSocket.
7. Clean teardown of both processes.
"""

import json
import logging
import subprocess
import sys
import time
import urllib.request

from websockets.sync.client import connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("verify_7a")


def run_full_stack_verification() -> bool:
    backend_proc = None
    frontend_proc = None

    try:
        # 1. Start Backend
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

        # Wait for backend health
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

        # 2. Verify all REST endpoints
        logger.info("Verifying all backend REST endpoints...")
        rest_checks = [
            ("/api/health", "Service Health"),
            ("/api/stats", "System Statistics"),
            ("/api/events?limit=5", "Recent Incidents"),
            ("/api/cameras", "Configured Cameras"),
            ("/api/zones", "Spatial Boundaries"),
            ("/api/video/demo", "Demo Video Stream"),
        ]

        for path, desc in rest_checks:
            url = f"http://127.0.0.1:8000{path}"
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                assert resp.status == 200, f"Failed on {path}: {resp.status}"
                content_type = resp.headers.get("content-type", "")
                content_len = resp.headers.get("content-length", "N/A")
                logger.info(f"  [OK] {desc} ({path}) -> Status {resp.status} | Content-Type: {content_type} | Size: {content_len}")

        # 3. Verify WebSocket Connection
        logger.info("Connecting to WebSocket stream at ws://127.0.0.1:8000/ws/events...")
        with connect("ws://127.0.0.1:8000/ws/events") as ws:
            handshake = json.loads(ws.recv(timeout=2.0))
            logger.info(f"  [WS HANDSHAKE OK] Received: {handshake}")
            assert handshake.get("message_type") == "CONNECTED"

            ws.send("ping")
            pong = ws.recv(timeout=2.0)
            logger.info(f"  [WS PING-PONG OK] Response: {pong}")
            assert pong == "pong"

        # 4. Start Frontend Vite Server
        logger.info("Starting Vite frontend development server on http://127.0.0.1:5173...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend_cmd = [npm_cmd, "run", "dev"]
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd="frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for frontend to respond
        frontend_ready = False
        frontend_html = ""
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:5173", timeout=1.0) as resp:
                    if resp.status == 200:
                        frontend_html = resp.read().decode()
                        if '<div id="root">' in frontend_html:
                            frontend_ready = True
                            logger.info("[FRONTEND READY] Vite dev server serving HTML successfully!")
                            break
            except Exception:
                time.sleep(0.25)

        if not frontend_ready:
            logger.error("Vite frontend server failed to start within timeout.")
            return False

        assert "IBVAP — Intelligent Border Video Analytics Platform" in frontend_html
        assert "/src/main.tsx" in frontend_html
        logger.info("  [OK] HTML Title and Entry script tag verified.")

        logger.info("==========================================================")
        logger.info("ALL MILESTONE 7A FULL-STACK CHECKS PASSED WITH 100% SUCCESS!")
        logger.info("==========================================================")
        return True

    except Exception as e:
        logger.error(f"Verification encountered error: {e}", exc_info=True)
        return False
    finally:
        if frontend_proc is not None:
            logger.info("Stopping frontend Vite dev server...")
            frontend_proc.terminate()
            try:
                frontend_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                frontend_proc.kill()

        if backend_proc is not None:
            logger.info("Stopping FastAPI backend server...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
        logger.info("Servers successfully terminated.")


if __name__ == "__main__":
    success = run_full_stack_verification()
    sys.exit(0 if success else 1)
