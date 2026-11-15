"""Package an immutable local release; require explicit mode when omitting dense assets."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from scripts.common import ROOT, json_read, json_write, sha256
from scripts.verify_release import verify


def assemble(evidence,frontend,out,index=None,model=None,mode="cached_bm25"):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Release destination must be empty; stage each release in a new directory")
    if mode != "bm25" and not index:
        raise ValueError("Dense modes require a bound index")
    if mode == "hybrid" and not model:
        raise ValueError("Live hybrid requires the exact local text checkpoint")
    out.mkdir(parents=True,exist_ok=True)
    for name,path in (("evidence",evidence),("frontend",frontend),("index",index),("model",model)):
        if path:shutil.copytree(path,out/name)
    for name in ("backend", "scripts"):
        shutil.copytree(ROOT/name,out/name,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for filename in ("requirements.txt","requirements-ml.txt","requirements-runtime.lock","requirements-serving.lock"):
        shutil.copyfile(ROOT/filename,out/filename)
    files={p.relative_to(out).as_posix():sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    manifest={"schema_version":1,"release_id":json_read(Path(evidence)/"manifest.json")["release_id"],
              "mode":mode,"data_mode":"verified","files":files,
              "review_gate":"Source-checked rows remain a preview until independent human verification is recorded."}
    json_write(out/"release.json",manifest)
    report=verify(out)
    if not report["valid"]:raise ValueError(str(report))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("evidence","frontend","out"):parser.add_argument("--"+key,type=Path,required=True)
    for key in ("index","model"):parser.add_argument("--"+key,type=Path)
    parser.add_argument("--mode",choices=("hybrid","cached_bm25","bm25"),default="cached_bm25")
    args=parser.parse_args();print(json.dumps(assemble(args.evidence,args.frontend,args.out,args.index,args.model,args.mode),indent=2))


if __name__ == "__main__":main()
