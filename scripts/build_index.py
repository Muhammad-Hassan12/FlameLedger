"""Build a fresh index bound to an explicit CPU text export and evidence row order."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from backend.contracts import ScenarioInput, normalize_scenario
from backend.retrieval import Encoder, fmt_doc, fmt_query, scenario_query
from scripts.common import FORMATTING_VERSION, json_read, json_write, jsonl_read, jsonl_write, model_fingerprint, ordered_id_digest, sha256


def build(model,evidence,out):
    model,evidence,out=Path(model),Path(evidence),Path(out)
    passages=jsonl_read(evidence/"passages.jsonl")
    sources={s["id"]:s for s in json_read(evidence/"sources.json")["sources"]}
    evidence_manifest=json_read(evidence/"manifest.json")
    encoder=Encoder(model)
    start=time.perf_counter()
    print(f"Encoding {len(passages)} passages with the selected local export…",flush=True)
    vectors=encoder.encode([fmt_doc(p["title"],p["text"]) for p in passages],batch_size=4)
    out.mkdir(parents=True,exist_ok=True)
    np.save(out/"vectors.npy",vectors,allow_pickle=False)
    jsonl_write(out/"passages.jsonl",passages)
    queries=[scenario_query(normalize_scenario(ScenarioInput(preset_id=p),sources)) for p in ("lunar","iss")]
    preset_vectors=encoder.encode([fmt_query(q) for q in queries],batch_size=2)
    json_write(out/"preset_vectors.json",{q:v.tolist() for q,v in zip(queries,preset_vectors)})
    fingerprint=model_fingerprint(model)
    manifest={"schema_version":1,"dimension":768,"dtype":"float32","row_count":len(passages),
              "ordered_id_digest":ordered_id_digest(passages),"model_fingerprint":fingerprint["digest"],
              "model_files":fingerprint["files"],"formatting_version":FORMATTING_VERSION,
              "evidence_release_id":evidence_manifest["release_id"],"vectors_sha256":sha256(out/"vectors.npy"),
              "passages_sha256":sha256(out/"passages.jsonl"),"preset_vectors_sha256":sha256(out/"preset_vectors.json"),
              "build_seconds":round(time.perf_counter()-start,3)}
    json_write(out/"manifest.json",manifest)
    # Store auditable preset retrieval results through the very same serving ranker.
    from backend.retrieval import Retriever
    ranker=Retriever.__new__(Retriever)
    from backend.retrieval import BM25
    ranker.passages,ranker.vectors,ranker.bm25=passages,vectors,BM25(passages)
    json_write(out/"preset_results.json",{q:ranker.rank(q,vector=v,limit=10) for q,v in zip(queries,preset_vectors)})
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("model","evidence","out"):parser.add_argument("--"+key,type=Path,required=True)
    args=parser.parse_args()
    result=build(args.model,args.evidence,args.out)
    print(json.dumps({k:v for k,v in result.items() if k != "model_files"},indent=2))


if __name__ == "__main__":main()
