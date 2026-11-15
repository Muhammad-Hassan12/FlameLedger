"""Reproducible, explicitly source-checked development curation (not human review)."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
TODAY = "2026-11-15"
sources, runs, passages = [], [], []

def source(sid, title, url, ntrs=None, psi=None, challenge=False, rights="Public distribution; portions may be copyright protected; original source rights apply"):
    candidates = list((ROOT / "data/raw" / str(ntrs)).glob("*.pdf")) if ntrs else []
    local = candidates[0] if candidates else None
    row={"id":sid,"title":title,"url":url,"ntrs_id":ntrs,"psi_id":psi,"challenge_resource":challenge,
         "retrieved_at":TODAY,"license_status":rights,"local_path":local.relative_to(ROOT).as_posix() if local else None,
         "sha256":hashlib.sha256(local.read_bytes()).hexdigest() if local else None,
         "import_status":"report_downloaded_source_checked" if local else "official_web_source_checked_download_pending",
         "package_relationship":"Selected public report from implementation plan. Separate from supplied training archive; October 28 PSI source package not supplied."}
    sources.append(row)
    return sid

def bind_local(sid, relative):
    path=ROOT/relative
    if path.is_file():
        row=next(s for s in sources if s["id"]==sid)
        row.update(local_path=relative,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),import_status="official_html_downloaded_source_checked")

S15=source("SRC-SAFFIRE-I-V","Fire Safety Implications of Preliminary Results from Saffire IV and V Experiments on Large Scale Spacecraft Fires","https://ntrs.nasa.gov/citations/20210011521","20210011521", "PSI-98",True)
S6=source("SRC-SAFFIRE-VI","Preliminary Results from the Saffire VI Experiment","https://ntrs.nasa.gov/citations/20240007488","20240007488")
SL=source("SRC-LUCI","Lunar Combustion Investigation: Flammability Results from a Rotating Sounding Rocket","https://ntrs.nasa.gov/citations/20250010653","20250010653")
SM=source("SRC-FM2","Flammability of Materials on the Moon","https://ntrs.nasa.gov/citations/20240015307","20240015307")
SB=source("SRC-BASS-II","Burning and Suppression of Solids-II Summary Report","https://ntrs.nasa.gov/citations/20210011385","20210011385")
SF=source("SRC-FLEX","Detailed Results from the Flame Extinguishment Experiment (FLEX) March 2009 to December 2011","https://ntrs.nasa.gov/citations/20150023456","20150023456", "PSI-69",True, "Public Use Permitted (NTRS record)")
SG=source("SRC-LUNAR-LAB","Solid Fuel Ignition Testing for Lunar Applications, Theory and Experimental Results","https://ntrs.nasa.gov/citations/20250002114","20250002114")
SN=source("SRC-NIST-SAME","Evaluation of Spacecraft Smoke Detector Performance in the Low-Gravity Environment","https://www.nist.gov/publications/evaluation-spacecraft-smoke-detector-performance-low-gravity-environment",psi="PSI-101",challenge=True,rights="NIST public publication metadata; publisher DOI10.1016/j.firesaf.2018.04.004; article rights apply")
SNEWS=source("SRC-NIST-SAME-NEWS","NIST/NASA Study Shows One Detector Doesn't Fit All for Smoke in Spacecraft","https://www.nist.gov/news-events/news/2018/05/nistnasa-study-shows-one-detector-doesnt-fit-all-smoke-spacecraft",rights="NIST public information; source reuse policy applies")
bind_local(SN,"data/raw/nist-detectors/source.html")
bind_local(SNEWS,"data/raw/nist-detectors-news/source.html")
for pid,title in [("98","Saffire I"),("101","Smoke Aerosol Measurement Experiment-Reflight"),("69","Flame Extinguishment Experiment")]:
    source("SRC-PSI-"+pid,title+" NASA PSI investigation", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-"+pid,psi="PSI-"+pid,challenge=True)
    sources[-1]["import_status"]="catalog_link_only_raw_dataset_not_imported"
    sources[-1]["package_relationship"]="Challenge-listed investigation identified by the plan; links related report/publication. No PSI raw files in supplied bundle; this is a catalog pointer, not a raw-data import."

investigations=[
 {"id":"SAFFIRE","family":"Saffire","platform":"Orbiting Cygnus spacecraft","hardware":"Saffire Flow Unit","fuel_class":"solid","scope":"Large-scale solid-fuel flame spread in orbital microgravity"},
 {"id":"LUCI","family":"LUCI","platform":"Blue Origin New Shepard rotating sounding rocket","hardware":"Centrifugal lunar-gravity combustion chamber","fuel_class":"solid","scope":"Simulated lunar gravity; air at normal pressure; Coriolis effects apply"},
 {"id":"BASS-II","family":"BASS-II","platform":"International Space Station","hardware":"Microgravity Science Glovebox small flow duct","fuel_class":"solid","scope":"Small solid-fuel flames; oxygen dilution and ventilation control"},
 {"id":"SAME-R","family":"SAME / SAME-R","platform":"International Space Station","hardware":"Smoke generation and aerosol measurement apparatus","fuel_class":"detector","scope":"Material-dependent detector response; aggregate observations are not individually identified runs"},
 {"id":"FLEX","family":"FLEX","platform":"International Space Station","hardware":"MDCA in the Combustion Integrated Rack","fuel_class":"droplet","scope":"Droplet burning and extinction; source matrices distinguish nominal and actual conditions"},
 {"id":"LUNAR-LAB","family":"Lunar gravity laboratory","platform":"NASA Glenn Zero Gravity Facility centrifuge and White Sands terrestrial facility","hardware":"Drop-tower partial-gravity centrifuge","fuel_class":"solid","scope":"Reduced-pressure lunar-gravity ignition/extinction; protocols remain distinct"},
]

def loc(page=None,table=None,row=None,label=None):
    return {k:v for k,v in {"page":page,"table":table,"row":row,"label":label or (f"PDF page {page}" if page else "Publication abstract")}.items() if v is not None}

def phase(sid,locator,oxygen=None,pressure=None,g=None,regime="microgravity",flow=None,direction=None,basis="mole",method="orbital freefall",key="initial",original=None,qualifier="As-reported initial conditions; nominal gravity mapped by documented regime."):
    return {"key":key,"oxygen_pct":oxygen,"oxygen_basis":basis,"pressure_kpa":pressure,"g_level":g,"gravity_regime":regime,"gravity_method":method,"flow_cm_s":flow,"flow_direction":direction,"protocol":"forced-flow solid-fuel burning" if flow is not None else "See source; no forced-flow speed assigned", "original":original or {"oxygen":{"value":oxygen,"unit":"mol%" if basis=="mole" else "vol%" if basis=="volume" else "% basis not specified"},"pressure":{"value":pressure,"unit":"kPa absolute"},"flow":{"value":flow,"unit":"cm/s"}},"qualifier":qualifier,"source_id":sid,"locator":locator}

def add(rid,inv,asrun,material,geometry,sid,locator,phases,measurements=None,lane="prevention",etype="run",physical=None,qualifier="Source checked during development; independent human verification pending."):
    runs.append({"id":rid,"investigation_id":inv,"as_run_id":asrun,"evidence_type":etype,"physical_run_id":physical or (rid if etype=="run" else None),"lane":lane,"material":material,"fuel_class":"detector" if inv=="SAME-R" else "droplet" if inv=="FLEX" else "solid","geometry":geometry,"review_status":"source_checked","source_id":sid,"locator":locator,"qualifier":qualifier,"phases":phases,"measurements":measurements or [],"passage_ids":[]})
    return runs[-1]

def measurement(rid,sid,locator,endpoint,definition,value=None,unit=None,outcome="",phase_key="initial",protocol="source-defined"):
    return {"id":rid+":"+endpoint,"endpoint":endpoint,"definition":definition,"value":value,"unit":unit,"outcome":outcome,"phase_key":phase_key,"verification_status":"source_checked","source_id":sid,"locator":locator,"protocol":protocol}

def passage(pid,sid,title,text,locator,lane="prevention",run_ids=None,kind="page_passage"):
    passages.append({"id":pid,"source_id":sid,"title":title,"text":text,"kind":kind,"lane":lane,"run_ids":run_ids or [],"locator":locator,"review_status":"source_checked"})
    for run in runs:
        if run["id"] in (run_ids or []):run["passage_ids"].append(pid)

# Table 2 physical runs. Oxygen basis follows Table1/microgravity atmosphere context;
# first four Table2 oxygen values carry unspecified basis rather than infer mol/volume.
for sample,o2,press,flow,steady,maximum,width,length,duct,material in [
 ("I-1",21,100,20,4,6.2,41,94,46,"SIBAL fabric"),
 ("II-5",21,100,20,4,4,5,30,46,"SIBAL fabric"),
 ("II-6",21,100,25,5,5,5,30,46,"SIBAL fabric"),
 ("III-1",21,100,25,5,8.2,41,94,46,"SIBAL fabric"),
 ("IV-1",22,100,20,8.5,11,41,50,30,"SIBAL fabric"),
 ("V-2",26.2,70.7,20,10,14,41,50,30,"Cotton jersey")]:
    rid="SAFFIRE-"+sample; locator=loc(8,"Table 2",sample,"Thin-sample test conditions and flame size")
    p=phase(S15,locator,o2,press,None,flow=flow,direction="concurrent",basis="mole" if sample in {"IV-1","V-2"} else "unspecified",original={"oxygen_pct":o2,"pressure_kpa":press,"flow_cm_s":flow,"duct_height_cm":duct,"sample_width_cm":width,"sample_length_cm":length})
    add(rid,"SAFFIRE",sample,material,f"{width} cm wide x {length} cm long; duct height {duct} cm",S15,locator,[p],[measurement(rid,S15,locator,"steady_flame_size","Reported steady-state flame size for thin samples (Table 2)",steady,"cm"),measurement(rid,S15,locator,"maximum_flame_size","Reported maximum flame size for thin samples (Table 2)",maximum,"cm")])
    passage("PASS-"+rid,S15,"Saffire thin-fuel test "+sample,f"{sample}: {material}; oxygen {o2}%, pressure {press} kPa; concurrent flow {flow} cm/s. Steady flame size {steady} cm; maximum {maximum} cm. Duct height {duct} cm.",locator,run_ids=[rid],kind="table")

for sample,o2,press,material,length,thick in [("VI-2",31.0,54.1,"SIBAL fabric",50,None),("VI-3",30.3,54.6,"PMMA",18,1.0),("VI-4",28.8,55.2,"PMMA",18,0.5)]:
    rid="SAFFIRE-"+sample; locator=loc(11,"Test Matrix (as executed)",sample,"Executed Saffire VI matrix")
    phases=[phase(S6,locator,o2,press,None,flow=20,direction="concurrent")]
    measurements=[]
    if sample=="VI-3":
        # Time-varying phases preserve flow changes, without mixing initial gases with later phases.
        phases += [phase(S6,loc(17,label="Flow schedule at 1120 s"),flow=5,direction="concurrent",key="reduced_flow",qualifier="Flow reduced at 1120 s; initial gas values are not copied to this phase."),phase(S6,loc(17,label="Flow schedule at 1420 s"),flow=0,direction="concurrent",key="flow_off",qualifier="Duct flow terminated at 1420 s; subsequent gases not transcribed.")]
    # Oxygen-consumption totals transcribed only after alignment of the table headers.
    add(rid,"SAFFIRE",sample,material,f"41 cm wide x {length} cm long"+(f" x {thick} cm thick; "+("two-sided" if thick==1 else "one-sided") if thick else "; thin fabric"),S6,locator,phases,measurements,qualifier="Preliminary Saffire VI report. Executed matrix, not proposed design conditions. Independent human verification pending.")
    passage("PASS-"+rid,S6,"Saffire VI executed test "+sample,f"{sample} used {material}, {o2} mol% oxygen, {press} kPa and 20 cm/s concurrent flow in orbit. These preliminary executed conditions differ from lunar gravity.",locator,run_ids=[rid],kind="table")

# LUCI is nominal lunar centrifugal gravity, not a lunar-surface experiment. Preserve
# normal-pressure textual context without converting an unspecified pressure to101.3.
for material,sample,geometry,endpt,definition,value,page in [
 ("SIBAL fabric","LUCI fabric","5 cm wide x 30 cm long fabric sheet","flame_base_spread_rate","Linear fit to SIBAL flame-base position",0.92,19),
 ("PMMA","LUCI rod","4 mm diameter acrylic rod","flame_tip_spread_rate","Approximately linear PMMA flame-tip spread",1.5,21)]:
    rid="LUCI-FABRIC" if sample=="LUCI fabric" else "LUCI-PMMA"
    locator=loc(page,label="LUCI measured flame propagation")
    phases=[phase(SL,loc(12,label="Experimental overview; air at normal pressure"),None,None,None,"lunar",method="centrifugal acceleration on rotating New Shepard; nominal lunar regime",basis="unspecified",qualifier="Air at normal pressure; oxygen depleted during burn. Numeric oxygen/pressure/g not assigned from qualitative overview.")]
    add(rid,"LUCI",sample,material,geometry,SL,locator,phases,[measurement(rid,SL,locator,endpt,definition,value,"mm/s")],qualifier="Simulated lunar gravity, 11 RPM at 1.22 m effective radius; air at normal pressure. Coriolis effects and oxygen depletion differ from a lunar cabin. Human verification pending.")
    passage("PASS-"+rid,SL,sample+" source context",f"{sample} burned in air at normal pressure under centrifugal lunar-gravity simulation. Reported {endpt.replace('_',' ')}: {value} mm/s. Gas composition changed during burning; forced airflow is not specified.",locator,run_ids=[rid])

# Aggregate detection observations: do not count as identified physical runs.
for material,outcome in [("Kapton","The ISS photoelectric detector frequently missed the smaller particles from overheated Kapton."),("Teflon","The ISS photoelectric detector frequently missed the smaller particles from overheated Teflon."),("Cellulose / silicone / Pyrell","Larger smoke particles from cellulose, silicone and Pyrell were detected by the ISS light-scattering detector.")]:
    rid="SAME-"+("LARGE-PARTICLES" if "/" in material else material.upper())
    locator=loc(label="NIST report, material-specific detector observations, May2018")
    p=phase(SNEWS,locator,regime="microgravity",basis="unspecified",qualifier="Material-level aggregate; no individual run or environmental setpoint is assigned.")
    add(rid,"SAME-R",None,material,"Oxidative pyrolysis smoke; source aggregates multiple test conditions",SNEWS,locator,[p],[measurement(rid,SNEWS,locator,"smoke_detection_response","ISS light-scattering photoelectric detector material-dependent response",outcome=outcome)],lane="detection",etype="aggregate_observation")
    passage("PASS-"+rid,SNEWS,"Material-dependent spacecraft detector response",outcome+" This is a study-level observation, not an identifiable run; particle aging, heating and flow differed across tests.",locator,lane="detection",run_ids=[rid])

passage("PASS-FM2-PRESET",SM,"Illustrative lunar exploration atmosphere", "FM2 planned two atmospheres: 21% oxygen at 14.7 psia, and 34% oxygen at 8.2 psia. These design cases support the illustrative lunar preset; they are not completed lunar test results.",loc(1,label="FM2 environmental control design cases"))
passage("PASS-FLEX-SCOPE",SF,"FLEX droplet-extinction scope", "FLEX used the MDCA apparatus in the ISS Combustion Integrated Rack. The technical report documents 284 tests, with nominal matrix conditions separated from individual droplet outcomes. No uninspected matrix row is promoted to a run.",loc(label="NTRS publication abstract"),lane="suppression",kind="abstract")
passage("PASS-LUNAR-LAB-SCOPE",SG,"Reduced-pressure lunar-gravity test limitations", "The study compares White Sands terrestrial testing and a Glenn drop-tower centrifuge. Differences in ignition, material geometry and gas velocity limit direct endpoint comparisons. Lunar buoyant velocity remains undetermined.",loc(9,label="Cross-facility protocol differences and interpretation"))

# Appendix A's calibrated O2 columns are distinct from raw sensor readings. The
# pressure is not given per row and is deliberately left unknown. Fan controls
# and air displays are preserved without treating potentiometer values as cm/s.
for sample,asrun,sample_id,thickness,width,initial,final,raw_o2,page,outcome,schedule in [
 ("B1",7,"147",100,2,22.2,22.2,20.6,111,"Rapid ignition followed by extinction when flow was switched off; soot and a blue leading edge were noted.","Air display 5; fan display 62; flow switched off during spread"),
 ("B10",62,"173m",200,1,21.0,20.8,20.1,111,"Steady spread was examined at several flow settings; extinction occurred at fan potentiometer 0.35.","Air display 5, 4, 3, 2, 1; fan settings 1.7 (52), 1.25, 0.9, 0.6, 0.4, 0.35"),
 ("B11",61,"158m",200,2,21.0,20.7,20.1,111,"Multiple flow settings were used for steady spread; extinction occurred at potentiometer 0.35.","Air display 5, 3, 1, <1; fan settings 2.5 (59), 1.3, 0.7, 0.5, 0.35"),
 ("B12",13,"160",300,2,22.2,22.1,20.5,111,"The flame was predominantly blue, with soot noted on the underside.","Air display 2; fan display 46.5"),
 ("B13",63,"162m",400,2,21.0,20.5,20.1,111,"Steady spread was investigated at multiple flow settings, followed by extinction at potentiometer 0.35.","Air display 10, 5, 4, 3, 2, 1; fan settings 3.5 (68), 1.7, 1.25, 0.9, 0.6, 0.4, 0.35"),
 ("B14",47,"174m",200,1,15.0,None,14.1,111,"Only brief ignition was observed before the flame extinguished.","Air display 5, 3, 2, extinction; fan display not recorded")]:
    rid="BASS-II-"+sample
    locator=loc(page,"Appendix A, Table A.1",f"{sample}; as-run {asrun}; sample {sample_id}","Bhattacharjee PMMA test matrix; printed page 103")
    p=phase(SB,locator,initial,None,None,"microgravity",None,"opposed",basis="volume",original={"as_run_test_number":asrun,"test_number":sample,"sample_number":sample_id,"calibrated_initial_oxygen_vol_pct":initial,"calibrated_final_oxygen_vol_pct":final,"uncalibrated_initial_oxygen_vol_pct":raw_o2,"flow_schedule_native":schedule,"flow_restrictor":2,"igniter":"Integral"},qualifier="Calibrated initial oxygen is retained. Per-run absolute pressure and calibrated speed are not provided in this matrix row; changing fan settings are not one fixed condition.")
    p["protocol"]="Opposed spread; integral igniter; flow restrictor 2; fan schedule varies by test"
    add(rid,"BASS-II",sample,"PMMA",f"{width} cm wide x {thickness} micrometre film; sample {sample_id}",SB,locator,[p],[measurement(rid,SB,locator,"flame_observation","Test observations from the BASS-II Appendix A operator matrix",outcome=outcome,protocol=p["protocol"])],qualifier="Source matrix transcribed with original calibrated and uncalibrated oxygen kept separate. Independent human verification pending.")
    passage("PASS-"+rid,SB,"BASS-II "+sample+" operator observation",f"{sample}, as-run {asrun}: {width} cm wide PMMA film, {thickness} micrometres thick; calibrated initial oxygen {initial} vol%. "+outcome,locator,run_ids=[rid],kind="table")

rid="LUNAR-LAB-PROTOCOL"
locator=loc(7,label="Section B, NASA Glenn partial-gravity testing")
p=phase(SG,locator,None,56.5,1/6,"lunar",basis="unspecified",method="Drop-tower centrifuge, 20.4 RPM; nominal 1/6-g radial acceleration",original={"nominal_chamber_pressure":{"value":56.5,"unit":"kPa","reported_equivalent":"8.2 psia","locator":"PDF page 6"},"radial_acceleration":"1/6 g","rotation":"20.4 RPM","drop_duration":"5.2 seconds","target_oxygen":"Varied by material; no value assigned"},qualifier="Study-level protocol at the nominal lunar habitat target pressure, not an individually identified physical run. Gas velocity at the flame was not determined.")
p["protocol"]="Oxygen-enhanced ignition before drop; upward spread; buoyancy-driven flow during 5.2-second centrifugal lunar-gravity interval"
add(rid,"LUNAR-LAB",None,"Solid materials", "Two offset samples per drop; material and geometry varied across series",SG,locator,[p],[measurement(rid,SG,locator,"extinction_protocol","Study endpoint is burning status at the end of the 5.2-second drop, distinct from NASA Test 1 burn length",outcome="The test series used a short-duration extinction criterion; it does not identify a run-level material pass/fail outcome.",protocol=p["protocol"])],etype="aggregate_observation",qualifier="Nominal low-pressure lunar-gravity protocol. Aggregate context is excluded from physical-run coverage; no material acceptance conclusion is assigned.")
passage("PASS-"+rid,SG,"Lunar low-pressure centrifugal test protocol", "The study targeted 56.5 kPa (8.2 psia). Glenn tests used a 20.4 RPM centrifuge during 5.2-second drops, producing nominal one-sixth-g radial acceleration. Oxygen limits varied by material; results depend on ignition and short-duration extinction protocols.",locator,run_ids=[rid])

# FLEX detailed results use actual mmHg pressure and measured initial diameter,
# which differ from the nominal matrix. Preserve the table's outcome label and
# leave unknown relative flow speed null even in a nominally quiescent chamber.
for number,identifier,fuel,pressure_mmhg,o2,initial_d,extinction_d,burn_s,page,nominal_d,nominal_o2 in [
 ("002","20CAL10","Methanol",762,21,1.86,0.94,5,26,2.00,21),
 ("003","20CAL12","Methanol",764.2,21,1.61,0.92,3.2,26,1.71,21),
 ("005","30CAL03","Methanol",760,21,1.92,0.81,6.34,26,1.95,21),
 ("006","40CAL01","Methanol",760,21,2.54,1.53,9.6,26,2.90,21),
 ("035","181F001","Heptane",768.1,21,3.85,3.34,8.9,27,None,None),
 ("036","190R002","Methanol",539,20,2.4,1.67,7.1,27,2.45,21)]:
    rid="FLEX-"+number
    locator=loc(page,"Appendix A, Table IX",f"FLEX-{number}; {identifier}","Detailed droplet results; actual recorded pressure and initial diameter")
    pressure=round(pressure_mmhg*0.133322387415,6)
    original={"FLEX_test":number,"FLEX_identifier":identifier,"absolute_pressure":{"value":pressure_mmhg,"unit":"mmHg"},"oxygen":{"value":o2/100,"unit":"mole fraction"},"nitrogen":{"value":1-o2/100,"unit":"mole fraction; rounded table value"},"actual_initial_droplet_diameter":{"value":initial_d,"unit":"mm"},"nominal_matrix_initial_diameter":{"value":nominal_d,"unit":"mm"},"nominal_matrix_oxygen_pct":nominal_o2,"visible_extinction_diameter":{"value":extinction_d,"unit":"mm"},"reported_test_end":"Extinction","support_fiber":False,"conversion":"1 mmHg = 0.133322387415 kPa"}
    p=phase(SF,locator,o2,pressure,None,"microgravity",None,None,basis="mole",original=original,qualifier="Actual Table IX pressure and oxygen composition are used. Initial diameter differs from nominal matrix values. No measured droplet-relative flow speed is assigned.")
    p["protocol"]="Free droplet; no support fiber; MDCA quiescent chamber; visible-flame extinction"
    measurements=[measurement(rid,SF,locator,"visible_flame_extinction_diameter","Droplet diameter when the visible flame extinguished; Table IX and Appendix A.1 definition",extinction_d,"mm",outcome="Visible flame extinction reported; this endpoint does not establish absence of low-temperature combustion.",protocol=p["protocol"]),measurement(rid,SF,locator,"burn_duration","Reported burn time in FLEX Table IX",burn_s,"s",outcome="Table IX test end: Extinction",protocol=p["protocol"])]
    add(rid,"FLEX", "FLEX-"+number,fuel,f"Free droplet, measured initial diameter {initial_d} mm; no support fiber",SF,locator,[p],measurements,lane="suppression",qualifier="Visible-flame extinction is a droplet-study endpoint. It does not demonstrate cabin fire suppression or material acceptance. Independent human verification pending.")
    passage("PASS-"+rid,SF,"FLEX "+number+" visible-flame extinction",f"FLEX-{number} ({identifier}): {fuel}, {o2}% oxygen by mole, {pressure_mmhg} mmHg absolute pressure; initial droplet {initial_d} mm; visible-flame extinction at {extinction_d} mm; burn time {burn_s} s. Free droplet without a support fiber.",locator,lane="suppression",run_ids=[rid],kind="table")
passage("PASS-FLEX-ISS-PRESET",SF,"FLEX cabin-air reference atmosphere", "Section 4.1 and Table I describe the engineering tests in ISS cabin air: nominal oxygen mole fraction 0.21, carbon dioxide mole fraction 0.005, balance nitrogen, at 1.0 atm. This nominal context supports the approximate ISS-like preset; individual test pressures are retained separately.",loc(16,"Table I",label="Cabin-air test matrix and nominal composition; see also PDF page 15"),lane="suppression",kind="table")

def save():
    (ROOT / "data/manifests").mkdir(parents=True,exist_ok=True)
    (ROOT / "data/curated").mkdir(parents=True,exist_ok=True)
    (ROOT/"data/manifests/sources.json").write_text(json.dumps({"schema_version":1,"sources":sources},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (ROOT/"data/curated/evidence.json").write_text(json.dumps({"schema_version":1,"investigations":investigations,"runs":runs,"passages":passages},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Wrote {len(runs)} source-checked rows, {len(passages)} passages, {len(sources)} sources. Human review pending.")

if __name__=="__main__":save()
