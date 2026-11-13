"""Mobile-emulation screenshot tool via Chrome DevTools Protocol.

Usage: python tools/devshots.py <url> <out.png> [width] [height] [wait_s] [js]
(optional js runs after load, e.g. to open a dialog before the shot)
Launches its own headless Chrome instance with a throwaway profile.
"""
import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333

url = sys.argv[1]
out = Path(sys.argv[2])
width = int(sys.argv[3]) if len(sys.argv) > 3 else 390
height = int(sys.argv[4]) if len(sys.argv) > 4 else 844
wait_s = float(sys.argv[5]) if len(sys.argv) > 5 else 9

profile = tempfile.mkdtemp(prefix="cdp_shots_")
proc = subprocess.Popen([
    CHROME, "--headless", "--disable-gpu", f"--user-data-dir={profile}",
    f"--remote-debugging-port={PORT}", "--no-first-run", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    # wait for the devtools endpoint
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    # create a fresh tab (PUT required on modern Chrome)
    r = httpx.put(f"http://127.0.0.1:{PORT}/json/new?about:blank", timeout=5)
    target = r.json()
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=60)
    next_id = [0]

    def cmd(method, params=None):
        next_id[0] += 1
        ws.send(json.dumps({"id": next_id[0], "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == next_id[0]:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    # true mobile device emulation (honors viewport meta, DPR 2 for crisp shots)
    cmd("Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": True})
    cmd("Page.enable")
    cmd("Page.navigate", {"url": url})
    time.sleep(wait_s)
    if len(sys.argv) > 6:
        cmd("Runtime.evaluate", {"expression": sys.argv[6]})
        time.sleep(0.8)
    shot = cmd("Page.captureScreenshot", {"format": "png"})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(shot["data"]))
    print(f"saved {out} ({width}x{height} css px)")
    ws.close()
finally:
    proc.kill()
