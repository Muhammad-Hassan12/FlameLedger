"""Download the immutable public base revision named in the uploaded model card, for offline evaluation only."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

from scripts.common import ROOT,json_write,safe_child,sha256


def main():
    model_card=ROOT/"NASA_Flame_In_Freefall_Final/runs/full/model_ft/README.md"
    text=model_card.read_text(encoding="utf-8")
    match=re.search(r"Base model:.*?at revision ([a-f0-9]{40})",text)
    if not match:raise ValueError("The supplied model card does not identify an immutable base revision")
    revision=match.group(1);repo="google/embeddinggemma-2"
    url=f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
    with urllib.request.urlopen(url,timeout=30) as response:info=json.load(response)
    if info.get("sha") != revision or info.get("gated"):raise ValueError("Pinned public base revision is not available anonymously")
    destination=ROOT/"build/base-original";destination.mkdir(parents=True,exist_ok=True)
    siblings=[s for s in info["siblings"] if s["rfilename"] != ".gitattributes"]
    def fetch(item):
        name=item["rfilename"];path=safe_child(destination,name);path.parent.mkdir(parents=True,exist_ok=True)
        expected=item.get("lfs",{}).get("sha256")
        if path.is_file() and (not expected or sha256(path)==expected):
            return {"file":name,"sha256":sha256(path),"bytes":path.stat().st_size,"upstream_sha256":expected}
        source=f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        temporary=path.with_suffix(path.suffix+".part")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(source,timeout=90) as response,temporary.open("wb") as stream:
                    received,last_report=0,0
                    for block in iter(lambda:response.read(4*1024*1024),b""):
                        stream.write(block);received+=len(block)
                        if received-last_report >=128*1024*1024:
                            print(f"{name}: {received//(1024*1024)} MiB downloaded",flush=True);last_report=received
                digest=sha256(temporary)
                if expected and digest != expected:raise ValueError("Upstream LFS checksum mismatch")
                temporary.replace(path)
                return {"file":name,"sha256":digest,"bytes":path.stat().st_size,"upstream_sha256":expected}
            except Exception:
                if attempt==2:raise
                time.sleep(2*(attempt+1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        files=list(pool.map(fetch,siblings))
    report={"purpose":"Offline base-hybrid evaluation only; never substituted for the production tuned encoder", "repository":repo,
            "revision":revision,"source_of_revision":"Supplied model_ft/README.md Base model revision comment",
            "license":info.get("cardData",{}).get("license"),"files":files}
    json_write(ROOT/"artifacts/base-reference-download.json",report)
    print(json.dumps({k:v for k,v in report.items() if k!="files"},indent=2))


if __name__ == "__main__":main()
