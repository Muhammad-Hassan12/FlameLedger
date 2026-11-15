"""Production browser walkthrough, screenshots, reduced motion and throttled rendering measurements."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.common import ROOT,json_write

OBSERVER="""window.__lab={lcp:0,cls:0};new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__lab.lcp=entry.startTime;}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(list=>{for(const entry of list.getEntries())if(!entry.hadRecentInput)window.__lab.cls+=entry.value;}).observe({type:'layout-shift',buffered:true});"""


def run(url,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report={"url":url,"viewports":[],"errors":[]}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel="chrome",headless=True)
        for width in (360,768,1440):
            for motion in ("no-preference","reduce"):
                context=browser.new_context(viewport={"width":width,"height":1000},reduced_motion=motion,device_scale_factor=1)
                page=context.new_page();errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
                page.add_init_script(OBSERVER)
                page.goto(url,wait_until="networkidle")
                page.locator(".run-card").first.wait_for()
                page.locator("#comparison .compare-table").wait_for()
                with page.expect_download() as pair_download:
                    page.locator("#export-comparison").click()
                assert pair_download.value.suggested_filename.endswith(".csv")
                page.locator("#briefing .briefing-lane").first.wait_for()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),f"Horizontal overflow at {width}"
                page.screenshot(path=str(out/f"dashboard-{width}-{motion}.png"),full_page=True)
                button=page.locator(".run-card [data-source]").first
                button.focus();page.keyboard.press("Enter")
                page.locator("#source-drawer .source-section").first.wait_for()
                page.keyboard.press("Escape")
                assert button.evaluate("el=>el===document.activeElement"),"Drawer focus did not return"
                page.locator("#preview-coverage").check()
                cell=page.locator(".coverage-matrix button.populated").first
                if cell.count():
                    cell.click();assert not page.locator("#clear-cell").is_hidden();page.locator("#clear-cell").click()
                page.locator('[data-lane="detection"]').click();page.locator('[data-lane="detection"][aria-pressed="true"]').wait_for()
                page.locator("#run-scenario:not([disabled])").wait_for()
                assert page.locator(".run-card").count()>0
                page.locator("#preset").select_option("iss")
                page.locator("#run-scenario:not([disabled])").wait_for()
                assert page.locator("#oxygen").input_value() == "21"
                with page.expect_download() as download:
                    page.locator("#export").click()
                assert download.value.suggested_filename.endswith(".csv")
                metrics=page.evaluate("({lab:window.__lab,animation:getComputedStyle(document.querySelector('.sprite-flame')).animationName})")
                if motion == "reduce":assert metrics["animation"] == "none"
                report["viewports"].append({"width":width,"motion":motion,"overflow":False,"js_errors":errors,"walkthrough":"passed"})
                report["errors"].extend(errors)
                context.close()
        context=browser.new_context(viewport={"width":360,"height":800},device_scale_factor=1,is_mobile=True,has_touch=True)
        page=context.new_page();page.add_init_script(OBSERVER)
        session=context.new_cdp_session(page);session.send("Network.enable")
        session.send("Network.emulateNetworkConditions",{"offline":False,"latency":150,"downloadThroughput":1_600_000/8,"uploadThroughput":750_000/8})
        session.send("Emulation.setCPUThrottlingRate",{"rate":4})
        page.goto(url,wait_until="networkidle");page.locator(".run-card").first.wait_for();page.wait_for_timeout(400)
        report["mobile_lab"]=page.evaluate("({lcp_ms:window.__lab.lcp,cls:window.__lab.cls,static_transfer_bytes:performance.getEntriesByType('resource').filter(r=>!r.name.includes('/api/')).reduce((n,r)=>n+r.transferSize,0)})")
        report["mobile_lab"]["profile"]="Chrome headless, 360×800, CPU 4×, 150ms latency, 1.6Mbit/s down, cold context; local Windows host"
        page.screenshot(path=str(out/"mobile-throttled.png"),full_page=True)
        context.close()
        context=browser.new_context(viewport={"width":360,"height":800})
        context.route("**/assets/chamber*",lambda route:route.abort())
        page=context.new_page();page.goto(url,wait_until="networkidle");page.locator(".run-card").first.wait_for()
        assert page.locator("#export").is_enabled();report["artwork_failure"]="Evidence remains operable"
        context.close()
        context=browser.new_context(viewport={"width":1440,"height":1000})
        page=context.new_page();page.goto(url,wait_until="networkidle");page.locator(".run-card").first.wait_for()
        profiler=context.new_cdp_session(page);profiler.send("Performance.enable")
        profiles=[]
        for decoration in ("enabled","disabled"):
            if decoration == "disabled":
                page.locator("#chamber-scene").evaluate("el=>{el.hidden=true;el.classList.remove('animate');}")
            before={m["name"]:m["value"] for m in profiler.send("Performance.getMetrics")["metrics"]}
            start=time.perf_counter()
            with page.expect_response(lambda response:response.url.endswith("/api/scenario") and response.request.method == "POST"):
                page.locator("#preset").select_option("iss" if decoration == "enabled" else "lunar")
            page.locator("#run-scenario:not([disabled])").wait_for()
            after={m["name"]:m["value"] for m in profiler.send("Performance.getMetrics")["metrics"]}
            profiles.append({"decoration":decoration,"wall_ms":(time.perf_counter()-start)*1000,
                             **{f"{key}_ms":(after.get(key,0)-before.get(key,0))*1000 for key in ("TaskDuration","ScriptDuration","LayoutDuration")}})
        report["scenario_interaction_profile"]={"samples":profiles,"note":"One local interaction per condition; includes request/render work and is diagnostic, not a causal benchmark or field INP."}
        context.close()
        context=browser.new_context(viewport={"width":768,"height":1000})
        context.route("**/api/brief",lambda route:route.fulfill(status=503,content_type="application/json",body='{"detail":{"message":"Simulated unavailable briefing"}}'))
        page=context.new_page();page.goto(url,wait_until="networkidle");page.locator(".run-card").first.wait_for()
        page.locator("#briefing-mode").filter(has_text="BRIEFING UNAVAILABLE").wait_for()
        assert page.locator("#export").is_enabled();report["briefing_failure"]="Evidence and export remain operable"
        context.close()
        context=browser.new_context(viewport={"width":768,"height":1000})
        page=context.new_page();page.goto(url.split("?")[0]+"?preset=iss&lane=detection",wait_until="networkidle")
        page.locator("#comparison .compare-table").wait_for()
        assert page.locator("#compare-left").input_value() == "SAFFIRE-VI-2"
        assert "LUCI" in page.locator("#compare-right").input_value()
        with page.expect_download() as pair:page.locator("#export-comparison").click()
        pair.value.save_as(str(out/"comparison-pair.csv"))
        import csv
        with (out/"comparison-pair.csv").open(encoding="utf-8-sig",newline="") as stream:
            pair_rows=list(csv.DictReader(stream))
        assert {r["run_id"] for r in pair_rows} == {page.locator("#compare-left").input_value(),page.locator("#compare-right").input_value()}
        report["filtered_deep_link_and_pair_export"]="Detection deep link retains pinned comparison; CSV contains exactly the selected pair with original units/protocols."
        context.close();browser.close()
    json_write(out/"report.json",report)
    if report["errors"]:raise ValueError(str(report["errors"]))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--url",default="http://127.0.0.1:8000");parser.add_argument("--out",default=str(ROOT/"artifacts/browser"))
    parser.add_argument("--record-only",action="store_true",help="Record a real walkthrough instead of repeating browser checks")
    args=parser.parse_args()
    if args.record_only:
        from scripts.record_demo import record
        report=record(args.url,Path(args.out))
    else:report=run(args.url,args.out)
    print(json.dumps(report,indent=2))


if __name__ == "__main__":main()
