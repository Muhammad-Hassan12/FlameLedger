"""Download the explicitly selected public source versions; never modify originals."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error
import time

ROOT = Path(__file__).resolve().parents[1]
NTRS_IDS = ["20210011521", "20240007488", "20250010653", "20250002114", "20240015307", "20210011385", "20150023456"]


def download(url, timeout=120):
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={"User-Agent":"FlameLedger-research/1.0"})
            with urllib.request.urlopen(request,timeout=timeout) as response:
                return response.read(100*1024*1024)
        except (urllib.error.URLError,TimeoutError) as error:
            if isinstance(error,urllib.error.HTTPError) and error.code not in {429,500,502,503,504}:
                raise
            if attempt == 2:raise
            time.sleep(2*(attempt+1))

def fetch(ntrs_id):
    target = ROOT / "data" / "raw" / ntrs_id
    target.mkdir(parents=True, exist_ok=True)
    metadata=target/"metadata.json"
    data=json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else json.loads(download(f"https://ntrs.nasa.gov/api/citations/{ntrs_id}",timeout=30))
    (target / "metadata.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    files = []
    for item in data.get("downloads", []):
        name = item.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue
        url = item.get("links", {}).get("pdf") or f"/api/citations/{ntrs_id}/downloads/{urllib.parse.quote(name)}"
        if url.startswith("/"):
            url = "https://ntrs.nasa.gov" + url
        output = target / Path(name).name
        if not output.exists():
            content=download(url)
            if not content.startswith(b"%PDF"):raise ValueError(f"Unexpected non-PDF body: {url}")
            temporary=output.with_suffix(".pdf.part")
            temporary.write_bytes(content)
            temporary.replace(output)
        content = output.read_bytes()
        if not content.startswith(b"%PDF"):
            raise ValueError(f"Unexpected non-PDF download: {output}")
        files.append({"file":str(output.relative_to(ROOT)),"sha256":hashlib.sha256(content).hexdigest(),"url":url})
    return {"ntrs_id":ntrs_id,"title":data.get("title"),"files":files}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", default=NTRS_IDS)
    parser.add_argument("--nist", action="store_true", help="Also preserve the official detector-study HTML for checksum provenance")
    args = parser.parse_args()
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,ntrs_id):ntrs_id for ntrs_id in args.ids}
        for future in concurrent.futures.as_completed(futures):
            try:print(json.dumps(future.result()),flush=True)
            except Exception as error:
                errors.append({"ntrs_id":futures[future],"error":str(error)})
    if args.nist:
        try:
            for source,url in (("nist-detectors","https://www.nist.gov/publications/evaluation-spacecraft-smoke-detector-performance-low-gravity-environment"),
                               ("nist-detectors-news","https://www.nist.gov/news-events/news/2018/05/nistnasa-study-shows-one-detector-doesnt-fit-all-smoke-spacecraft")):
                target=ROOT/"data/raw"/source/"source.html"
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():target.write_bytes(download(url,timeout=30))
                print(json.dumps({"source":source,"file":str(target.relative_to(ROOT)),"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)
        except Exception as error:errors.append({"source":"NIST-detectors","error":str(error)})
    if errors:
        print(json.dumps({"download_errors":errors}),flush=True)
        raise SystemExit(1)
