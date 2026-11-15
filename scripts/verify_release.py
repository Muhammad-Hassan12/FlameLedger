"""Verify a self-contained release before it is accepted by the API or deployed."""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from scripts.common import digest_json, json_read, jsonl_read, safe_child, sha256, ordered_id_digest


def verify(release, *, allow_dense_failure=False):
    release = Path(release).resolve()
    manifest = json_read(release / "release.json")
    errors, dense_errors = [], []
    if manifest.get("schema_version") != 1 or manifest.get("data_mode") != "verified":
        errors.append("Unsupported release contract")
    files = manifest.get("files", {})
    for required in ("evidence/evidence.sqlite3", "evidence/passages.jsonl", "evidence/manifest.json", "evidence/sources.json", "frontend/index.html"):
        if required not in files:
            errors.append(f"Required asset omitted from manifest: {required}")
    if manifest.get("mode") not in {"hybrid", "cached_bm25", "bm25"}:
        errors.append("Release retrieval mode is invalid")
    if manifest.get("mode") in {"hybrid", "cached_bm25"}:
        for required in ("index/manifest.json", "index/vectors.npy", "index/passages.jsonl", "index/preset_vectors.json"):
            if required not in files:
                dense_errors.append(f"Required dense asset omitted: {required}")
    if manifest.get("mode") == "hybrid" and "model/config.json" not in files:
        dense_errors.append("Live hybrid release requires its model")
    for name, expected in files.items():
        try:
            file = safe_child(release, name)
            if not file.is_file() or sha256(file) != expected:
                raise ValueError(f"Asset checksum mismatch: {name}")
        except (ValueError, OSError) as error:
            (dense_errors if name.startswith(("index/", "model/")) else errors).append(str(error))
    db = release / "evidence/evidence.sqlite3"
    if not errors:
        try:
            with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    errors.append("SQLite integrity failure")
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    errors.append("SQLite orphaned reference")
                actual_id = conn.execute("SELECT value FROM metadata WHERE key='release_id'").fetchone()[0]
                if actual_id != manifest["release_id"]:
                    errors.append("Data release ID mismatch")
                import json
                sources = [json.loads(p) for (p,) in conn.execute("SELECT payload FROM sources")]
                investigations = [json.loads(p) for (p,) in conn.execute("SELECT payload FROM investigations")]
                runs = [json.loads(p) for (p,) in conn.execute("SELECT payload FROM runs")]
            passages = jsonl_read(release / "evidence/passages.jsonl")
            if len({p["id"] for p in passages}) != len(passages):
                errors.append("Duplicate passage IDs")
            from scripts.build_evidence import validate
            source_records = [{k:v for k,v in source.items() if k != "local_path"} for source in sources]
            validate({"investigations":investigations,"runs":runs,"passages":passages},source_records)
            for source in sources:
                bundled = release / "evidence/source_files" / (source["id"]+".pdf")
                if bundled.is_file() and sha256(bundled) != source.get("sha256"):
                    errors.append("Bundled source checksum differs from source metadata")
            if manifest["mode"] != "bm25" and not dense_errors:
                from backend.retrieval import validate_matrix
                index = json_read(release / "index/manifest.json")
                indexed = jsonl_read(release / "index/passages.jsonl")
                if ordered_id_digest(indexed) != ordered_id_digest(passages):
                    dense_errors.append("Evidence and index row-ID mismatch")
                if index["evidence_release_id"] != actual_id:
                    dense_errors.append("Index and evidence release mismatch")
                if index["passages_sha256"] != sha256(release / "index/passages.jsonl"):
                    dense_errors.append("Index passage checksum mismatch")
                try:
                    validate_matrix(release / "index/vectors.npy", indexed, index)
                except ValueError as error:
                    dense_errors.append(str(error))
                model_files = {n.removeprefix("model/"): v for n, v in files.items() if n.startswith("model/")}
                if model_files and digest_json(model_files) != index["model_fingerprint"]:
                    dense_errors.append("Model/index checkpoint identity mismatch")
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
            errors.append(str(error))
    return {"valid": not errors and (allow_dense_failure or not dense_errors), "release_id": manifest.get("release_id"),
            "mode": manifest.get("mode"), "files_verified": len(files), "errors": errors, "dense_errors": dense_errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.release)
    except (OSError, ValueError, KeyError) as error:
        report = {"valid": False, "errors": [str(error)]}
    import json
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
