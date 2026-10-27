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

viewports = [320, 360, 375, 390, 430, 768, 1024, 1280, 1440]
results = {}

for w in viewports:
    cdp_send("Emulation.setDeviceMetricsOverride", {
        "width": w,
        "height": 800,
        "deviceScaleFactor": 1,
        "mobile": (w < 1024)
    })
    time.sleep(0.5)

    check_js = f"""
    (() => {{
        const winW = {w};
        const docScrollW = document.documentElement.scrollWidth;
        const bodyScrollW = document.body.scrollWidth;
        const badElements = [];
        document.querySelectorAll('*').forEach(el => {{
            const rect = el.getBoundingClientRect();
            if (rect.right > winW + 1) {{
                badElements.push({{
                    tag: el.tagName,
                    cls: el.className,
                    id: el.id,
                    right: Math.round(rect.right),
                    width: Math.round(rect.width),
                    snippet: el.outerHTML.substring(0, 70).replace(/\\n/g, ' ')
                }});
            }}
        }});
        return {{
            viewport: winW,
            docScrollW,
            bodyScrollW,
            overflows: docScrollW > winW,
            badCount: badElements.length,
            badElements: badElements.slice(0, 10)
        }};
    }})()
    """
    res = cdp_send("Runtime.evaluate", {"expression": check_js, "returnByValue": True})
    results[w] = res.get("result", {}).get("value", {})

print(json.dumps(results, indent=2))
ws.close()
proc.terminate()
