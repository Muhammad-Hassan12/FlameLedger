"""Run the public walkthrough plus a bounded four-client mixed-load smoke test."""
import argparse
import concurrent.futures
import json
import time
from collections import Counter

import httpx
import numpy as np

from scripts.common import json_write


def smoke(base_url,clients=4):
    with httpx.Client(base_url=base_url,timeout=20) as client:
        ready=client.get("/api/readyz");ready.raise_for_status()
        result=client.post("/api/scenario",json={"preset_id":"lunar"});result.raise_for_status();data=result.json()
        assert data["runs"],"No evidence loaded"
        for run in data["runs"]:client.get(f"/api/runs/{run['id']}").raise_for_status()
        pins=data["pinned_examples"]
        atmosphere=next(p["id"] for p in pins if p["label"] == "Atmosphere analog")
        gravity=next(p["id"] for p in pins if p["label"] == "Gravity analog")
        compare=client.post("/api/compare",json={"run_ids":[atmosphere,gravity]});compare.raise_for_status()
        assert compare.json()["delta"] is None
        csv=client.get("/api/export",params={"release_id":data["release_id"]});csv.raise_for_status()
        assert "source_url" in csv.text
        assert client.get("/api/export",params={"release_id":"stale"}).status_code == 409
        for lane in ("detection","suppression"):
            scoped=client.post("/api/scenario",json={"preset_id":"iss","lane":lane});scoped.raise_for_status()
            assert scoped.json()["runs"],f"No {lane} evidence"
        search_start=time.perf_counter()
        search=client.post("/api/search",json={"query":"What do the FLEX droplet tests report about visible-flame extinction in methanol?"})
        search.raise_for_status()
        cold_search_seconds=time.perf_counter()-search_start
        observed_mode=search.json()["retrieval_mode"]
    retrieval_modes=[]
    def worker(i):
        timings=[]
        with httpx.Client(base_url=base_url,timeout=20) as client:
            for preset in ("lunar","iss"):
                start=time.perf_counter();response=client.post("/api/scenario",json={"preset_id":preset});response.raise_for_status()
                timings.append(("scenario",time.perf_counter()-start))
                start=time.perf_counter();response=client.post("/api/brief",json={"scenario":{"preset_id":preset},"release_id":data["release_id"]});response.raise_for_status()
                timings.append(("brief",time.perf_counter()-start))
                start=time.perf_counter();response=client.post("/api/search",json={"query":"spacecraft smoke detector response"});response.raise_for_status()
                timings.append(("search",time.perf_counter()-start))
                retrieval_modes.append(response.json()["retrieval_mode"])
        return timings
    with concurrent.futures.ThreadPoolExecutor(max_workers=clients) as pool:
        timings=[pair for output in pool.map(worker,range(clients)) for pair in output]
    return {"base_url":base_url,"clients":clients,"release_id":data["release_id"],"readiness":ready.json(),"run_count":data["total"],
            "scenario_p95_seconds":float(np.percentile([t for kind,t in timings if kind == "scenario"],95)),
            "brief_p95_seconds":float(np.percentile([t for kind,t in timings if kind == "brief"],95)),
            "search_p95_seconds":float(np.percentile([t for kind,t in timings if kind == "search"],95)),
            "first_custom_search_seconds":cold_search_seconds,"first_custom_search_mode":observed_mode,
            "mixed_search_modes":dict(Counter(retrieval_modes)),
            "note":"Local or hosted smoke according to base_url. Template/cache timing is not live Gemini latency. Host RAM and swap need independent measurement."}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--url",default="http://127.0.0.1:8000");parser.add_argument("--out",default="artifacts/api-smoke.json")
    args=parser.parse_args();report=smoke(args.url);json_write(args.out,report);print(json.dumps(report,indent=2))


if __name__ == "__main__":main()
