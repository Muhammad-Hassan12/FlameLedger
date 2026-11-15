"""Package only verified release assets into a reproducible, traversal-safe Linux deployment archive."""
from __future__ import annotations

import argparse
import gzip
import json
import tarfile
import time
from pathlib import Path,PurePosixPath

from scripts.common import json_read,json_write,safe_child,sha256
from scripts.verify_release import verify


def pack(release,out):
    release,out=Path(release).resolve(),Path(out).resolve()
    if out.is_relative_to(release) or out.exists():raise ValueError("Choose a fresh archive path outside the immutable release")
    report=verify(release)
    if not report["valid"]:raise ValueError(str(report))
    manifest=json_read(release/"release.json")
    names=sorted([*manifest["files"],"release.json"])
    for name in names:
        parts=PurePosixPath(name).parts
        if ".env" in parts or ".git" in parts or any(part.startswith(".env.") for part in parts):
            raise ValueError("Secrets and Git metadata must remain outside release archives")
        if safe_child(release,name).is_symlink():raise ValueError("Release archives contain regular files only")
    out.parent.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    def portable(info):
        info.uid=info.gid=info.mtime=0;info.uname=info.gname="";info.mode=0o644
        return info
    with out.open("wb") as raw,gzip.GzipFile(fileobj=raw,filename="",mode="wb",compresslevel=3,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode="w|") as archive:
            for name in names:
                archive.add(safe_child(release,name),arcname="flameledger/"+name,recursive=False,filter=portable)
    result={"archive":str(out),"archive_sha256":sha256(out),"archive_bytes":out.stat().st_size,
            "release_manifest_sha256":sha256(release/"release.json"),"evidence_release_id":manifest["release_id"],
            "regular_files":len(names),"elapsed_seconds":time.perf_counter()-start,
            "note":"Extract into a fresh staging directory, then verify the extracted release before activation. No credentials or reference base weights are packaged."}
    json_write(out.with_suffix(out.suffix+".json"),result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",required=True,type=Path);parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args();print(json.dumps(pack(args.release,args.out),indent=2))


if __name__ == "__main__":main()
