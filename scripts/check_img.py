import json, subprocess, time, urllib.request
from websockets.sync.client import connect

edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
browser = subprocess.Popen([edge_exe, "--headless=new", "--remote-debugging-port=9227", "--disable-gpu", "about:blank"])
time.sleep(1.5)
try:
    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9227/json").read().decode())
    ws_url = [t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"][0]
    with connect(ws_url) as cdp:
        def cmd(req_id, method, params=None):
            payload = {"id": req_id, "method": method}
            if params: payload["params"] = params
            cdp.send(json.dumps(payload))
            while True:
                msg = json.loads(cdp.recv())
                if msg.get("id") == req_id: return msg

        cmd(1, "Page.enable")
        cmd(2, "Page.navigate", {"url": "http://127.0.0.1:5173"})
        time.sleep(3.5)
        res = cmd(3, "Runtime.evaluate", {
            "expression": "JSON.stringify({ src: document.querySelector('img.surveillance-video')?.src, complete: document.querySelector('img.surveillance-video')?.complete, naturalWidth: document.querySelector('img.surveillance-video')?.naturalWidth, naturalHeight: document.querySelector('img.surveillance-video')?.naturalHeight })",
            "returnByValue": True
        })
        print("IMG STATE:", res.get("result", {}).get("result", {}).get("value"))
finally:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(browser.pid)], capture_output=True)
