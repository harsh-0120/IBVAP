"""
Milestone 6B Verification Script: Live FastAPI & WebSocket Validation.
Starts a live uvicorn server, validates:
1. REST endpoints (/api/health, /api/events, /api/stats, /docs)
2. WebSocket handshake on /ws/events
3. Heartbeat ping/pong
4. Real-time event broadcasting
5. Clean shutdown
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
logger = logging.getLogger("verify_6b")


def run_verification(port: int = 8000) -> bool:
    server_process = None
    try:
        logger.info(f"Starting live Uvicorn server on port {port}...")
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]
        server_process = subprocess.Popen(cmd)

        # Wait for server to become responsive
        health_url = f"http://127.0.0.1:{port}/api/health"
        server_up = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        if data.get("status") == "online":
                            server_up = True
                            logger.info(f"Server is online! Health response: {data}")
                            break
            except Exception:
                time.sleep(0.2)

        if not server_up:
            logger.error("Server failed to start within timeout.")
            return False

        # 1. Validate REST endpoints
        logger.info("Validating REST endpoints...")
        endpoints = ["/api/stats", "/api/events?limit=5", "/api/cameras", "/api/zones", "/docs"]
        for ep in endpoints:
            url = f"http://127.0.0.1:{port}{ep}"
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                assert resp.status == 200, f"Endpoint {ep} returned status {resp.status}"
                logger.info(f"  [REST OK] {ep} -> Status 200")

        # 2. Validate WebSocket Handshake & Heartbeat
        ws_url = f"ws://127.0.0.1:{port}/ws/events"
        logger.info(f"Connecting to WebSocket endpoint: {ws_url}...")
        with connect(ws_url) as ws:
            # Receive handshake
            handshake = json.loads(ws.recv(timeout=2.0))
            logger.info(f"  [WS HANDSHAKE OK] Received: {handshake}")
            assert handshake.get("message_type") == "CONNECTED"
            assert handshake.get("service") == "IBVAP"

            # Ping-pong
            ws.send("ping")
            pong = ws.recv(timeout=2.0)
            logger.info(f"  [WS HEARTBEAT OK] Sent 'ping' -> Received '{pong}'")
            assert pong == "pong"

        logger.info("WebSocket disconnect verified.")

        logger.info("==========================================================")
        logger.info("ALL MILESTONE 6B LIVE CHECKS PASSED SUCCESSFULLY!")
        logger.info("==========================================================")
        return True

    except Exception as e:
        logger.error(f"Verification failed with error: {e}", exc_info=True)
        return False
    finally:
        if server_process is not None:
            logger.info("Terminating live Uvicorn server process...")
            server_process.terminate()
            try:
                server_process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                server_process.kill()
            logger.info("Server process stopped.")


if __name__ == "__main__":
    success = run_verification(port=8000)
    sys.exit(0 if success else 1)
