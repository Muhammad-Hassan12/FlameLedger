"""Deterministic applicability, phase-coherent comparison, and unique-run coverage."""
from __future__ import annotations

import math
from collections import defaultdict

from backend.contracts import TOLERANCES, UNITS

CHECKED = {"source_checked", "human_verified"}
STATE_ORDER = {"match": 0, "analog": 1, "insufficient_conditions": 2}
MEASUREMENT_UNITS = {"mm": (0.1, "cm"), "cm": (1.0, "cm"), "m": (100.0, "cm"),
                     "mm/s": (0.1, "cm/s"), "cm/s": (1.0, "cm/s"), "m/s": (100.0, "cm/s"),
                     "ms": (0.001, "s"), "s": (1.0, "s")}


def converted_measurement(measurement):
    factor, unit = MEASUREMENT_UNITS.get(measurement.get("unit"), (1.0, measurement.get("unit")))
    value = measurement.get("value")
    return (value * factor if isinstance(value, (int, float)) else None), unit


def phase_value(phase: dict, axis: str):
    value = phase.get(axis)
    if axis == "oxygen_pct" and phase.get("oxygen_basis") not in {"mole", "volume"}:
        return None
    if axis == "g_level" and value is None and phase.get("gravity_regime") == "microgravity":
        return 0.0  # A documented regime, explicitly disclosed in Methods and each field reason.
    return value


def material_tier(run: dict, material: str):
    if material.lower() == "all":
        return 0
    if material.casefold() == run["material"].casefold():
        return 0
    if material.casefold() == run.get("fuel_class", "").casefold():
        return 1
    return 2


def filtered_runs(runs: list[dict], scenario: dict) -> list[dict]:
    result = []
    for run in runs:
        if scenario.get("lane", "all") != "all" and run["lane"] != scenario["lane"]:
            continue
        if scenario.get("endpoint") and not any(m["endpoint"] == scenario["endpoint"] for m in run["measurements"]):
            continue
        if scenario.get("gravity_regime") and not any(p.get("gravity_regime") == scenario["gravity_regime"] for p in run["phases"]):
            continue
        result.append(run)
    return result


def evaluate_phase(phase: dict, scenario: dict) -> dict:
    fields, missing, different = [], [], []
    distance = 0.0
    for axis, tolerance in TOLERANCES.items():
        target = scenario.get(axis)
        if target is None:
            continue
        value = phase_value(phase, axis)
        delta = None if value is None else value - target
        state = "missing" if value is None else "within_tolerance" if abs(delta) <= tolerance + 1e-9 else "different"
        mapped = axis == "g_level" and phase.get(axis) is None and value is not None
        fields.append({"field": axis, "scenario": target, "evidence": value, "delta": delta,
                       "unit": UNITS[axis], "tolerance": tolerance, "state": state,
                       "note": "Documented microgravity regime mapped to 0 g for search; residual acceleration was not supplied." if mapped else None})
        if value is None:
            missing.append(axis)
        else:
            distance += abs(delta) / tolerance
            if state == "different":
                different.append(axis)
    direction = scenario.get("flow_direction")
    if direction and direction != "unspecified":
        if not phase.get("flow_direction") or phase["flow_direction"] == "unspecified":
            missing.append("flow_direction")
        elif direction != phase["flow_direction"]:
            different.append("flow_direction")
    state = "insufficient_conditions" if missing or not fields else "analog" if different else "match"
    reasons = []
    if missing:
        reasons.append("Not reported or not convertible: " + ", ".join(missing) + ".")
    if different:
        reasons.append("Outside illustrative search tolerances or different protocol: " + ", ".join(different) + ".")
    if state == "match":
        reasons.append("All specified condition axes are within the illustrative search tolerances in this phase.")
    return {"applicability": state, "phase_key": phase["key"], "fields": fields,
            "missing_fields": missing, "different_fields": different, "distance": round(distance, 6), "reasons": reasons}


def rank_runs(runs: list[dict], scenario: dict) -> list[dict]:
    ranked = []
    for run in filtered_runs(runs, scenario):
        assessments = [evaluate_phase(p, scenario) for p in run["phases"]
                       if not scenario.get("gravity_regime") or p.get("gravity_regime") == scenario["gravity_regime"]]
        if not assessments:
            assessments = [{"applicability": "insufficient_conditions", "phase_key": None, "fields": [],
                            "missing_fields": ["condition_phase"], "different_fields": [], "distance": 0,
                            "reasons": ["No coherent condition phase is indexed."]}]
        assessment = min(assessments, key=lambda a: (STATE_ORDER[a["applicability"]], a["distance"], a["phase_key"] or ""))
        tier = material_tier(run, scenario.get("material", "all"))
        reasons = assessment["reasons"].copy()
        if tier == 2:
            reasons.append("Different material; shown as general context.")
        if run["review_status"] != "human_verified":
            reasons.append("Source located during development; independent human verification is pending.")
        ranked.append({**run, **assessment, "reasons": reasons, "material_tier": tier})
    return sorted(ranked, key=lambda r: (r["material_tier"], STATE_ORDER[r["applicability"]],
                                         r["distance"] if r["applicability"] != "insufficient_conditions" else math.inf, r["id"]))


def coverage(runs: list[dict], scenario: dict, *, include_pending_review=False) -> dict:
    cells = defaultdict(set)
    excluded = {"aggregate_or_unidentified": 0, "pending_review": 0, "missing_conditions": 0}
    for run in filtered_runs(runs, scenario):
        if material_tier(run, scenario.get("material", "all")) == 2:
            continue
        if not run.get("physical_run_id") or run["evidence_type"] == "aggregate_observation":
            excluded["aggregate_or_unidentified"] += 1
            continue
        if run["review_status"] != "human_verified" and not include_pending_review:
            excluded["pending_review"] += 1
            continue
        if run["review_status"] not in CHECKED:
            continue
        has_pair = False
        for phase in run["phases"]:
            if scenario.get("gravity_regime") and phase.get("gravity_regime") != scenario["gravity_regime"]:
                continue
            oxygen, pressure = phase_value(phase, "oxygen_pct"), phase_value(phase, "pressure_kpa")
            if oxygen is None or pressure is None:
                continue
            has_pair = True
            obin, pbin = min(95, int(oxygen // 5) * 5), int(pressure // 10) * 10
            cells[(obin, pbin)].add(run["physical_run_id"])
        if not has_pair:
            excluded["missing_conditions"] += 1
    items = [{"oxygen_min": o, "oxygen_max": o + 5, "pressure_min": p, "pressure_max": p + 10,
              "count": len(ids), "run_ids": sorted(ids)} for (o, p), ids in sorted(cells.items())]
    return {"cells": items, "oxygen_bin_pct": 5, "pressure_bin_kpa": 10, "unique_runs": len(set().union(*cells.values())) if cells else 0,
            "filters": {k: scenario.get(k) for k in ("lane", "material", "endpoint", "gravity_regime")},
            "excluded": excluded, "review_scope": "human_verified" if not include_pending_review else "source_checked_preview",
            "empty_label": "No matching run in the indexed evidence",
            "note": "Coverage counts independently verified physical runs. Source-checked rows awaiting human review are shown separately in the evidence preview. Bins include their lower bound and exclude their upper bound, except 100% O₂ is included in the final bin."}


def compare_runs(left: dict, right: dict, endpoint=None, phase_keys=None) -> dict:
    selected = []
    for i, run in enumerate((left, right)):
        key = phase_keys[i] if phase_keys else (run["phases"][0]["key"] if run["phases"] else None)
        phase = next((p for p in run["phases"] if p["key"] == key), None)
        if key and phase is None:
            raise ValueError("Unknown phase for selected run")
        selected.append(phase or {})
    lp, rp = selected
    aligned = [{"field": k, "left": lp.get(k), "right": rp.get(k)} for k in
               ("oxygen_pct", "oxygen_basis", "pressure_kpa", "g_level", "gravity_regime", "gravity_method", "flow_cm_s", "flow_direction", "protocol")]
    aligned += [{"field": k, "left": left.get(k), "right": right.get(k)} for k in ("material", "geometry", "fuel_class")]
    confounders = [f"{r['field']} differs or is unreported." for r in aligned if r["left"] is None or r["right"] is None or r["left"] != r["right"]]
    if lp.get("key") != rp.get("key"):
        confounders.append("Condition phase keys differ; equivalent temporal phases have not been established.")
    lm = [m for m in left["measurements"] if (endpoint is None or m["endpoint"] == endpoint) and m.get("phase_key") == lp.get("key")]
    rm = [m for m in right["measurements"] if (endpoint is None or m["endpoint"] == endpoint) and m.get("phase_key") == rp.get("key")]
    pair = next(((a, b) for a in lm for b in rm if a["endpoint"] == b["endpoint"] and a["definition"] == b["definition"]
                 and converted_measurement(a)[1] == converted_measurement(b)[1]
                 and a.get("protocol") and a.get("protocol") == b.get("protocol")), None)
    comparable = bool(pair and not confounders and all(m.get("verification_status") in CHECKED for m in pair)
                      and all(isinstance(m.get("value"), (float, int)) for m in pair))
    if not pair:
        confounders.append("A shared endpoint, definition, phase and converted unit could not be established.")
    return {"run_ids": [left["id"], right["id"]], "phase_keys": [lp.get("key"), rp.get("key")],
            "phase_notes": [lp.get("qualifier"), rp.get("qualifier")],
            "facts": aligned, "observations": [lm, rm], "comparability": "comparable" if comparable else "limited",
            "confounders": confounders, "delta": (converted_measurement(pair[1])[0] - converted_measurement(pair[0])[0]) if comparable else None,
            "delta_unit": converted_measurement(pair[0])[1] if comparable else None,
            "note": "Side-by-side reported facts. Differences in setup prevent causal conclusions."}
