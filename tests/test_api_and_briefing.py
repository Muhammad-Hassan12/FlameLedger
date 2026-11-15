import asyncio
import copy
import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend.briefing import validate_summary
from backend.config import Settings
from backend.main import create_app,csv_safe
from scripts.verify_release import verify
from scripts.common import FORMATTING_VERSION,json_write,jsonl_read,jsonl_write,ordered_id_digest,sha256


def valid_summary():
    return {"sections":[{"lane":"prevention","claims":[{"text":"The cited study reports material combustion observations.","limit":"Setup differences limit comparison.","evidence_ids":["E-TEST"]}]}]}


@pytest.mark.parametrize("mutation",["unknown_id","number","safety","wrong_domain","missing_id","extra_key"])
def test_generated_claim_validation(mutation):
    summary=valid_summary();claim=summary["sections"][0]["claims"][0]
    if mutation == "unknown_id":claim["evidence_ids"]=["UNKNOWN"]
    if mutation == "number":claim["text"]="Oxygen was 34 percent."
    if mutation == "safety":claim["text"]="This setup is safe."
    if mutation == "wrong_domain":summary["sections"][0]["lane"]="suppression"
    if mutation == "missing_id":claim["evidence_ids"]=[]
    if mutation == "extra_key":claim["extra"]="surprise"
    with pytest.raises(ValueError):validate_summary(summary,{"E-TEST":{"lane":"prevention"}})


def test_valid_structure_is_not_claimed_as_human_approval():
    assert validate_summary(valid_summary(),{"E-TEST":{"lane":"prevention"}}) == valid_summary()


def test_empty_generated_briefing_is_rejected():
    with pytest.raises(ValueError):validate_summary({"sections":[{"lane":"prevention","claims":[]}]},{"E-TEST":{"lane":"prevention"}})


def test_api_scenario_compare_sources_export_and_stale_release(fixture_release):
    with TestClient(create_app(Settings(fixture_release,runtime_mode="bm25"))) as client:
        assert client.get("/api/readyz").json()["ready"]
        data=client.post("/api/scenario",json={"preset_id":"lunar"}).json()
        assert len(data["runs"]) == 3
        assert data["coverage"]["unique_runs"] == 0
        assert data["preview_coverage"]["unique_runs"] == 2
        assert client.get("/api/runs/TEST-R1").status_code == 200
        assert client.get("/api/runs/UNKNOWN").status_code == 404
        result=client.post("/api/compare",json={"run_ids":["TEST-R1","TEST-R2"]}).json()
        assert result["delta"] is None
        assert client.post("/api/scenario",json={"oxygen_pct":101}).status_code == 422
        assert client.get("/api/export",params={"release_id":"stale"}).status_code == 409
        response=client.get("/api/export",params={"release_id":data["release_id"]})
        assert response.status_code == 200
        rows=list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))))
        assert {r["run_id"] for r in rows} == {"TEST-R1","TEST-R2","TEST-R3"}
        assert all(r["source_url"] == "https://example.org/synthetic" for r in rows)
        pair=client.get("/api/export",params={"release_id":data["release_id"],"ids":"TEST-R1,TEST-R2"})
        pair_rows=list(csv.DictReader(io.StringIO(pair.text.lstrip("\ufeff"))))
        assert {r["run_id"] for r in pair_rows} == {"TEST-R1","TEST-R2"}
        assert pair_rows[0]["condition_protocol"] == "fixture protocol"
        assert pair_rows[0]["geometry"] == "Synthetic sheet"
        assert __import__('json').loads(pair_rows[0]["original_conditions"])["oxygen"] == "34 mol%"
        assert len(client.get("/api/catalog").json()["run_options"]) == 3
        brief=client.post("/api/brief",json={"scenario":{"preset_id":"lunar"},"release_id":data["release_id"]}).json()
        assert brief["summary_status"] == "template"
        assert brief["fallback_reason"] == "key_not_configured"
        assert client.post("/api/brief",json={"scenario":{"lane":"detection"},"selected_ids":["TEST-R1"],"release_id":data["release_id"]}).status_code == 422


@pytest.mark.parametrize("failure",["timeout","json","unknown_id","number"])
def test_fake_provider_failures_keep_evidence_and_api_usable(fixture_release,failure):
    async def provider(evidence):
        if failure == "timeout":await asyncio.sleep(.1)
        if failure == "json":raise ValueError("Bad JSON")
        result=valid_summary()
        claim=result["sections"][0]["claims"][0]
        claim["evidence_ids"]=["UNKNOWN"] if failure == "unknown_id" else [next(k for k,v in evidence.items() if v["lane"] == "prevention")]
        if failure == "number":claim["text"]="Observed at 34 percent oxygen."
        return result
    with TestClient(create_app(Settings(fixture_release,runtime_mode="bm25",gemini_timeout_seconds=.01),provider=provider)) as client:
        rid=client.post("/api/scenario",json={}).json()["release_id"]
        brief=client.post("/api/brief",json={"scenario":{},"release_id":rid}).json()
        assert brief["summary_status"] == "template"
        assert brief["evidence_map"]
        assert client.get("/api/runs/TEST-R1").status_code == 200
        assert client.get("/api/export",params={"release_id":rid}).status_code == 200


def test_release_corruption_disables_readiness(fixture_release):
    assert verify(fixture_release)["valid"]
    (fixture_release/"evidence/passages.jsonl").write_text("tampered",encoding="utf-8")
    assert not verify(fixture_release)["valid"]
    with TestClient(create_app(Settings(fixture_release,runtime_mode="bm25"))) as client:
        assert client.get("/api/healthz").status_code == 200
        assert client.get("/api/readyz").status_code == 503
        assert client.post("/api/scenario",json={}).status_code == 503


def test_csv_formula_injection_is_neutralized():
    for text in ["=HYPERLINK(\"bad\")","+command","-command","@SUM(A1:A2)","  =cmd"]:
        assert csv_safe(text).startswith("'")
    assert csv_safe("Synthetic material") == "Synthetic material"


def test_dense_only_corruption_preserves_evidence_and_reports_fallback(fixture_release):
    import numpy as np
    index=fixture_release/"index";index.mkdir()
    rows=jsonl_read(fixture_release/"evidence/passages.jsonl")
    vectors=np.zeros((len(rows),768),dtype=np.float32);vectors[:,0]=1
    np.save(index/"vectors.npy",vectors,allow_pickle=False)
    jsonl_write(index/"passages.jsonl",rows)
    json_write(index/"preset_vectors.json",{})
    from scripts.common import json_read
    release=json_read(fixture_release/"release.json")
    json_write(index/"manifest.json",{"ordered_id_digest":ordered_id_digest(rows),"vectors_sha256":sha256(index/"vectors.npy"),
                                     "passages_sha256":sha256(index/"passages.jsonl"),"formatting_version":FORMATTING_VERSION,
                                     "evidence_release_id":release["release_id"]})
    release["mode"]="cached_bm25"
    release["files"].update({p.relative_to(fixture_release).as_posix():sha256(p) for p in index.iterdir()})
    json_write(fixture_release/"release.json",release)
    assert verify(fixture_release)["valid"]
    (index/"vectors.npy").write_bytes(b"corrupted dense-only asset")
    assert not verify(fixture_release)["valid"]
    assert verify(fixture_release,allow_dense_failure=True)["valid"]
    with TestClient(create_app(Settings(fixture_release,runtime_mode="cached_bm25"))) as client:
        ready=client.get("/api/readyz").json()
        assert ready["ready"] and not ready["retrieval"]["dense_index"]
        assert client.post("/api/scenario",json={}).status_code == 200
        assert client.post("/api/search",json={"query":"flame"}).json()["retrieval_mode"] == "bm25"
