"""Public request contracts. All displayed scientific values originate in the evidence store."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Lane = Literal["all", "prevention", "detection", "suppression"]


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    preset_id: Literal["lunar", "iss"] | None = "lunar"
    oxygen_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_kpa: float | None = Field(default=None, gt=0, le=300)
    g_level: float | None = Field(default=None, ge=0, le=2)
    flow_cm_s: float | None = Field(default=None, ge=0, le=200)
    flow_direction: Literal["concurrent", "opposed", "quiescent", "unspecified"] | None = None
    lane: Lane = "all"
    material: str = Field(default="all", min_length=1, max_length=100)
    endpoint: str | None = Field(default=None, max_length=100)
    gravity_regime: str | None = Field(default=None, max_length=60)
    question: str = Field(default="Which indexed experiments inform this cabin environment?", max_length=1000)
    limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def require_custom_condition(self):
        if self.preset_id is None and all(v is None for v in (self.oxygen_pct, self.pressure_kpa, self.g_level)):
            raise ValueError("Specify at least one custom atmosphere or gravity condition.")
        return self


class CompareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_ids: list[str] = Field(min_length=2, max_length=2)
    endpoint: str | None = Field(default=None, max_length=100)
    phase_keys: list[str] | None = Field(default=None, min_length=2, max_length=2)


class BriefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: ScenarioInput
    selected_ids: list[str] = Field(default_factory=list, max_length=10)
    release_id: str = Field(min_length=1, max_length=100)


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    lane: Lane = "all"
    limit: int = Field(default=10, ge=1, le=20)


TOLERANCES = {"oxygen_pct": 2.0, "pressure_kpa": 5.0, "g_level": 0.03, "flow_cm_s": 5.0}
UNITS = {"oxygen_pct": "percentage points", "pressure_kpa": "kPa", "g_level": "g", "flow_cm_s": "cm/s"}


def presets(sources: dict) -> list[dict]:
    def citation(ntrs_id, fallback):
        source = next((s for s in sources.values() if s.get("ntrs_id") == ntrs_id or s.get("ntrs_id") == int(ntrs_id)), None)
        return {"source_id": source["id"] if source else None,
                "url": source["url"] if source else fallback,
                "title": source["title"] if source else "Source not ingested",
                "locator": "Exploration atmosphere design case" if ntrs_id == "20240015307" else "Test Matrix I, cabin air"}
    return [
        {"id": "lunar", "name": "Lunar exploration", "version": "1", "oxygen_pct": 34.0,
         "pressure_kpa": 56.5370098, "g_level": 0.16, "flow_cm_s": None, "flow_direction": None,
         "gravity_regime": "lunar", "label": "Illustrative NASA exploration case",
         "approximation": "Planned 34% O₂, 8.2 psia converted to 56.54 kPa; gravity approximated as 0.16 g. Airflow unspecified. This is scenario context, not an executed FM² test.",
         "citation": citation("20240015307", "https://ntrs.nasa.gov/citations/20240015307")},
        {"id": "iss", "name": "ISS-like cabin", "version": "1", "oxygen_pct": 21.0,
         "pressure_kpa": 101.3, "g_level": 0.0, "flow_cm_s": None, "flow_direction": None,
         "gravity_regime": "microgravity", "label": "Nominal cabin-air baseline",
         "approximation": "About 21% O₂ and one atmosphere (101.3 kPa). Microgravity is mapped to 0 g for search only. Airflow unspecified; this preset does not describe every ISS experiment.",
         "citation": citation("20150023456", "https://ntrs.nasa.gov/citations/20150023456")},
    ]


def normalize_scenario(request: ScenarioInput, sources: dict) -> dict:
    values = request.model_dump()
    preset = next((p for p in presets(sources) if p["id"] == request.preset_id), None)
    if preset:
        # Explicit null flow remains unspecified. Only scenario axes inherit preset defaults.
        for key in ("oxygen_pct", "pressure_kpa", "g_level"):
            if values[key] is None:
                values[key] = preset[key]
        values["preset"] = preset
    else:
        values["preset"] = None
    values["question"] = " ".join(values["question"].split())
    return values
