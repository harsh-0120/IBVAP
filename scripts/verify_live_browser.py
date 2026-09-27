"""
Bounded Headless Browser Verification for Live AI Surveillance Dashboard.
Strictly bounded execution using Chrome/Edge DevTools Protocol (CDP).
Properly handles asynchronous CDP events by matching request IDs.
"""

import base64
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from websockets.sync.client import connect

SCREENSHOT_PATH = Path("data/live_ai_surveillance_dashboard.png").resolve()


def send_cdp(cdp, req_id, method, params=None):
    payload = {"id": req_id, "method": method}
    if params:
        payload["params"] = params
    cdp.send(json.dumps(payload))
    while True:
        msg = json.loads(cdp.recv())
        if msg.get("id") == req_id:
            return msg


def run_browser_verification():
    print("==================================================")
    print("STARTING BOUNDED LIVE BROWSER VERIFICATION")
    print("==================================================")

    edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    browser = subprocess.Popen([
        edge_exe,
        "--headless=new",
        "--remote-debugging-port=9225",
        "--disable-gpu",
        "about:blank",
    ])
    time.sleep(1.5)

    try:
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9225/json", timeout=3).read().decode())
        ws_url = [t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"][0]

        with connect(ws_url) as cdp:
            send_cdp(cdp, 1, "Runtime.enable")
            send_cdp(cdp, 2, "Page.enable")

            # Viewport 1920x1080
            send_cdp(cdp, 3, "Emulation.setDeviceMetricsOverride", {
                "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False
            })

            # Navigate to Dashboard
            print("1. Navigating to http://127.0.0.1:5173...")
            send_cdp(cdp, 4, "Page.navigate", {"url": "http://127.0.0.1:5173"})

            # Wait for React mount and data load
            time.sleep(3.5)

            # Query StatCards count
            res5 = send_cdp(cdp, 5, "Runtime.evaluate", {
                "expression": "document.querySelectorAll('.stat-card').length",
                "returnByValue": True,
            })
            stat_cards_count = res5.get("result", {}).get("result", {}).get("value", 0)
            print(f"2. Rendered StatCards: {stat_cards_count} (Expected: 5)")
            assert stat_cards_count == 5, f"Expected 5 stat cards, got {stat_cards_count}"

            # Query Camera selection tabs
            res6 = send_cdp(cdp, 6, "Runtime.evaluate", {
                "expression": "Array.from(document.querySelectorAll('[role=tab]')).map(b => b.innerText.trim())",
                "returnByValue": True,
            })
            tabs_text = res6.get("result", {}).get("result", {}).get("value", [])
            print(f"3. Camera Tabs Rendered: {tabs_text}")
            assert any("CAM-01" in t for t in tabs_text), "CAM-01 tab missing"
            assert any("CAM-02" in t for t in tabs_text), "CAM-02 tab missing"
            assert any("CAM-03" in t for t in tabs_text), "CAM-03 tab missing"

            # Query active stream img
            res7 = send_cdp(cdp, 7, "Runtime.evaluate", {
                "expression": "document.querySelector('img.surveillance-video')?.src || ''",
                "returnByValue": True,
            })
            img_src = res7.get("result", {}).get("result", {}).get("value", "")
            print(f"4. Active Live Stream Source: {img_src}")
            assert "/api/video/live/CAM-01" in img_src, f"Expected CAM-01 live stream, got {img_src}"

            # Click CAM-02 tab
            print("5. Clicking CAM-02 tab in browser...")
            res8 = send_cdp(cdp, 8, "Runtime.evaluate", {
                "expression": "(()=>{ const btns = Array.from(document.querySelectorAll('[role=tab]')); const b = btns.find(x => x.innerText.includes('CAM-02')); if (b) { b.click(); return true; } return false; })()",
                "returnByValue": True,
            })
            clicked = res8.get("result", {}).get("result", {}).get("value", False)
            print(f"  Clicked CAM-02 button: {clicked}")
            assert clicked, "Failed to click CAM-02 tab"

            # Wait for stream switch
            time.sleep(2.0)

            # Check switched stream img
            res9 = send_cdp(cdp, 9, "Runtime.evaluate", {
                "expression": "document.querySelector('img.surveillance-video')?.src || ''",
                "returnByValue": True,
            })
            switched_img_src = res9.get("result", {}).get("result", {}).get("value", "")
            print(f"6. Switched Live Stream Source: {switched_img_src}")
            assert "/api/video/live/CAM-02" in switched_img_src, f"Expected CAM-02 stream, got {switched_img_src}"

            # Capture high-resolution screenshot
            print(f"7. Capturing dashboard screenshot to {SCREENSHOT_PATH}...")
            res10 = send_cdp(cdp, 10, "Page.captureScreenshot", {"format": "png"})
            img_bytes = base64.b64decode(res10["result"]["data"])
            SCREENSHOT_PATH.write_bytes(img_bytes)
            print(f"  Saved screenshot: {len(img_bytes):,} bytes ({SCREENSHOT_PATH})")

            # Check for console errors
            res11 = send_cdp(cdp, 11, "Runtime.evaluate", {
                "expression": "window.__errors || []",
                "returnByValue": True,
            })
            errors = res11.get("result", {}).get("result", {}).get("value", [])
            print(f"8. Browser Console Errors: {len(errors)} errors")

        print("\n==================================================")
        print("BOUNDED BROWSER VERIFICATION COMPLETED SUCCESSFULLY!")
        print("==================================================")

    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(browser.pid)], capture_output=True)


if __name__ == "__main__":
    run_browser_verification()
