import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from websockets.sync.client import connect

out_file = Path("frontend/dashboard_1920x1080.png").resolve()

# 1. Start Frontend Dev Server
print("Starting Vite frontend dev server...", flush=True)
npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
f_proc = subprocess.Popen([npm_cmd, "run", "dev"], cwd="frontend")
for _ in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:5173", timeout=1) as r:
            if r.status == 200:
                print("Frontend online at http://127.0.0.1:5173", flush=True)
                break
    except Exception:
        time.sleep(0.2)

# 2. Start Headless Edge
print("Launching Edge headless browser...", flush=True)
edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
browser = subprocess.Popen([edge_exe, "--headless=new", "--remote-debugging-port=9222", "about:blank"])
time.sleep(1.5)

try:
    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read().decode())
    ws_url = [t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"][0]

    with connect(ws_url) as cdp:
        # Set 1080p resolution
        cdp.send(json.dumps({
            "id": 1,
            "method": "Emulation.setDeviceMetricsOverride",
            "params": {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False}
        }))
        while True:
            r = json.loads(cdp.recv())
            if r.get("id") == 1:
                break

        # Navigate to dashboard
        cdp.send(json.dumps({"id": 2, "method": "Page.navigate", "params": {"url": "http://127.0.0.1:5173"}}))
        while True:
            r = json.loads(cdp.recv())
            if r.get("id") == 2:
                break

        # Wait for React mount
        time.sleep(2.5)

        # Query rendered stat cards
        cdp.send(json.dumps({
            "id": 3,
            "method": "Runtime.evaluate",
            "params": {"expression": "document.querySelectorAll('.stat-card').length", "returnByValue": True}
        }))
        while True:
            r = json.loads(cdp.recv())
            if r.get("id") == 3:
                cards = r.get("result", {}).get("result", {}).get("value", 0)
                print(f"Rendered stat cards: {cards}", flush=True)
                break

        # Capture 1920x1080 screenshot
        print("Capturing 1920x1080 dashboard screenshot...", flush=True)
        cdp.send(json.dumps({"id": 4, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            r = json.loads(cdp.recv())
            if r.get("id") == 4:
                data = base64.b64decode(r["result"]["data"])
                out_file.write_bytes(data)
                print(f"SUCCESS: Saved 1920x1080 screenshot to {out_file} ({len(data):,} bytes)", flush=True)
                break

finally:
    print("Cleaning up processes...", flush=True)
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(browser.pid)], capture_output=True)
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(f_proc.pid)], capture_output=True)
    print("Cleaned up.", flush=True)
