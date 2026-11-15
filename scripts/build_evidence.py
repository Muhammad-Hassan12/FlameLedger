"""Validate curated source rows and build a read-only SQLite evidence snapshot."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sqlite3
from contextlib import closing
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from scripts.common import ROOT, digest_json, json_read, json_write, jsonl_read, jsonl_write, safe_child, sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(data, sources):
    source_ids = {s["id"] for s in sources}
    require(len(source_ids) == len(sources), "Duplicate source ID")
    require(all(re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", sid) for sid in source_ids), "Unsafe source ID")
    inv_ids = {i["id"] for i in data["investigations"]}
    require(len(inv_ids) == len(data["investigations"]), "Duplicate investigation ID")
    run_ids = [r["id"] for r in data["runs"]]
    require(len(set(run_ids)) == len(run_ids), "Duplicate run ID")
    require(all(re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", rid) for rid in run_ids), "Unsafe run ID")
    measurement_ids = [m["id"] for r in data["runs"] for m in r["measurements"]]
    require(len(measurement_ids) == len(set(measurement_ids)), "Duplicate measurement ID")

    def citation(row, label):
        require(row.get("source_id") in source_ids, f"Orphaned source reference: {label}")
        loc = row.get("locator") or {}
        require(bool(loc.get("page") or loc.get("label")), f"Missing source locator: {label}")
        if loc.get("page") is not None:
            require(type(loc["page"]) is int and loc["page"] >= 1, f"Invalid PDF page: {label}")

    for source in sources:
        url = urlparse(source["url"])
        require(url.scheme == "https" and bool(url.netloc), f"Invalid source URL: {source['id']}")
        if source.get("local_path"):
            file = safe_child(ROOT, source["local_path"])
            require(file.is_file() and sha256(file) == source["sha256"], f"Source checksum mismatch: {source['id']}")
        require(source.get("license_status") and source.get("retrieved_at"), f"Missing provenance: {source['id']}")
    for run in data["runs"]:
        require(run["investigation_id"] in inv_ids, f"Orphaned investigation: {run['id']}")
        require(run["lane"] in {"prevention", "detection", "suppression"}, f"Invalid research lane: {run['id']}")
        require(run["evidence_type"] in {"run", "aggregate_observation", "observation"}, "Unknown evidence type")
        require(run["review_status"] in {"pending", "source_checked", "human_verified"}, "Unknown review state")
        if run["review_status"] == "human_verified":
            require(run.get("reviewer") and run.get("reviewed_at"), "Independent verification needs a reviewer and review date")
        citation(run, run["id"])
        phase_keys = [p["key"] for p in run["phases"]]
        require(len(phase_keys) == len(set(phase_keys)), f"Duplicate phase: {run['id']}")
        for phase in run["phases"]:
            citation(phase, run["id"] + "/" + phase["key"])
            for key, lo, hi in (("oxygen_pct", 0, 100), ("pressure_kpa", 0, 1000), ("g_level", 0, 10), ("flow_cm_s", 0, 10000)):
                value = phase.get(key)
                require(value is None or (type(value) in {int, float} and math.isfinite(value) and lo <= value <= hi), f"Invalid {key}: {run['id']}")
                require(key != "pressure_kpa" or value is None or value > 0, "Pressure must be absolute and positive")
            if phase.get("oxygen_pct") is not None:
                require(phase.get("oxygen_basis") in {"mole", "volume", "unspecified"}, "Missing oxygen basis")
            require(isinstance(phase.get("original"), dict), "Original values/units must be retained")
        for measurement in run["measurements"]:
            citation(measurement, measurement["id"])
            require(measurement.get("phase_key") is None or measurement["phase_key"] in phase_keys, "Orphaned measurement phase")
            require(measurement.get("definition") and measurement.get("endpoint"), "Outcome requires an endpoint definition")
            if measurement.get("verification_status") in {"source_checked", "human_verified"}:
                require(measurement.get("outcome") or measurement.get("value") is not None, "Unsupported measurement marked checked")
            if measurement.get("value") is not None:
                require(type(measurement["value"]) in {int, float} and math.isfinite(measurement["value"]) and measurement.get("unit"), "Invalid numerical measurement")
    passage_ids = [p["id"] for p in data["passages"]]
    require(len(set(passage_ids)) == len(passage_ids), "Duplicate passage ID")
    for passage in data["passages"]:
        require(passage["source_id"] in source_ids, "Orphaned passage source")
        require(passage.get("text") and passage.get("title"), "Empty passage")
        require(all(r in run_ids for r in passage.get("run_ids", [])), "Orphaned passage/run join")
        if passage["kind"] != "document_context":
            citation(passage, passage["id"])


def import_literature(run_dir, sources, data):
    corpus = Path(run_dir) / "chunks.jsonl"
    if not corpus.is_file():
        return
    corpus_hash = sha256(corpus)
    known_sources = {s.get("ntrs_id"): s["id"] for s in sources}
    present_ids = {s["id"] for s in sources}
    for item in jsonl_read(corpus):
        ntrs_id = item["paper_id"].removeprefix("NTRS_")
        sid = known_sources.get(ntrs_id) or known_sources.get(int(ntrs_id)) if ntrs_id.isdigit() else None
        sid = sid or item["source_id"]
        if sid not in present_ids:
            sources.append({"id": sid, "title": item["title"], "url": f"https://ntrs.nasa.gov/citations/{ntrs_id}",
                            "ntrs_id": ntrs_id, "psi_id": None, "sha256": corpus_hash,
                            "retrieved_at": "2026-11-15", "license_status": "NTRS public metadata; verify rights on original document before redistribution",
                            "challenge_resource": False, "import_status": "legacy_literature_context",
                            "local_path": corpus.relative_to(ROOT).as_posix(),
                            "package_relationship": "Provided training-run corpus; original PDF/abstract provenance retained, page locator unavailable"})
            present_ids.add(sid)
        text = (item["title"] + " " + item["text"]).casefold()
        lane = "detection" if any(t in text for t in ("smoke detector", "smoke detection", "aerosol")) else "suppression" if any(t in text for t in ("extinction", "suppress", "extinguish")) else "prevention"
        data["passages"].append({"id": item["doc_id"], "source_id": sid, "paper_id": item["paper_id"],
                                 "title": item["title"], "text": item["text"], "kind": "document_context",
                                 "original_kind": item["kind"], "lane": lane, "run_ids": [],
                                 "locator": {"label": "Abstract" if item["kind"] == "abstract" else "Legacy passage; page locator unavailable"},
                                 "review_status": "pending", "provenance": "Supplied legacy literature baseline; never a verified physical run"})


def build(manifest, curated, out, run_dir=None):
    sources = json_read(manifest)["sources"]
    data = json_read(curated)
    if run_dir:
        import_literature(run_dir, sources, data)
    validate(data, sources)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Stable identities are tied to source bytes and curated rows, not build wall-clock time.
    release_id = "evidence-" + digest_json({"sources": sources, "data": data})[:16]
    db_path = out / "evidence.sqlite3"
    temp = out / "evidence.sqlite3.tmp"
    with closing(sqlite3.connect(temp)) as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS metadata; DROP TABLE IF EXISTS sources;
            DROP TABLE IF EXISTS investigations; DROP TABLE IF EXISTS runs; DROP TABLE IF EXISTS passages;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE investigations (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE runs (id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL REFERENCES investigations(id), source_id TEXT NOT NULL REFERENCES sources(id), payload TEXT NOT NULL);
            CREATE TABLE passages (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), payload TEXT NOT NULL);
        """)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executemany("INSERT INTO sources VALUES (?,?)", [(s["id"], json.dumps(s, ensure_ascii=False)) for s in sources])
        conn.executemany("INSERT INTO investigations VALUES (?,?)", [(r["id"], json.dumps(r, ensure_ascii=False)) for r in data["investigations"]])
        conn.executemany("INSERT INTO runs VALUES (?,?,?,?)", [(r["id"], r["investigation_id"], r["source_id"], json.dumps(r, ensure_ascii=False)) for r in data["runs"]])
        conn.executemany("INSERT INTO passages VALUES (?,?,?)", [(p["id"], p["source_id"], json.dumps(p, ensure_ascii=False)) for p in data["passages"]])
        conn.execute("INSERT INTO metadata VALUES ('release_id',?)", (release_id,))
        conn.execute("INSERT INTO metadata VALUES ('data_mode','verified')")
        conn.commit()
        require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity check failed")
    temp.replace(db_path)
    passages = sorted(data["passages"], key=lambda p: p["id"])
    jsonl_write(out / "passages.jsonl", passages)
    json_write(out / "sources.json", {"sources": sources})
    approved=ROOT/"data/curated/approved_briefings.json"
    if approved.is_file():
        json_write(out/"approved_briefings.json",json_read(approved))
    for source in sources:
        local = source.get("local_path")
        if local and Path(local).suffix.lower() == ".pdf":
            target = out / "source_files" / (source["id"] + ".pdf")
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(safe_child(ROOT, local), target)
    stats = {"release_id": release_id, "runs": len(data["runs"]), "passages": len(passages), "sources": len(sources),
             "investigations": dict(Counter(r["investigation_id"] for r in data["runs"])),
             "review_states": dict(Counter(r["review_status"] for r in data["runs"])),
             "citation_types": dict(Counter(p["kind"] for p in passages)),
             "human_review_required": any(r["review_status"] != "human_verified" for r in data["runs"]),
             "built_at": datetime.now(timezone.utc).isoformat(), "database_sha256": sha256(db_path)}
    json_write(out / "manifest.json", stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/sources.json")
    parser.add_argument("--curated", type=Path, default=ROOT / "data/curated/evidence.json")
    parser.add_argument("--out", type=Path, default=ROOT / "build/evidence")
    parser.add_argument("--run-dir", type=Path, default=ROOT / "NASA_Flame_In_Freefall_Final/runs/full")
    args = parser.parse_args()
    print(json.dumps(build(args.manifest, args.curated, args.out, args.run_dir), indent=2))


if __name__ == "__main__":
    main()
