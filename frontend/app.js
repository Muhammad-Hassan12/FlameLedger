"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const e = escapeHTML;
const names = {oxygen_pct:"Oxygen",oxygen_basis:"Oxygen basis",pressure_kpa:"Absolute pressure",g_level:"Gravity",gravity_regime:"Gravity regime",gravity_method:"Gravity method",flow_cm_s:"Airflow",flow_direction:"Flow direction",protocol:"Protocol",material:"Material",geometry:"Sample geometry",fuel_class:"Fuel class"};
const units = {oxygen_pct:"% O₂",pressure_kpa:"kPa",g_level:"g",flow_cm_s:"cm/s"};
const labels = {match:"Condition match",analog:"Analog",insufficient_conditions:"Incomplete"};
const state = {presets:[],allRuns:new Map(),comparisonIds:[],response:null,payload:null,lane:"all",cell:null,scenarioSeq:0,briefSeq:0,scenarioAbort:null,briefAbort:null,trigger:null};
const pretty = value => value === null || value === undefined || value === "" ? "Not reported" : typeof value === "object" ? Object.entries(value).map(([key,val]) => `${key}: ${pretty(val)}`).join("; ") : String(value).replaceAll("_"," ");
const number = value => value === null || value === undefined ? null : Number(value).toLocaleString("en-US",{maximumFractionDigits:2});
const safeURL = value => { try {const parsed = new URL(value,location.origin);return parsed.protocol === "https:" || (parsed.origin === location.origin && parsed.pathname.startsWith("/api/sources/")) ? parsed.href : "#";} catch {return "#";} };
const locatorText = locator => !locator ? "Document context" : [locator.page ? `PDF p. ${locator.page}` : "",locator.table ? (/^table\b/i.test(locator.table) ? locator.table : `Table ${locator.table}`) : "",locator.row ? `row ${locator.row}` : "",locator.label || ""].filter(Boolean).join(" · ");

async function api(path, options = {}) {
  const response = await fetch(path,{...options,headers:{"Accept":"application/json",...(options.body ? {"Content-Type":"application/json"} : {}),...options.headers}});
  if (!response.ok) {
    let body;try {body = await response.json();} catch {body = null;}
    const message = body?.detail?.message || body?.detail?.errors?.map(x=>x.message).join("; ") || `The request could not be completed (${response.status}).`;
    const error = new Error(message);error.status = response.status;throw error;
  }
  return response.json();
}
function errorBanner(message) {$("#global-error span").textContent = message;$("#global-error").hidden = false;}
function clearError() {$("#global-error").hidden = true;}
function applyCatalog(catalog) {
  state.allRuns=new Map((catalog.run_options || []).map(run=>[run.id,run]));
  for(const [id,values] of [["#material",catalog.materials],["#endpoint",catalog.endpoints],["#regime-filter",catalog.gravity_regimes]]) {
    const control=$(id),previous=control.value,first=control.options[0].outerHTML;
    control.innerHTML=first+values.map(value=>`<option value="${e(value)}">${e(pretty(value))}</option>`).join("");
    control.value=values.includes(previous) ? previous : control.options[0].value;
  }
}
function readNumber(id) {return $(id).value.trim() === "" ? null : Number($(id).value);}
function readScenario() {
  return {preset_id:$("#preset").value === "custom" ? null : $("#preset").value,oxygen_pct:readNumber("#oxygen"),pressure_kpa:readNumber("#pressure"),g_level:readNumber("#gravity"),flow_cm_s:readNumber("#airflow"),flow_direction:$("#direction").value || null,lane:state.lane,material:$("#material").value,endpoint:$("#endpoint").value || null,gravity_regime:$("#regime-filter").value || null,question:$("#question").value.trim(),limit:100};
}
function setPreset(id) {
  const preset = state.presets.find(item=>item.id === id);
  if (!preset) {$("#preset-description").textContent="Custom cabin conditions";$("#preset-assumptions").textContent="User-specified atmosphere and gravity. Blank axes are unspecified. Values are research search inputs.";$("#preset-source").hidden=true;$("#scene-label").textContent="CUSTOM";return;}
  for (const [field,input] of [["oxygen_pct","#oxygen"],["pressure_kpa","#pressure"],["g_level","#gravity"],["flow_cm_s","#airflow"]]) $(input).value = preset[field] === null ? "" : (field === "pressure_kpa" ? Number(preset[field].toFixed(2)) : preset[field]);
  $("#direction").value="";
  $("#preset-description").textContent=preset.label;
  $("#preset-assumptions").textContent=preset.approximation;
  $("#preset-source").href=safeURL(preset.citation.url);$("#preset-source").hidden=false;
  $("#scene-label").textContent=id === "lunar" ? "LUNAR" : "ORBITAL";
  animateScene();
}
function animateScene() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.hidden) return;
  const scene=$("#chamber-scene");scene.classList.remove("animate");requestAnimationFrame(()=>scene.classList.add("animate"));
}
function getVisibleRuns() {
  const runs=state.response?.runs || [];
  return state.cell ? runs.filter(run=>state.cell.run_ids.includes(run.physical_run_id)) : runs;
}
function fieldValue(phase,field) {
  if (phase?.[field] !== null && phase?.[field] !== undefined) return number(phase[field]);
  return field === "g_level" ? (phase?.gravity_regime === "microgravity" ? "µg" : phase?.gravity_regime === "lunar" ? "Lunar" : null) : null;
}
function cardHTML(run,index) {
  const phase=run.phases.find(item=>item.key === run.phase_key) || run.phases[0];
  const pin=state.response.pinned_examples.find(item=>item.id === run.id);
  const fields=[["oxygen_pct","Oxygen"],["pressure_kpa","Pressure"],["g_level","Gravity"],["flow_cm_s","Airflow"]];
  return `<article class="run-card" data-run="${e(run.id)}">${pin ? `<p class="pinned-label">PINNED / ${e(pin.label)}</p>` : ""}<div class="run-card-header"><div class="run-ident"><span class="run-number">${String(index+1).padStart(2,"0")}</span><h3>${e(run.as_run_id || run.id)}</h3></div><span class="applicability ${e(run.applicability)}">${e(labels[run.applicability])}</span></div><p class="run-context"><span class="lane-dot ${e(run.lane)}"></span> ${e(run.investigation.family)}<span class="dot-separator">/</span>${e(run.material)}${run.evidence_type === "aggregate_observation" ? " · aggregate observation" : ""}</p><dl class="condition-strip">${fields.map(([field,label])=>{const value=fieldValue(phase,field);return `<div><dt>${label}</dt><dd>${value === null ? '<span class="missing-value">Not reported</span>' : `${e(value)}<small>${(value === "µg" || value === "Lunar") ? "regime" : e(units[field])}</small>`}</dd></div>`;}).join("")}</dl><div class="run-card-footer"><button class="source-button" type="button" data-source="${e(run.id)}"><span aria-hidden="true">▤</span> Source &amp; record <span aria-hidden="true">↗</span></button><div class="run-actions"><span class="small muted mono">${run.review_status === "human_verified" ? "REVIEWED" : "REVIEW PENDING"}</span><button class="compare-add" type="button" data-compare="${e(run.id)}" aria-label="Compare ${e(run.as_run_id || run.id)}">+ Compare</button></div></div><details class="why-details"><summary>Why this ${run.applicability === "match" ? "matches" : run.applicability === "analog" ? "is an analog" : "is incomplete"}</summary><ul>${run.reasons.map(reason=>`<li>${e(reason)}</li>`).join("")}${run.qualifier ? `<li>${e(run.qualifier)}</li>` : ""}</ul><div class="delta-list">${run.fields.map(field=>`<span class="${e(field.state)}">${e(names[field.field])}: ${field.delta === null ? "missing" : `${field.delta > 0 ? "+" : ""}${e(number(field.delta))} ${e(field.unit)}`}</span>`).join("")}</div></details></article>`;
}
function renderRuns() {
  const runs=getVisibleRuns();
  $("#run-list").innerHTML=runs.length ? runs.map(cardHTML).join("") : `<div class="loading-placeholder"><p>${state.cell ? "No matching run in the indexed evidence" : "No evidence under these filters"}</p><p class="small muted">Inspect the source scope or clear a filter to see other analogs.</p></div>`;
  $("#run-list").setAttribute("aria-busy","false");
  $("#run-list").classList.remove("show-all");
  $("#result-status").innerHTML = runs.length > 5 ? `${runs.length} records in the active scope. <button class="text-button" id="show-all" type="button">Show all records</button>` : `${runs.length} ${runs.length === 1 ? "record" : "records"} in the active scope.`;
}
function renderScenario() {
  const data=state.response;
  state.cell=null;$("#clear-cell").hidden=true;
  $("#ledger-summary").innerHTML=`<span><strong>${data.total} indexed records</strong> · active scope</span><span class="summary-states"><span>${data.counts.match} matches</span><span>${data.counts.analog} analogs</span><span>${data.counts.insufficient_conditions} incomplete</span></span>`;
  $("#active-scenario").innerHTML=[...["oxygen_pct","pressure_kpa","g_level"].filter(field=>data.scenario[field] !== null).map(field=>`<span>${e(number(data.scenario[field]))} ${e(units[field])}</span>`),`<span>${data.scenario.flow_cm_s === null ? "Flow unspecified" : `${e(number(data.scenario.flow_cm_s))} cm/s`}</span>`].join("");
  $("#review-notice").hidden=!data.runs.some(run=>run.review_status !== "human_verified");
  $("#release-status").textContent=`${data.total} records in scope · source-linked release`;
  $("#release-id").textContent=data.release_id;
  $("#export").disabled=false;
  $("#research-gaps").innerHTML=[...data.gaps,"Unspecified conditions remain unknown. Indexed coverage is limited to this release and the selected filters."].map(gap=>`<p>${e(gap)}</p>`).join("");
  renderRuns();renderCoverage();
}
async function loadScenario() {
  if (!$("#scenario-form").reportValidity()) return;
  const sequence=++state.scenarioSeq;
  state.scenarioAbort?.abort();state.briefAbort?.abort();
  state.scenarioAbort=new AbortController();
  const payload=readScenario();
  clearError();$("#run-scenario").disabled=true;$("#run-scenario").firstChild.textContent="Finding evidence ";$("#run-list").setAttribute("aria-busy","true");
  $("#result-status").textContent="Updating the evidence; previous values remain visible until the new response arrives.";
  try {
    const data=await api("/api/scenario",{method:"POST",body:JSON.stringify(payload),signal:state.scenarioAbort.signal});
    if (sequence !== state.scenarioSeq) return;
    if(state.response && state.response.release_id !== data.release_id) {
      const catalog=await api("/api/catalog",{signal:state.scenarioAbort.signal});
      if(sequence !== state.scenarioSeq)return;
      if(catalog.release_id !== data.release_id)throw new Error("The evidence release changed during loading. Retry to refresh the ledger.");
      applyCatalog(catalog);
    }
    state.response=data;state.payload=payload;
    for (const run of data.runs) state.allRuns.set(run.id,run);
    renderScenario();initializeCompare();loadBriefing();
    const params=new URLSearchParams();params.set("preset",payload.preset_id || "custom");params.set("lane",payload.lane);
    if (!payload.preset_id) for (const key of ["oxygen_pct","pressure_kpa","g_level","flow_cm_s"]) if(payload[key] !== null)params.set(key,String(payload[key]));
    history.replaceState(null,"",`${location.pathname}?${params}`);animateScene();
  } catch (error) {if (error.name !== "AbortError") {errorBanner(error.message);$("#result-status").textContent="The update failed. Previously loaded evidence remains available.";}}
  finally {if(sequence === state.scenarioSeq){$("#run-scenario").disabled=false;$("#run-scenario").firstChild.textContent="Find relevant evidence ";$("#run-list").setAttribute("aria-busy","false");}}
}
function initializeCompare() {
  const left=$("#compare-left"),right=$("#compare-right"),previous=[left.value,right.value];
  const options=[...state.allRuns.values()].map(run=>`<option value="${e(run.id)}">${e(run.as_run_id || run.id)} · ${e(run.material)}</option>`).join("");
  left.innerHTML=options;right.innerHTML=options;
  const pins=state.response.pinned_examples;
  left.value=[previous[0],pins.find(item=>item.label === "Atmosphere analog")?.id,[...state.allRuns.keys()][0]].find(id=>state.allRuns.has(id)) || "";
  right.value=[previous[1],pins.find(item=>item.label === "Gravity analog")?.id,[...state.allRuns.keys()][1],left.value].find(id=>state.allRuns.has(id)) || "";
  loadComparison();
}
let compareSeq=0;
async function loadComparison() {
  const seq=++compareSeq;
  $("#comparison").classList.add("updating");
  $("#export-comparison").disabled=true;
  const ids=[$("#compare-left").value,$("#compare-right").value];
  if (ids.some(id=>!id)) {$("#comparison").innerHTML='<p class="muted">No indexed records are available for comparison.</p>';$("#comparison").classList.remove("updating");return;}
  try {
    const data=await api("/api/compare",{method:"POST",body:JSON.stringify({run_ids:ids})});
    if(seq !== compareSeq)return;
    for(const [i,pinID] of [[0,"#left-pin"],[1,"#right-pin"]]) {const pin=state.response?.pinned_examples.find(item=>item.id === ids[i]);$(pinID).textContent=pin ? pin.label.toUpperCase() : "SELECTED RECORD";}
    const visible=new Set(["oxygen_pct","pressure_kpa","g_level","gravity_regime","gravity_method","material","flow_cm_s","flow_direction"]);
    const facts=data.facts.filter(fact=>visible.has(fact.field));
    const table=`<table class="compare-table"><caption class="sr-only">Aligned conditions for ${e(ids[0])} and ${e(ids[1])}</caption><thead class="sr-only"><tr><th scope="col">Field</th><th scope="col">${e(ids[0])}</th><th scope="col">${e(ids[1])}</th></tr></thead><tbody>${facts.map(fact=>`<tr><th scope="row">${e(names[fact.field])}</th>${[fact.left,fact.right].map(value=>`<td>${e(typeof value === "number" ? number(value) : pretty(value))}${value !== null && value !== undefined && units[fact.field] ? ` ${e(units[fact.field])}` : ""}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    const observations=`<div class="compare-observations">${data.runs.map((run,i)=>`<div><h4>${e(run.as_run_id || run.id)} / REPORTED OBSERVATION</h4>${run.measurements.length ? run.measurements.slice(0,2).map(item=>`<p>${e(item.outcome || `${number(item.value)} ${item.unit || ""}`)}</p>`).join("") : '<p>No outcome indexed for this record.</p>'}${data.phase_notes?.[i] ? `<p class="small">${e(data.phase_notes[i])}</p>` : ""}</div>`).join("")}</div>`;
    const limit=`<div class="compare-limit"><span class="limit-symbol" aria-hidden="true">◇</span><div><p><strong>${data.comparability === "limited" ? "Limited comparison" : "Compatible reported endpoint"}</strong> · ${data.delta === null ? "A numerical outcome difference is not supported for these setups." : `Reported difference: ${e(number(data.delta))} ${e(data.delta_unit)}`}</p><details><summary>Inspect comparison limits (${data.confounders.length})</summary><ul>${data.confounders.map(item=>`<li>${e(item)}</li>`).join("")}</ul><p>${e(data.note)}</p></details></div></div>`;
    $("#comparison").innerHTML=table+observations+limit+`<div class="compare-sources">${data.runs.map(run=>`<button class="source-button" type="button" data-source="${e(run.id)}">${e(run.as_run_id || run.id)} source <span aria-hidden="true">↗</span></button>`).join("")}</div>`;
    state.comparisonIds=data.run_ids.slice();
    $("#export-comparison").disabled=false;
  } catch(error){if(seq === compareSeq)$("#comparison").textContent=error.message;}
  finally {if(seq === compareSeq)$("#comparison").classList.remove("updating");}
}
function activeCoverage(){return $("#preview-coverage").checked ? state.response.preview_coverage : state.response.coverage;}
function renderCoverage() {
  const coverage=activeCoverage();if(!coverage)return;
  const cells=coverage.cells;const scenario=state.response.scenario;
  const oxygenValues=[20,35,...cells.map(c=>c.oxygen_min),Math.floor((scenario.oxygen_pct ?? 34)/5)*5];
  const pressureValues=[50,100,...cells.map(c=>c.pressure_min),Math.floor((scenario.pressure_kpa ?? 56)/10)*10];
  const omin=Math.max(0,Math.min(...oxygenValues)-5),omax=Math.min(95,Math.max(...oxygenValues)+5);
  const pmin=Math.max(0,Math.min(...pressureValues)-10),pmax=Math.max(...pressureValues)+10;
  const os=Array.from({length:(omax-omin)/5+1},(_,i)=>omax-i*5),ps=Array.from({length:(pmax-pmin)/10+1},(_,i)=>pmin+i*10);
  const map=new Map(cells.map(cell=>[`${cell.oxygen_min}/${cell.pressure_min}`,cell]));
  $("#coverage-grid").innerHTML=`<table class="coverage-matrix"><caption>O₂ % ↓ &nbsp; ABSOLUTE PRESSURE (kPa) →</caption><thead><tr><th scope="col"><span class="sr-only">Oxygen</span></th>${ps.map(p=>`<th scope="col">${p}–${p+10}</th>`).join("")}</tr></thead><tbody>${os.map(o=>`<tr><th scope="row">${o}–${o+5}%</th>${ps.map(p=>{const cell=map.get(`${o}/${p}`);const count=cell?.count || 0;const active=state.cell?.oxygen_min === o && state.cell?.pressure_min === p;const scenarioCell=scenario.oxygen_pct >= o && scenario.oxygen_pct < o+5 && scenario.pressure_kpa >= p && scenario.pressure_kpa < p+10;return `<td><button type="button" class="${count ? "populated" : ""} ${scenarioCell ? "scenario-cell" : ""}" data-cell-o="${o}" data-cell-p="${p}" aria-pressed="${active}" title="${o}–${o+5}% O₂, ${p}–${p+10} kPa: ${count} unique runs" aria-label="${o} to ${o+5} percent oxygen, ${p} to ${p+10} kilopascals: ${count} unique runs">${count || "·"}</button></td>`;}).join("")}</tr>`).join("")}</tbody></table>`;
  $("#coverage-scope").textContent=`${coverage.unique_runs} ${coverage.review_scope === "human_verified" ? "independently verified" : "source-checked preview"} physical runs. Active lane: ${state.payload.lane}; material: ${state.payload.material}; endpoint: ${state.payload.endpoint || "all"}; gravity filter: ${state.payload.gravity_regime || "all"}. Aggregate observations and repeated phases do not inflate counts. Amber corner: scenario bin.`;
  if(!state.cell)$("#coverage-detail").textContent=coverage.unique_runs ? "Select a cell to inspect its source-linked runs." : $("#preview-coverage").checked ? "No matching run in the indexed evidence under these filters." : "Independent human verification is pending. Enable the source-checked preview to inspect candidate coverage.";
}
function selectCell(o,p) {
  const coverage=activeCoverage();state.cell=coverage.cells.find(cell=>cell.oxygen_min === o && cell.pressure_min === p) || {oxygen_min:o,pressure_min:p,run_ids:[],count:0};
  $("#coverage-detail").innerHTML=`<strong>${o}–${o+5}% O₂ / ${p}–${p+10} kPa</strong><br>${state.cell.count ? `${state.cell.count} unique physical ${state.cell.count === 1 ? "run" : "runs"}. The evidence ledger now shows this cell.` : "No matching run in the indexed evidence. Clear the selection to inspect available analogs."}`;
  $("#clear-cell").hidden=false;renderCoverage();renderRuns();
}
async function openSource(id,trigger) {
  const dialog=$("#source-drawer");state.trigger=trigger || document.activeElement;
  $("#source-content").innerHTML='<h2 id="source-title">Loading source record…</h2>';
  if(!dialog.open)dialog.showModal();
  try {
    const run=await api(`/api/runs/${encodeURIComponent(id)}`);const citation=run.citation;
    const links=(card)=>`<div class="source-links"><a class="button secondary compact" target="_blank" rel="noopener noreferrer" href="${e(safeURL(card.url))}">Official source ↗</a>${card.file_url ? `<a class="button secondary compact" target="_blank" rel="noopener noreferrer" href="${e(safeURL(card.file_url)+(card.locator?.page ? `#page=${card.locator.page}` : ""))}">Open PDF${card.locator?.page ? ` · p. ${card.locator.page}` : ""} ↗</a>` : ""}</div>`;
    $("#source-content").innerHTML=`<h2 id="source-title">${e(run.as_run_id || run.id)}</h2><p class="drawer-subtitle">${e(run.investigation.family)} / ${e(run.material)}</p><div class="source-section"><h3>Evidence &amp; review</h3><p class="review-label">${run.review_status === "human_verified" ? "Independently human verified" : "Source-checked during development · independent human verification pending"}</p><p>${e(run.qualifier || "")}</p><p>${e(pretty(run.evidence_type))} · ${e(run.investigation.platform)}<br>${e(run.geometry)}</p></div><div class="source-section"><h3>Original source</h3><p>${e(citation.title)}</p><p class="mono">${e(locatorText(run.locator))}</p>${links(citation)}<p class="small">Retrieved ${e(citation.retrieved_at)} · ${e(citation.import_status)}</p><p>${e(citation.package_relationship || "")}</p><p class="checksum">SHA-256 ${e(citation.sha256 || "Not available")}</p></div>${run.phases.map(phase=>`<div class="source-section"><h3>Condition phase / ${e(phase.key)}</h3><p>${e(phase.qualifier || "")}</p><table><tbody>${[...Object.keys(names).filter(key=>key in phase),"original"].map(key=>`<tr><th scope="row">${e(names[key] || "Original values / units")}</th><td>${e(pretty(phase[key]))}${phase[key] !== null && units[key] ? ` ${e(units[key])}` : ""}</td></tr>`).join("")}</tbody></table><p class="small">${e(locatorText(phase.locator))}</p></div>`).join("")}<div class="source-section"><h3>Reported observations</h3>${run.measurements.length ? run.measurements.map(m=>`<div class="source-excerpt"><p><strong>${e(pretty(m.endpoint))}</strong></p><p>${e(m.outcome || "")}${m.value !== null && m.value !== undefined ? ` · ${e(m.value)} ${e(m.unit)}` : ""}</p><p>${e(m.definition)}</p><p class="small">${e(locatorText(m.locator))} · ${e(pretty(m.verification_status))}</p>${m.source_id !== run.source_id ? links(m.citation) : ""}</div>`).join("") : '<p>No outcome is indexed for this record.</p>'}</div>${run.passages.length ? `<div class="source-section"><h3>Source-linked passages</h3>${run.passages.map(p=>`<div class="source-excerpt"><p>${e(p.text)}</p><p class="small">${e(locatorText(p.locator))}</p></div>`).join("")}</div>` : ""}`;
    $("#source-close").focus();
  } catch(error){$("#source-content").innerHTML=`<h2 id="source-title">Source unavailable</h2><p>${e(error.message)}</p>`;}
}
async function loadBriefing() {
  if(!state.response)return;
  const seq=++state.briefSeq;state.briefAbort?.abort();state.briefAbort=new AbortController();
  $("#briefing-mode").textContent="PREPARING BRIEF";$("#refresh-brief").disabled=true;
  try {
    const data=await api("/api/brief",{method:"POST",body:JSON.stringify({scenario:state.payload,selected_ids:[],release_id:state.response.release_id}),signal:state.briefAbort.signal});
    if(seq !== state.briefSeq)return;
    $("#briefing-mode").textContent=data.summary_status === "template" ? "EVIDENCE ONLY" : data.summary_status === "cached_approved" ? "CACHED AI · REVIEWED" : data.summary_status.startsWith("cached") ? "CACHED AI · UNREVIEWED" : "AI SUMMARY · UNREVIEWED";
    $("#retrieval-mode").textContent=pretty(data.retrieval_mode);
    $("#briefing").innerHTML=data.sections.map(section=>`<div class="briefing-lane"><h3><span class="lane-dot ${e(section.lane)}"></span>${e(section.lane)}</h3>${section.claims.length ? section.claims.map(claim=>`<p>${e(claim.text)}</p><p class="claim-limit">${e(claim.limit)}</p><div class="claim-citations">${claim.evidence_ids.map(id=>{const item=data.evidence_map[id];return item.run_id ? `<button type="button" data-source="${e(item.run_id)}">[${e(item.title)}] ↗</button>` : `<a href="${e(safeURL(item.citation.url))}" target="_blank" rel="noopener noreferrer">[${e(item.citation.ntrs_id || id)}] ↗</a>`;}).join("")}</div>`).join("") : '<p class="muted">No evidence in this packet under the active scope.</p>'}</div>`).join("")+(data.review_note ? `<p class="small amber-text">${e(data.review_note)}</p>` : "");
    $("#research-gaps").innerHTML=[...state.response.gaps,...data.gaps,"Unspecified conditions remain unknown. Coverage is limited to the active evidence release and filters."].map(gap=>`<p>${e(gap)}</p>`).join("");
  } catch(error){if(error.name !== "AbortError") {$("#briefing-mode").textContent="BRIEFING UNAVAILABLE";$("#briefing").innerHTML='<p class="muted">The briefing could not be loaded. Source-linked facts, comparisons and CSV export remain available.</p>';}}
  finally {if(seq === state.briefSeq)$("#refresh-brief").disabled=false;}
}
async function downloadCSV(scope="ledger") {
  if(!state.response)return;
  // The comparison selects records across the catalog, independently of ledger filters.
  const filters=scope === "comparison" ? {...state.payload,lane:"all",material:"all",endpoint:null,gravity_regime:null} : state.payload;
  const params=new URLSearchParams({release_id:state.response.release_id,filters:JSON.stringify(filters)});
  if(scope === "comparison") {if(state.comparisonIds.length !== 2)return;params.set("ids",state.comparisonIds.join(","));}
  else if(state.cell) {const ids=getVisibleRuns().map(run=>run.id);if(!ids.length){errorBanner("This cell has no evidence to export. Clear the cell selection to export the active scope.");return;}params.set("ids",ids.join(","));}
  const exportButton=scope === "comparison" ? $("#export-comparison") : $("#export");exportButton.disabled=true;
  try {const response=await fetch(`/api/export?${params}`);if(!response.ok)throw new Error(response.status === 409 ? "The evidence release changed. Refresh the ledger before exporting." : "Evidence export failed.");const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download=scope === "comparison" ? "flameledger-comparison.csv" : "flameledger-evidence.csv";anchor.click();setTimeout(()=>URL.revokeObjectURL(url),5000);} catch(error){errorBanner(error.message);} finally{exportButton.disabled=scope === "comparison" && $("#comparison").classList.contains("updating");}
}
async function searchLiterature(event) {
  event.preventDefault();const query=$("#literature-query").value.trim();if(!query)return;
  $("#search-results").textContent="Searching source-linked passages…";
  try {const data=await api("/api/search",{method:"POST",body:JSON.stringify({query,lane:state.lane,limit:6})});$("#search-results").innerHTML=`<p class="small mono muted">${e(pretty(data.retrieval_mode))}</p>`+(data.results.length ? data.results.map(p=>`<article class="literature-result"><p class="context-tag">${p.kind === "document_context" ? "DOCUMENT CONTEXT · NOT A RUN" : "SOURCE-LINKED PASSAGE"}</p><a target="_blank" rel="noopener noreferrer" href="${e(safeURL(p.citation.url))}">${e(p.title)} ↗</a><p>${e(p.text.slice(0,600))}${p.text.length > 600 ? "…" : ""}</p><p class="small mono">${e(locatorText(p.locator))}</p></article>`).join("") : '<p class="muted">No scored passage matches. Try a different question.</p>');}catch(error){$("#search-results").textContent=error.message;}
}
async function start() {
  try {
    const [presetData,catalog]=await Promise.all([api("/api/presets"),api("/api/catalog")]);state.presets=presetData.presets;
    applyCatalog(catalog);
    const params=new URLSearchParams(location.search);const preset=params.get("preset");if(["lunar","iss","custom"].includes(preset))$("#preset").value=preset;
    if(["all","prevention","detection","suppression"].includes(params.get("lane")))state.lane=params.get("lane");
    $$("[data-lane]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.lane === state.lane)));
    setPreset($("#preset").value);
    if($("#preset").value === "custom")for(const [key,id] of [["oxygen_pct","#oxygen"],["pressure_kpa","#pressure"],["g_level","#gravity"],["flow_cm_s","#airflow"]])$(id).value=params.get(key) || "";
    await loadScenario();
  }catch(error){errorBanner(`The evidence release is unavailable. ${error.message}`);$("#release-status").textContent="Evidence release unavailable";$("#run-list").setAttribute("aria-busy","false");$("#run-list").innerHTML='<div class="loading-placeholder"><p>No validated release is loaded.</p><p class="small muted">Build or restore the evidence release, then retry.</p></div>';}
}
$("#scenario-form").addEventListener("submit",event=>{event.preventDefault();loadScenario();});
$("#preset").addEventListener("change",()=>{setPreset($("#preset").value);loadScenario();});
for(const id of ["#oxygen","#pressure","#gravity","#airflow","#direction"])$(id).addEventListener("input",()=>{$("#preset").value="custom";setPreset("custom");});
$("#export").addEventListener("click",()=>downloadCSV());$("#export-comparison").addEventListener("click",()=>downloadCSV("comparison"));$("#retry").addEventListener("click",()=>state.response ? loadScenario() : start());
$("#compare-left").addEventListener("change",loadComparison);$("#compare-right").addEventListener("change",loadComparison);
$("#preview-coverage").addEventListener("change",()=>{state.cell=null;$("#clear-cell").hidden=true;renderCoverage();renderRuns();});
$("#clear-cell").addEventListener("click",()=>{state.cell=null;$("#clear-cell").hidden=true;renderCoverage();renderRuns();});
$("#source-close").addEventListener("click",()=>$("#source-drawer").close());
$("#source-drawer").addEventListener("close",()=>{state.trigger?.focus();});
for(const id of ["#methods-open","#disclosure-open"])$(id).addEventListener("click",()=>$("#methods-dialog").showModal());
$("#methods-close").addEventListener("click",()=>$("#methods-dialog").close());
$("#refresh-brief").addEventListener("click",loadBriefing);$("#search-form").addEventListener("submit",searchLiterature);
$("#chamber-art").addEventListener("error",()=>$("#chamber-scene").classList.add("art-failed"));
document.addEventListener("visibilitychange",()=>{if(document.hidden)$("#chamber-scene").classList.remove("animate");});
if("IntersectionObserver" in window)new IntersectionObserver(entries=>{if(!entries[0].isIntersecting)$("#chamber-scene").classList.remove("animate");}).observe($("#chamber-scene"));
document.addEventListener("click",event=>{
  const source=event.target.closest("[data-source]");if(source){openSource(source.dataset.source,source);return;}
  const compare=event.target.closest("[data-compare]");if(compare){$("#compare-right").value=compare.dataset.compare;loadComparison();$("#compare").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",block:"start"});return;}
  const lane=event.target.closest("[data-lane]");if(lane){state.lane=lane.dataset.lane;$$("[data-lane]").forEach(button=>button.setAttribute("aria-pressed",String(button === lane)));loadScenario();return;}
  const cell=event.target.closest("[data-cell-o]");if(cell){selectCell(Number(cell.dataset.cellO),Number(cell.dataset.cellP));return;}
  if(event.target.closest("#show-all")){$("#run-list").classList.add("show-all");$("#show-all").hidden=true;}
});
start();
