"""Create a silent, locally playable walkthrough from the real running release."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.common import json_write


def record(url,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    raw=out/"raw";raw.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel="chrome",headless=True)
        context=browser.new_context(viewport={"width":1280,"height":800},record_video_dir=str(raw),record_video_size={"width":1280,"height":800},reduced_motion="reduce")
        page=context.new_page();page.goto(url,wait_until="networkidle");page.locator(".run-card").first.wait_for()
        page.wait_for_timeout(1200)
        page.locator(".run-card [data-source]").first.click();page.locator("#source-drawer .source-section").first.wait_for();page.wait_for_timeout(1600);page.keyboard.press("Escape")
        page.locator("#compare").scroll_into_view_if_needed();page.wait_for_timeout(1600)
        page.locator("#comparison [data-source]").last.click();page.locator("#source-drawer .source-section").first.wait_for();page.wait_for_timeout(1600);page.keyboard.press("Escape")
        page.locator("#coverage").scroll_into_view_if_needed();page.locator("#preview-coverage").check();page.wait_for_timeout(1000)
        populated=page.locator(".coverage-matrix button.populated").first
        if populated.count():populated.click()
        page.wait_for_timeout(1000);page.locator("#export").scroll_into_view_if_needed()
        if populated.count():
            with page.expect_download():page.locator("#export").click()
        page.locator("#clear-cell").click();page.locator('[data-lane="detection"]').click()
        page.locator("#run-scenario:not([disabled])").wait_for()
        page.locator(".run-card").first.wait_for();page.wait_for_timeout(1500)
        page.locator('[data-lane="suppression"]').click();page.locator("#run-scenario:not([disabled])").wait_for()
        page.locator(".run-card").first.wait_for();page.wait_for_timeout(1600)
        page.locator(".run-card [data-source]").first.click();page.locator("#source-drawer .source-section").first.wait_for();page.wait_for_timeout(1800)
        video=page.video;context.close();source=Path(video.path());browser.close()
    # Playwright supplies this small encoder with `python -m playwright install ffmpeg`.
    cache=Path(__import__('os').environ.get("LOCALAPPDATA",""))/"ms-playwright"
    encoders=sorted(cache.glob("ffmpeg-*/ffmpeg-win64.exe"))
    output=out/"flameledger-walkthrough.webm"
    if output.exists():raise ValueError("Recording output already exists; select a fresh output directory")
    if encoders:
        subprocess.run([str(encoders[-1]),"-n","-loglevel","error","-i",str(source),"-t","29","-c","copy",str(output)],check=True,capture_output=True)
        info=subprocess.run([str(encoders[-1]),"-i",str(output)],capture_output=True,text=True)
        match=re.search(r"Duration: (\d+):(\d+):([\d.]+)",info.stderr)
        duration=sum(float(value)*factor for value,factor in zip(match.groups(),(3600,60,1))) if match else None
    else:
        source.replace(output);duration=None
    report={"url":url,"path":str(output),"bytes":output.stat().st_size,"duration_seconds":duration,
            "description":"Silent real-application walkthrough: lunar evidence, Saffire source, LUCI comparison, preview coverage, CSV, detector and FLEX extinction lanes.",
            "submission_status":"Venue fallback artifact; current event format and AI-disclosure rules still require verification. No hosted URL or human scientific review is implied."}
    json_write(out/"recording.json",report);return report
