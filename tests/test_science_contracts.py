import copy

import pytest

from backend.contracts import ScenarioInput, normalize_scenario
from backend.ranking import compare_runs, coverage, evaluate_phase, rank_runs
from scripts.build_evidence import validate


def scenario(**kwargs):
    return normalize_scenario(ScenarioInput(preset_id=None,oxygen_pct=34,pressure_kpa=56.5,g_level=.16,flow_cm_s=20,**kwargs),{})


def test_one_matching_field_does_not_fill_three_unknowns(synthetic_data):
    phase=synthetic_data[0]["runs"][2]["phases"][0]
    result=evaluate_phase(phase,scenario())
    assert result["applicability"] == "insufficient_conditions"
    assert set(result["missing_fields"]) == {"pressure_kpa","g_level","flow_cm_s"}


def test_coherent_phase_cannot_borrow_values(synthetic_data):
    run=copy.deepcopy(synthetic_data[0]["runs"][0])
    run["phases"][0]["pressure_kpa"]=None
    other=copy.deepcopy(run["phases"][0]);other.update(key="other",oxygen_pct=None,pressure_kpa=56.5)
    run["phases"].append(other)
    assert rank_runs([run],scenario())[0]["applicability"] == "insufficient_conditions"


def test_same_unit_incompatible_endpoints_never_subtracted(synthetic_data):
    left,right=synthetic_data[0]["runs"][:2]
    result=compare_runs(left,right)
    assert result["delta"] is None
    assert result["comparability"] == "limited"


def test_only_shared_endpoint_protocol_and_setup_allow_delta(synthetic_data):
    left=synthetic_data[0]["runs"][0]
    right=copy.deepcopy(left);right["id"]="TEST-R4";right["measurements"][0]["value"]=12
    assert compare_runs(left,right)["delta"] == 2
    right["phases"][0]["gravity_method"]="Different fixture method"
    assert compare_runs(left,right)["delta"] is None


def test_duplicate_phases_and_publications_do_not_inflate_coverage(synthetic_data):
    run=copy.deepcopy(synthetic_data[0]["runs"][0]);run["review_status"]="human_verified"
    run["phases"].append({**run["phases"][0],"key":"repeat"})
    publication=copy.deepcopy(run);publication["id"]="TEST-PUBLICATION"
    result=coverage([run,publication],scenario())
    assert result["unique_runs"] == 1
    assert result["cells"][0]["count"] == 1


def test_source_checked_rows_require_explicit_preview(synthetic_data):
    runs=synthetic_data[0]["runs"]
    assert coverage(runs,scenario())["unique_runs"] == 0
    assert coverage(runs,scenario(),include_pending_review=True)["unique_runs"] == 2
    runs[0]["evidence_type"]="aggregate_observation"
    assert coverage(runs,scenario(),include_pending_review=True)["unique_runs"] == 1


def test_known_length_units_convert_without_crossing_endpoint_definitions(synthetic_data):
    left=synthetic_data[0]["runs"][0]
    right=copy.deepcopy(left);right["id"]="TEST-OTHER"
    right["measurements"][0].update(value=120.0,unit="mm")
    result=compare_runs(left,right)
    assert result["delta"] == 2
    assert result["delta_unit"] == "cm"
    right["measurements"][0]["definition"]="Different observable, still a length"
    assert compare_runs(left,right)["delta"] is None


def test_unspecified_gas_basis_is_missing_evidence(synthetic_data):
    phase=synthetic_data[0]["runs"][0]["phases"][0];phase["oxygen_basis"]="unspecified"
    assert "oxygen_pct" in evaluate_phase(phase,scenario())["missing_fields"]


def test_incompatible_endpoint_and_lane_are_filtered(synthetic_data):
    assert not rank_runs(synthetic_data[0]["runs"],scenario(lane="detection",endpoint="flame_length"))


def test_data_builder_rejects_orphans_duplicates_and_unsupported_checked_values(synthetic_data):
    data,sources=synthetic_data
    validate(data,sources)
    broken=copy.deepcopy(data);broken["runs"].append(copy.deepcopy(data["runs"][0]))
    with pytest.raises(ValueError,match="Duplicate run"):validate(broken,sources)
    broken=copy.deepcopy(data);broken["runs"][0]["source_id"]="UNKNOWN"
    with pytest.raises(ValueError,match="Orphaned"):validate(broken,sources)
    broken=copy.deepcopy(data);broken["runs"][0]["measurements"][0].update(value=None,outcome=None)
    with pytest.raises(ValueError,match="Unsupported measurement"):validate(broken,sources)


@pytest.mark.parametrize("value",[float("nan"),float("inf"),-1,101])
def test_nonphysical_oxygen_rejected(value):
    with pytest.raises(ValueError):ScenarioInput(oxygen_pct=value)
