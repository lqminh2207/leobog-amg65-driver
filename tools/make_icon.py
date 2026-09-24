#!/usr/bin/env python3
"""Renders assets/app-icon.png (1024px) and assets/AppIcon.icns from assets/dragon.svg.

Dev-only tool: needs Playwright + Google Chrome to rasterise the SVG. The outputs are
committed, so building the app does not run this.
Dragon: "Spiked dragon head" by Delapouite, game-icons.net, CC BY 3.0.
"""
import os
import re
import subprocess
import tempfile

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def dragon_paths():
    svg = open(os.path.join(ASSETS, "dragon.svg")).read()
    # game-icons ship a black 512x512 backdrop path first; keep only the silhouette
    return [d for d in re.findall(r'<path[^>]*\bd="([^"]+)"', svg) if not d.startswith("M0 0h512v512H0z")]


def page_html():
    paths = "".join(f'<path d="{d}"/>' for d in dragon_paths())
    return f"""<html><body style="margin:0;background:transparent">
<svg width="1024" height="1024" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#232b40"/><stop offset="1" stop-color="#07090e"/>
    </linearGradient>
    <linearGradient id="fire" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#00f0ff"/><stop offset=".55" stop-color="#a855f7"/><stop offset="1" stop-color="#ff007f"/>
    </linearGradient>
    <radialGradient id="halo" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#a855f7" stop-opacity=".35"/><stop offset="1" stop-color="#a855f7" stop-opacity="0"/>
    </radialGradient>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
      <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000" flood-opacity=".55"/>
    </filter>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="14" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="squircle"><rect x="100" y="100" width="824" height="824" rx="185"/></clipPath>
  </defs>
  <rect x="100" y="100" width="824" height="824" rx="185" fill="url(#bg)" filter="url(#shadow)"/>
  <g clip-path="url(#squircle)"><circle cx="512" cy="520" r="360" fill="url(#halo)"/></g>
  <rect x="102" y="102" width="820" height="820" rx="183" fill="none" stroke="#fff" stroke-opacity=".09" stroke-width="4"/>
  <g transform="translate(192 190) scale(1.25)" fill="url(#fire)" filter="url(#glow)">{paths}</g>
</svg></body></html>"""


def main():
    png_path = os.path.join(ASSETS, "app-icon.png")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1024, "height": 1024})
        page.set_content(page_html())
        page.screenshot(path=png_path, omit_background=True, clip={"x": 0, "y": 0, "width": 1024, "height": 1024})
        browser.close()

    icon = Image.open(png_path).convert("RGBA")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset")
        os.makedirs(iconset)
        for size in (16, 32, 128, 256, 512):
            icon.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
            icon.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ASSETS, "AppIcon.icns")], check=True)
    print("wrote assets/app-icon.png and assets/AppIcon.icns")


if __name__ == "__main__":
    main()
