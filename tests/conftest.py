"""Synthetic fixtures live only under tests and are never NASA evidence."""
import copy
import json
from pathlib import Path

import pytest

from scripts.assemble_release import assemble
from scripts.build_evidence import build
from scripts.common import ROOT, json_write


@pytest.fixture
def synthetic_data():
    source={"id":"SRC-TEST","title":"Synthetic test source (not NASA)","url":"https://example.org/synthetic",
            "sha256":"0"*64,"retrieved_at":"2026-11-15","license_status":"Synthetic fixture",
            "import_status":"test_fixture","challenge_resource":False}
    locator={"page":1,"label":"Synthetic test row"}
    phase={"key":"burn","oxygen_pct":34.0,"oxygen_basis":"mole","pressure_kpa":56.5,"g_level":0.16,
           "gravity_regime":"lunar","gravity_method":"synthetic fixture","flow_cm_s":20.0,
           "flow_direction":"concurrent","protocol":"fixture protocol","original":{"oxygen":"34 mol%","pressure":"56.5 kPa"},
           "source_id":source["id"],"locator":locator}
    measurement={"id":"TEST-M1","endpoint":"flame_length","definition":"Visible axial length", "value":10.0,
                 "unit":"cm","outcome":"Synthetic fixture observation", "phase_key":"burn","verification_status":"source_checked",
                 "source_id":source["id"],"locator":locator,"protocol":"fixture protocol"}
    run={"id":"TEST-R1","investigation_id":"TEST-INV","as_run_id":"Synthetic run A", "evidence_type":"run",
         "physical_run_id":"TEST-R1","lane":"prevention","material":"Synthetic fabric","fuel_class":"solid",
         "geometry":"Synthetic sheet","review_status":"source_checked","source_id":source["id"],"locator":locator,
         "qualifier":"Synthetic fixture, not NASA evidence", "phases":[phase],"measurements":[measurement]}
    second=copy.deepcopy(run);second.update(id="TEST-R2",physical_run_id="TEST-R2",as_run_id="Synthetic run B",lane="suppression")
    second["measurements"][0].update(id="TEST-M2",endpoint="extinction_diameter",definition="Diameter at extinction")
    third=copy.deepcopy(run);third.update(id="TEST-R3",physical_run_id="TEST-R3",as_run_id="Synthetic run C",lane="detection")
    third["phases"][0].update(pressure_kpa=None,g_level=None,gravity_regime="unknown",flow_cm_s=None)
    third["measurements"][0].update(id="TEST-M3",endpoint="detector_response",definition="Synthetic detector response",value=None,unit=None)
    data={"schema_version":1,"investigations":[{"id":"TEST-INV","family":"Synthetic fixture","platform":"Test only","hardware":"Fixture","fuel_class":"solid","scope":"Test only"}],
          "runs":[run,second,third],"passages":[{"id":"TEST-P1","source_id":source["id"],"title":"Synthetic flame experiment","text":"Synthetic combustion flame length in lunar gravity.","kind":"page_passage","lane":"prevention","run_ids":[run["id"]],"locator":locator,"review_status":"source_checked"}]}
    return data,[source]


@pytest.fixture
def fixture_release(tmp_path,synthetic_data):
    data,sources=synthetic_data
    manifest=tmp_path/"sources.json";curated=tmp_path/"curated.json"
    json_write(manifest,{"sources":sources});json_write(curated,data)
    evidence=tmp_path/"evidence"
    build(manifest,curated,evidence,run_dir=None)
    frontend=tmp_path/"ui";frontend.mkdir();(frontend/"index.html").write_text("Synthetic test UI",encoding="utf-8")
    release=tmp_path/"release"
    assemble(evidence,frontend,release,mode="bm25")
    return release
