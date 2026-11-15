from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from scripts.common import jsonl_read


class EvidenceStore:
    def __init__(self, release):
        self.release = Path(release).resolve()
        db = self.release / "evidence/evidence.sqlite3"
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
            self.release_id = conn.execute("SELECT value FROM metadata WHERE key='release_id'").fetchone()[0]
            self.sources = {r["id"]: r for (payload,) in conn.execute("SELECT payload FROM sources ORDER BY id") for r in [json.loads(payload)]}
            self.investigations = {r["id"]: r for (payload,) in conn.execute("SELECT payload FROM investigations ORDER BY id") for r in [json.loads(payload)]}
            self.runs = [json.loads(p) for (p,) in conn.execute("SELECT payload FROM runs ORDER BY id")]
        self.passages = jsonl_read(self.release / "evidence/passages.jsonl")
        self.by_id = {r["id"]: r for r in self.runs}

    def source_card(self, source_id, locator=None):
        source = self.sources[source_id]
        card = {k: source.get(k) for k in ("id", "title", "url", "ntrs_id", "psi_id", "license_status", "retrieved_at", "sha256", "import_status", "challenge_resource", "package_relationship")}
        card["locator"] = locator
        local = self.release / "evidence/source_files" / f"{source_id}.pdf"
        card["file_url"] = f"/api/sources/{source_id}/file" if local.is_file() else None
        return card

    def enrich_run(self, run):
        return {**run, "investigation": self.investigations[run["investigation_id"]],
                "citation": self.source_card(run["source_id"], run.get("locator")),
                "measurements": [{**m, "citation": self.source_card(m["source_id"], m.get("locator"))} for m in run["measurements"]]}
