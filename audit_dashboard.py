import subprocess
import time
import requests
import json
import base64
import websocket

proc = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new",
    "--remote-debugging-port=9222",
    "--remote-allow-origins=*",
    "--user-data-dir=C:\\Users\\Sam\\AppData\\Local\\Temp\\chrome_cdp_admin",
    "--no-first-run",
    "--disable-gpu",
    "http://127.0.0.1:5000/login"
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

# 1. Login as admin
login_js = """
(() => {
    const email = document.querySelector('input[name="email"]') || document.querySelector('input[type="email"]') || document.querySelector('input[name="username"]');
    const pwd = document.querySelector('input[name="password"]');
    const form = document.querySelector('form');
    if (email && pwd && form) {
        email.value = 'admin@amrita.com';
        pwd.value = 'Amrita28';
        form.submit();
        return true;
    }
    return false;
})()
"""
res = cdp_send("Runtime.evaluate", {"expression": login_js, "returnByValue": True})
print("Login form submitted:", res)
time.sleep(2)

# Check current URL
url_res = cdp_send("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
print("Current URL after login:", url_res)

# Test dashboard at 390px
cdp_send("Emulation.setDeviceMetricsOverride", {
    "width": 390,
    "height": 844,
    "deviceScaleFactor": 2,
    "mobile": True
})
time.sleep(1)

# Check scrollWidth and element sizes on dashboard
dash_check_js = """
(() => {
    const docW = document.documentElement.offsetWidth;
    const scrollW = document.documentElement.scrollWidth;
    const bodyScrollW = document.body.scrollWidth;
    const winW = window.innerWidth;
    
    const wideElements = [];
    document.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.right > winW + 1) {
            wideElements.push({
                tag: el.tagName,
                cls: el.className,
                id: el.id,
                right: Math.round(r.right),
                width: Math.round(r.width),
                snippet: el.outerHTML.substring(0, 80).replace(/\\n/g, ' ')
            });
        }
    });

    return {
        url: window.location.href,
        docW,
        scrollW,
        bodyScrollW,
        winW,
        overflowing: scrollW > winW,
        wideCount: wideElements.length,
        wideElements: wideElements.slice(0, 15)
    };
})()
"""
dash_eval = cdp_send("Runtime.evaluate", {"expression": dash_check_js, "returnByValue": True})
print("DASHBOARD AUDIT AT 390px:")
print(json.dumps(dash_eval.get("result", {}).get("value", {}), indent=2))

# Take screenshot of dashboard
snap = cdp_send("Page.captureScreenshot", {"format": "png"})
if "data" in snap:
    with open(r"C:\Users\Sam\.gemini\antigravity-ide\brain\cd568210-fb52-4b98-b45b-bad2a032451c\dashboard_390_initial.png", "wb") as f:
        f.write(base64.b64decode(snap["data"]))
    print("Saved dashboard_390_initial.png!")

ws.close()
proc.terminate()
