import subprocess
import time
import requests
import json
import base64
import websocket

def run_test():
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

    try:
        time.sleep(2)
        tabs = requests.get("http://localhost:9222/json").json()
        target_tab = None
        for t in tabs:
            if t.get("type") == "page":
                target_tab = t
                break
        
        if not target_tab:
            print("No page tab found!")
            return

        ws_url = target_tab["webSocketDebuggerUrl"]
        ws = websocket.create_connection(ws_url)

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

        # Test at 390px
        print("Setting viewport to 390x844...")
        cdp_send("Emulation.setDeviceMetricsOverride", {
            "width": 390,
            "height": 844,
            "deviceScaleFactor": 2,
            "mobile": True
        })
        time.sleep(1)

        # Check scrollWidth and overflowing elements
        overflow_js = """
        (() => {
            const docWidth = document.documentElement.offsetWidth;
            const scrollWidth = document.documentElement.scrollWidth;
            const bodyScrollWidth = document.body.scrollWidth;
            const windowInnerWidth = window.innerWidth;
            
            const overflowing = [];
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const rect = el.getBoundingClientRect();
                if (rect.right > windowInnerWidth + 1 || rect.left < -1) {
                    overflowing.push({
                        tag: el.tagName,
                        className: el.className,
                        id: el.id,
                        right: rect.right,
                        left: rect.left,
                        width: rect.width,
                        outerHTML: el.outerHTML.substring(0, 100)
                    });
                }
            }
            return {
                docWidth,
                scrollWidth,
                bodyScrollWidth,
                windowInnerWidth,
                overflowingCount: overflowing.length,
                overflowing: overflowing.slice(0, 20)
            };
        })()
        """
        eval_res = cdp_send("Runtime.evaluate", {
            "expression": overflow_js,
            "returnByValue": True
        })
        print("OVERFLOW RESULTS FOR LANDING AT 390px:")
        print(json.dumps(eval_res.get("result", {}).get("value", {}), indent=2))

        # Take screenshot
        snap = cdp_send("Page.captureScreenshot", {"format": "png"})
        if "data" in snap:
            with open(r"C:\Users\Sam\.gemini\antigravity-ide\brain\cd568210-fb52-4b98-b45b-bad2a032451c\landing_390.png", "wb") as f:
                f.write(base64.b64decode(snap["data"]))
            print("Saved landing_390.png successfully!")

        ws.close()
    finally:
        proc.terminate()

if __name__ == "__main__":
    run_test()
