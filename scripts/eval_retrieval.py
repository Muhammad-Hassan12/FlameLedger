"""Evaluate the production ranker. Never relabel agent/teacher drafts as human questions."""
from __future__ import annotations

import argparse
import gc
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend.retrieval import Encoder, Retriever, fmt_query, validate_matrix
from backend.store import EvidenceStore
from scripts.common import json_read, json_write, jsonl_read, ordered_id_digest, model_fingerprint, sha256
from scripts.verify_release import verify


def metrics(results, relevant_passages, relevant_documents):
    ids=[r["id"] for r in results]
    relevant=set(relevant_passages)
    first=next((i for i,p in enumerate(ids,1) if p in relevant),None)
    documents=list(dict.fromkeys(r["source_id"] for r in results))
    labeled=set(relevant_documents)
    return {"passage_hit_at_5":float(bool(relevant.intersection(ids[:5]))),
            "mrr_at_10":1/first if first and first <= 10 else 0,
            "passage_recall_at_5":len(relevant.intersection(ids[:5]))/len(relevant) if relevant else None,
            "unique_document_recall_at_10":len(labeled.intersection(documents[:10]))/len(labeled) if len(labeled)>1 else None}


def evaluate(release,questions,out,base_index=None,base_model=None):
    checked=verify(release)
    if not checked["valid"]:raise ValueError(str(checked))
    rows=jsonl_read(questions)
    if not rows:raise ValueError("No labeled questions. A blank human template is not an evaluation set.")
    required={"id","query","set","relevant_passage_ids","authorship","question_family"}
    for row in rows:
        if not required.issubset(row) or not row["relevant_passage_ids"]:
            raise ValueError("Questions require identities, relevance labels and authorship")
        if row["authorship"] == "human" and not row.get("reviewer"):
            raise ValueError("Human labels need a recorded human reviewer")
    store=EvidenceStore(release)
    by_id={p["id"] for p in store.passages}
    if any(set(r["relevant_passage_ids"])-by_id for r in rows):raise ValueError("Question labels refer to unknown passages")
    ranker=Retriever(release,store.passages,mode="cached_bm25")
    model_path=Path(release)/"model"
    tuned_available=model_path.is_dir() and ranker.vectors is not None
    model_paths={"tuned_hybrid":model_path} if tuned_available else {}
    base_vectors=None
    if base_index or base_model:
        if not base_index or not base_model:raise ValueError("Base hybrid requires separately built base vectors AND their matching base checkpoint")
        base_rows=jsonl_read(Path(base_index)/"passages.jsonl")
        if ordered_id_digest(base_rows) != ordered_id_digest(store.passages):raise ValueError("Base index row order differs from release")
        if sha256(Path(base_index)/"passages.jsonl") != sha256(Path(release)/"evidence/passages.jsonl"):
            raise ValueError("Base index passage text differs from the serving evidence")
        base_manifest=json_read(Path(base_index)/"manifest.json")
        if base_manifest.get("model_fingerprint") != model_fingerprint(base_model)["digest"]:
            raise ValueError("Base model/index checkpoint identity mismatch")
        if base_manifest.get("evidence_release_id") != store.release_id or base_manifest.get("passages_sha256") != sha256(Path(base_index)/"passages.jsonl"):
            raise ValueError("Base index evidence identity mismatch")
        tuned_manifest=Path(release)/"index/manifest.json"
        if tuned_manifest.is_file() and base_manifest.get("model_fingerprint") == json_read(tuned_manifest).get("model_fingerprint"):
            raise ValueError("A distinct base checkpoint is required; tuned weights cannot be relabeled as baseline")
        base_vectors=validate_matrix(Path(base_index)/"vectors.npy",base_rows,base_manifest)
        model_paths["base_hybrid"]=Path(base_model)
    # Evaluate each encoder sequentially; never hold two full models in this small builder.
    query_vectors,encode_times={},{}
    for method,path in model_paths.items():
        encoder=Encoder(path)
        values,timings=[],[]
        for row in rows:
            started=time.perf_counter();values.append(encoder.encode([fmt_query(row["query"])])[0])
            timings.append((time.perf_counter()-started)*1000)
        query_vectors[method],encode_times[method]=values,timings
        del encoder;gc.collect()
    results=[]
    for row_index,row in enumerate(rows):
        vectors={method:values[row_index] for method,values in query_vectors.items()}
        encoding={method:values[row_index] for method,values in encode_times.items()}
        for method in ["bm25",*vectors.keys()]:
            original=ranker.vectors
            if method == "base_hybrid":ranker.vectors=base_vectors
            start=time.perf_counter()
            hits=ranker.rank(row["query"],limit=20,vector=vectors.get(method),method=method)
            latency=(time.perf_counter()-start)*1000
            ranker.vectors=original
            results.append({"id":row["id"],"set":row["set"],"authorship":row["authorship"],"question_family":row["question_family"],
                            "method":method,**metrics(hits,row["relevant_passage_ids"],row.get("relevant_document_ids",[])),
                            "rank_only_ms":latency,"encode_ms":encoding.get(method,0),"retrieval_ms":latency+encoding.get(method,0),
                            "returned_ids":[p["id"] for p in hits],
                            "citations":[{"source_id":p["source_id"],"locator":p.get("locator")} for p in hits]})
    aggregates=[]
    for group in sorted({(r["set"],r["authorship"],r["method"]) for r in results}):
        subset=[r for r in results if (r["set"],r["authorship"],r["method"]) == group]
        record={"set":group[0],"authorship":group[1],"method":group[2],"n":len(subset)}
        for metric in ("passage_hit_at_5","mrr_at_10","passage_recall_at_5","unique_document_recall_at_10"):
            values=[r[metric] for r in subset if r[metric] is not None]
            record[metric]=sum(values)/len(values) if values else None
        record["rank_only_p95_ms"]=float(np.percentile([r["rank_only_ms"] for r in subset],95))
        record["retrieval_p95_ms"]=float(np.percentile([r["retrieval_ms"] for r in subset],95))
        aggregates.append(record)
    report={"release_id":store.release_id,"summary":aggregates,"questions":results,
            "missing_checks":([] if tuned_available else ["Tuned query encoding unavailable"])+([] if "base_hybrid" in model_paths else ["Base checkpoint and separately built base vectors not supplied"]),
            "disclosure":"Rank latency excludes encode time; retrieval_ms includes measured encode time. Unique-document Recall@10 deduplicates canonical source IDs in the first20 serving passage hits (two-per-source cap). Generated questions are development smoke labels; no independent human performance is claimed. No bootstrap confidence interval is computed on correlated question families."}
    json_write(out,report);ranker.close();return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("release","questions"):parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--out",type=Path,default=Path("artifacts/retrieval-evaluation.json"))
    parser.add_argument("--base-index",type=Path);parser.add_argument("--base-model",type=Path)
    args=parser.parse_args();report=evaluate(args.release,args.questions,args.out,args.base_index,args.base_model)
    print(json.dumps({k:v for k,v in report.items() if k != "questions"},indent=2))


if __name__ == "__main__":main()
