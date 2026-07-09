#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML -> PNG レンダラ。使い方: python3 render.py input.html output.png [width]"""
import sys
from playwright.sync_api import sync_playwright

html_path = sys.argv[1]
out_path = sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 1120

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
    page.goto("file://" + html_path)
    page.wait_for_timeout(300)
    el = page.query_selector(".card") or page
    el.screenshot(path=out_path)
    browser.close()
print("wrote", out_path)
