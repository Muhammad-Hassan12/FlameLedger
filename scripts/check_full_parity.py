"""Memory-conscious offline full/slim comparison at a common BF16 precision; serving remains FP32."""
import argparse
import gc
import json
import time
from pathlib import Path

import numpy as np

from backend.retrieval import BM25,Retriever,fmt_doc,fmt_query
from scripts.common import ROOT,json_read,json_write,jsonl_read


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full",type=Path,default=ROOT/"NASA_Flame_In_Freefall_Final/runs/full/model_ft")
    parser.add_argument("--slim",type=Path,default=ROOT/"build/model-text")
    parser.add_argument("--index",type=Path,default=ROOT/"build/index")
    parser.add_argument("--questions",type=Path,default=ROOT/"eval/development_questions.jsonl")
    parser.add_argument("--out",type=Path,default=ROOT/"artifacts/full-slim-parity.json")
    args=parser.parse_args()
    import torch
    import psutil
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    rows=jsonl_read(args.questions);passages=jsonl_read(args.index/"passages.jsonl")
    samples=[p for p in passages if p["id"] in {"PASS-SAFFIRE-VI-2","PASS-FLEX-035"}]
    inputs=[fmt_query(r["query"]) for r in rows]+[fmt_doc(p["title"],p["text"]) for p in samples]
    vectors=[];started=time.perf_counter()
    for path,config in ((args.full,{}),(args.slim,{"vision_config":None,"audio_config":None})):
        print(f"Offline BF16 parity: loading {path.name}",flush=True)
        model=SentenceTransformer(str(path),device="cpu",local_files_only=True,trust_remote_code=False,
                                  config_kwargs=config,model_kwargs={"dtype":torch.bfloat16})
        model.default_prompt_name=None;model.max_seq_length=512;model.eval()
        with torch.inference_mode():
            value=model.encode(inputs,batch_size=2,normalize_embeddings=True,convert_to_tensor=True,show_progress_bar=False,prompt="").float().cpu().numpy()
        vectors.append(value)
        del model;gc.collect()
    maximum=float(abs(vectors[0]-vectors[1]).max())
    if not np.allclose(vectors[0],vectors[1],atol=2e-5,rtol=2e-5):raise ValueError("Full/slim BF16 parity failed")
    ranker=Retriever.__new__(Retriever)
    ranker.passages=passages;ranker.bm25=BM25(passages)
    ranker.vectors=np.load(args.index/"vectors.npy",allow_pickle=False,mmap_mode="r")
    equal=[]
    for i,row in enumerate(rows):
        left=[p["id"] for p in ranker.rank(row["query"],vector=vectors[0][i],limit=10)]
        right=[p["id"] for p in ranker.rank(row["query"],vector=vectors[1][i],limit=10)]
        equal.append(left==right)
    memory=psutil.Process().memory_info()
    report={"passed":True,"common_dtype":"bfloat16","serving_dtype":"float32","queries":len(rows),"documents":len(samples),
            "max_abs_embedding_difference":maximum,"tolerance":{"atol":2e-5,"rtol":2e-5},
            "serving_ranker_top10_equal_fraction":sum(equal)/len(equal),"peak_working_set_bytes":getattr(memory,"peak_wset",None),
            "elapsed_seconds":time.perf_counter()-started,"index_evidence_id":json_read(args.index/"manifest.json")["evidence_release_id"],
            "note":"Full and slim checkpoints were loaded sequentially and locally at the same BF16 precision to fit this builder. Export FP32 retained-tensor and save/reload checks are separate. Questions are agent-authored unreviewed parity probes, not human quality evaluation."}
    json_write(args.out,report);print(json.dumps(report,indent=2))


if __name__ == "__main__":main()
