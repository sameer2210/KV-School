import subprocess
import time
import requests
import json
import base64

# Start Chrome in headless mode with remote debugging
proc = subprocess.Popen([
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new",
    "--remote-debugging-port=9222",
    "--user-data-dir=C:\\Users\\Sam\\AppData\\Local\\Temp\\chrome_cdp",
    "--no-first-run",
    "--disable-gpu",
    "about:blank"
])

try:
    time.sleep(1.5)
    version = requests.get("http://localhost:9222/json/version").json()
    print("CDP Version:", version)

    # Open target
    new_tab = requests.put("http://localhost:9222/json/new?http://127.0.0.1:5000/").json()
    print("New tab:", new_tab)
finally:
    proc.terminate()
