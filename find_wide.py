import subprocess
import time
import requests
import json
import websocket

proc = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new",
    "--remote-debugging-port=9222",
    "--remote-allow-origins=*",
    "--user-data-dir=C:\\Users\\Sam\\AppData\\Local\\Temp\\chrome_cdp",
    "--no-first-run",
    "--disable-gpu",
    "http://127.0.0.1:5000/"
])
time.sleep(2)

tabs = requests.get("http://localhost:9222/json").json()
target_tab = [t for t in tabs if t.get("type") == "page"][0]
ws = websocket.create_connection(target_tab["webSocketDebuggerUrl"])

def cdp_send(method, params=None, msg_id=[1]):
    mid = msg_id[0]
    msg_id[0] += 1
    payload = {"id": mid, "method": method}
    if params:
        payload["params"] = params
    ws.send(json.dumps(payload))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == mid:
            return resp.get("result", {})

cdp_send("Emulation.setDeviceMetricsOverride", {
    "width": 390,
    "height": 844,
    "deviceScaleFactor": 2,
    "mobile": True
})

js = """
(() => {
    const wide = [];
    document.querySelectorAll('*').forEach(el => {
        if (el.scrollWidth > 390) {
            wide.push({
                tag: el.tagName,
                className: el.className,
                id: el.id,
                scrollWidth: el.scrollWidth,
                offsetWidth: el.offsetWidth,
                clientWidth: el.clientWidth,
                snippet: el.outerHTML.substring(0, 80)
            });
        }
    });
    return wide;
})()
"""

res = cdp_send("Runtime.evaluate", {"expression": js, "returnByValue": True})
print(json.dumps(res.get("result", {}).get("value", []), indent=2))
ws.close()
proc.terminate()
