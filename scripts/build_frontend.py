"""Produce dependency-free, content-versioned static assets and transfer-budget measurements."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

from scripts.common import ROOT, json_write


def build(out):
    source=ROOT/"frontend"
    out=Path(out).resolve()
    if out == source.resolve() or out == ROOT.resolve():
        raise ValueError("Build output must be separate from frontend sources")
    out.mkdir(parents=True,exist_ok=True)
    html=(source/"index.html").read_text(encoding="utf-8")
    expected={"index.html"}
    for filename in ("app.js","styles.css","assets/chamber.webp","assets/favicon.svg"):
        path=source/filename
        contents=path.read_bytes()
        version=hashlib.sha256(contents).hexdigest()[:12]
        target=f"assets/{path.stem}.{version}{path.suffix}"
        (out/target).parent.mkdir(exist_ok=True)
        (out/target).write_bytes(contents)
        expected.add(target)
        html=html.replace("/"+filename,"/"+target)
    (out/"index.html").write_text(html,encoding="utf-8")
    # Only generated build files are pruned, after confirming every resolved path stays in out.
    for old in out.rglob("*"):
        if old.is_file() and old.relative_to(out).as_posix() not in expected:
            if not old.resolve().is_relative_to(out):
                raise ValueError("Unexpected symlink in frontend build")
            old.unlink()
    measurements={p.relative_to(out).as_posix():{"bytes":p.stat().st_size,"gzip_bytes":len(gzip.compress(p.read_bytes(),mtime=0))} for p in out.rglob("*") if p.is_file()}
    total=sum(m["gzip_bytes"] for m in measurements.values())
    js=sum(m["gzip_bytes"] for name,m in measurements.items() if name.endswith(".js"))
    images=sum(m["gzip_bytes"] for name,m in measurements.items() if name.endswith((".png",".webp")))
    report={"files":measurements,"first_screen_gzip_bytes":total,"javascript_gzip_bytes":js,"artwork_gzip_bytes":images,
            "budgets_pass":total <=350*1024 and js <=180*1024 and images <=80*1024,
            "note":"Deterministic gzip transfer estimate, not a rendering metric. Serving headers/browser transfer measured separately."}
    json_write(ROOT/"artifacts/frontend-budget.json",report)
    if not report["budgets_pass"]:raise ValueError("Frontend transfer budget exceeded")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--out",type=Path,default=ROOT/"frontend/out")
    print(json.dumps(build(parser.parse_args().out),indent=2))


if __name__ == "__main__":main()
