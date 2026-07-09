import sys
from playwright.sync_api import sync_playwright
html_path, out_path = sys.argv[1], sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 1300
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
    pg.goto("file://" + html_path)
    pg.wait_for_timeout(400)
    (pg.query_selector(".card") or pg).screenshot(path=out_path)
    b.close()
print("wrote", out_path)
