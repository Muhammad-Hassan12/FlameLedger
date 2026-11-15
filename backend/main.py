from __future__ import annotations

import csv
import io
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from backend.briefing import BriefingService
from backend.config import Settings
from backend.contracts import BriefInput, CompareInput, ScenarioInput, SearchInput, TOLERANCES, normalize_scenario, presets
from backend.ranking import compare_runs, coverage, rank_runs
from backend.retrieval import Retriever
from backend.store import EvidenceStore
from scripts.common import ROOT, json_read
from scripts.verify_release import verify

log = logging.getLogger("flameledger")


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def scenario_response(store, scenario):
    ranked = rank_runs(store.runs, scenario)
    states = {state: sum(r["applicability"] == state for r in ranked) for state in ("match", "analog", "insufficient_conditions")}
    active = ranked[:scenario["limit"]]
    return {"scenario": scenario, "runs": [store.enrich_run(r) for r in active], "total": len(ranked), "counts": states,
            "coverage": coverage(store.runs, scenario), "preview_coverage": coverage(store.runs, scenario, include_pending_review=True),
            "release_id": store.release_id, "data_mode": "verified", "tolerances": TOLERANCES,
            "gaps": [f"No complete condition match among {len(ranked)} indexed records under the active filters."] if not states["match"] else [],
            "pinned_examples": [{"id": r["id"], "label": label} for needle, label in (("VI-2", "Atmosphere analog"), ("LUCI", "Gravity analog"))
                                for r in store.runs if (needle == "VI-2" and r.get("as_run_id") in {"VI-2", "Saffire VI-2"}) or (needle == "LUCI" and "LUCI" in r["id"].upper())][:3]}


def create_app(settings=None, provider=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = None
        app.state.retriever = None
        app.state.ready_error = "release_not_built"
        try:
            report = verify(settings.release_dir, allow_dense_failure=True)
            if not report["valid"]:
                raise ValueError("Required release integrity check failed")
            store = EvidenceStore(settings.release_dir)
            mode = "bm25" if report["dense_errors"] else settings.runtime_mode
            retriever = Retriever(settings.release_dir, store.passages, mode, settings.torch_threads, settings.encode_timeout_seconds)
            app.state.store, app.state.retriever = store, retriever
            app.state.briefing = BriefingService(store, retriever, settings, provider=provider)
            app.state.ready_error = None
        except (OSError, ValueError, KeyError) as error:
            log.error("Release unavailable (%s). Run the documented build commands.", type(error).__name__)
        yield
        if app.state.retriever:
            app.state.retriever.close()

    app = FastAPI(title="FlameLedger", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    limits = defaultdict(deque)

    @app.middleware("http")
    async def request_guard(request, call_next):
        if request.url.path.startswith("/api"):
            try:
                if int(request.headers.get("content-length", "0")) > 20_000:
                    return JSONResponse({"detail": {"code": "request_too_large"}}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": {"code": "invalid_content_length"}}, status_code=400)
            if request.method == "POST":
                body = await request.body()
                if len(body) > 20_000:
                    return JSONResponse({"detail": {"code": "request_too_large"}}, status_code=413)
                key = request.client.host if request.client else "local"
                now = time.monotonic()
                bucket = limits[key]
                while bucket and now - bucket[0] > 60:
                    bucket.popleft()
                if len(bucket) >= 90:
                    return JSONResponse({"detail": {"code": "rate_limit", "message": "Please wait before sending more requests."}}, status_code=429)
                bucket.append(now)
                if len(limits) > 2048:
                    for old in list(limits)[:1024]:
                        if not limits[old] or now - limits[old][-1] > 60:
                            del limits[old]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if "/assets/" in request.url.path else "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"detail": {"code": "validation_error", "errors": [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]}}, status_code=422)

    def store():
        if app.state.store is None:
            raise HTTPException(503, {"code": "release_unavailable", "message": "The evidence release is not ready. See the build instructions."})
        return app.state.store

    @app.get("/api/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/api/readyz")
    def ready():
        current = app.state.store
        retrieval = app.state.retriever
        value = {"ready": current is not None, "release_id": current.release_id if current else None,
                 "retrieval": {"configured_mode": settings.runtime_mode, "dense_index": bool(retrieval and retrieval.vectors is not None),
                               "live_encoder": bool(retrieval and retrieval.encoder is not None)},
                 "briefing": "gemini_configured" if settings.gemini_api_key and settings.gemini_model else "evidence_template"}
        return JSONResponse(value, status_code=200 if current else 503)

    @app.get("/api/presets")
    def get_presets():
        current = store()
        return {"presets": presets(current.sources), "release_id": current.release_id}

    @app.get("/api/catalog")
    def catalog():
        current = store()
        return {"materials": sorted({r["material"] for r in current.runs}),
                "run_options": [{k:r.get(k) for k in ("id","as_run_id","material","lane")} for r in current.runs],
                "endpoints": sorted({m["endpoint"] for r in current.runs for m in r["measurements"]}),
                "gravity_regimes": sorted({p["gravity_regime"] for r in current.runs for p in r["phases"] if p.get("gravity_regime")}),
                "investigations": list(current.investigations.values()), "review_states": {state: sum(r["review_status"] == state for r in current.runs) for state in ("source_checked", "human_verified", "pending")},
                "tolerances": TOLERANCES, "release_id": current.release_id}

    @app.post("/api/scenario")
    def scenario(request: ScenarioInput):
        current = store()
        return scenario_response(current, normalize_scenario(request, current.sources))

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        current = store()
        if run_id not in current.by_id:
            raise HTTPException(404, {"code": "unknown_run"})
        item = current.by_id[run_id]
        return {**current.enrich_run(item), "passages": [p for p in current.passages if run_id in p.get("run_ids", [])], "release_id": current.release_id}

    @app.get("/api/sources/{source_id}/file")
    def source_file(source_id: str):
        current = store()
        if source_id not in current.sources:
            raise HTTPException(404, {"code": "unknown_source"})
        file = current.release / "evidence/source_files" / f"{source_id}.pdf"
        if not file.is_file():
            raise HTTPException(404, {"code": "source_file_not_bundled"})
        return FileResponse(file, media_type="application/pdf")

    @app.post("/api/compare")
    def compare(request: CompareInput):
        current = store()
        if any(r not in current.by_id for r in request.run_ids):
            raise HTTPException(404, {"code": "unknown_run"})
        try:
            result = compare_runs(*(current.by_id[r] for r in request.run_ids), endpoint=request.endpoint, phase_keys=request.phase_keys)
        except ValueError as error:
            raise HTTPException(422, {"code": "invalid_phase", "message": str(error)}) from None
        return {**result, "runs": [current.enrich_run(current.by_id[r]) for r in request.run_ids], "release_id": current.release_id}

    @app.post("/api/search")
    async def search(request: SearchInput):
        current = store()
        result = await app.state.retriever.search(request.query, request.lane, request.limit)
        result["results"] = [{**p, "citation": current.source_card(p["source_id"], p.get("locator"))} for p in result["results"]]
        return {**result, "release_id": current.release_id}

    @app.post("/api/brief")
    async def brief(request: BriefInput):
        current = store()
        if request.release_id != current.release_id:
            raise HTTPException(409, {"code": "release_changed", "message": "Refresh the evidence before generating a briefing."})
        normalized = normalize_scenario(request.scenario, current.sources)
        ranked = rank_runs(current.runs, normalized)
        if set(request.selected_ids) - {r["id"] for r in ranked}:
            raise HTTPException(422, {"code": "selection_outside_scope"})
        return await app.state.briefing.generate(normalized, ranked, request.selected_ids)

    @app.get("/api/export")
    def export(release_id: str = Query(max_length=100), filters: str = Query(default="{}", max_length=5000), ids: str = Query(default="", max_length=4000)):
        current = store()
        if release_id != current.release_id:
            raise HTTPException(409, {"code": "release_changed", "message": "Refresh evidence; the displayed release has changed."})
        try:
            import json
            normalized = normalize_scenario(ScenarioInput.model_validate(json.loads(filters)), current.sources)
        except (ValueError, TypeError):
            raise HTTPException(422, {"code": "invalid_filters"}) from None
        ranked = rank_runs(current.runs, normalized)
        selected = set(ids.split(",")) - {""}
        if len(selected) > 100 or selected - {r["id"] for r in ranked}:
            raise HTTPException(422, {"code": "selection_outside_scope"})
        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        columns = ["release_id", "run_id", "as_run_id", "physical_run_id", "lane", "material", "geometry", "evidence_type", "review_status", "phase", "oxygen_pct", "oxygen_basis", "pressure_kpa", "g_level", "gravity_regime", "gravity_method", "flow_cm_s", "flow_direction", "condition_protocol", "original_conditions", "condition_qualifier", "run_qualifier", "applicability", "endpoint", "value", "unit", "definition", "outcome", "measurement_protocol", "verification_status", "source_id", "source_sha256", "source_url", "locator"]
        writer.writerow(columns)
        for r in ranked:
            if selected and r["id"] not in selected:
                continue
            for phase in r["phases"] or [{}]:
                if normalized["gravity_regime"] and phase.get("gravity_regime") != normalized["gravity_regime"]:
                    continue
                measurements = [m for m in r["measurements"] if m.get("phase_key") in {None, phase.get("key")} and (not normalized["endpoint"] or m["endpoint"] == normalized["endpoint"])] or [{}]
                for m in measurements:
                    sid = m.get("source_id", phase.get("source_id", r["source_id"]))
                    values = {**r, **phase, **m, "release_id": current.release_id, "run_id": r["id"], "phase": phase.get("key"), "source_url": current.sources[sid]["url"], "locator": json.dumps(m.get("locator", phase.get("locator", r.get("locator"))), ensure_ascii=False)}
                    values.update(condition_protocol=phase.get("protocol"),measurement_protocol=m.get("protocol"),
                                  original_conditions=json.dumps(phase.get("original",{}),ensure_ascii=False),
                                  condition_qualifier=phase.get("qualifier"),run_qualifier=r.get("qualifier"),
                                  source_id=sid,source_sha256=current.sources[sid].get("sha256"))
                    writer.writerow([csv_safe(values.get(c)) for c in columns])
        return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="flameledger-evidence.csv"'})

    frontend = settings.release_dir / "frontend"
    if not frontend.is_dir():
        frontend = ROOT / "frontend"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="dashboard")
    return app


app = create_app()
