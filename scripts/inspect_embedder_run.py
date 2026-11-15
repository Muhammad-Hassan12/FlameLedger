"""Audit local artifacts without executing the notebook or downloading replacement weights."""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

import numpy as np

from scripts.common import ROOT, digest_json, json_read, json_write, jsonl_read, sha256, safe_child


def tensor_inventory(path):
    with Path(path).open("rb") as stream:
        header_size = struct.unpack("<Q", stream.read(8))[0]
        if header_size > 32 * 1024 * 1024:
            raise ValueError("Invalid safetensors header length")
        header = json.loads(stream.read(header_size))
    result = {k: v for k, v in header.items() if k != "__metadata__"}
    size = Path(path).stat().st_size - 8 - header_size
    for name, spec in result.items():
        if spec["data_offsets"][1] > size or spec["data_offsets"][0] < 0:
            raise ValueError(f"Invalid tensor byte range: {name}")
    return result


def inspect(run_dir):
    run_dir = Path(run_dir).resolve()
    required = ["model_ft/config.json", "model_ft/modules.json", "model_ft/tokenizer.json",
                "model_ft/1_Pooling/config.json", "index/doc_emb.npy", "index/chunks_meta.jsonl",
                "index/serving_config.json", "results.json", "scorecard.md"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    report = {"run_dir": str(run_dir), "missing_required": missing, "errors": [], "warnings": []}
    if missing:
        report["errors"].append("Required files are missing; no replacement model is allowed.")
        return report
    config = json_read(run_dir / "model_ft/config.json")
    serving, results = json_read(run_dir / "index/serving_config.json"), json_read(run_dir / "results.json")
    for key, result_key in (("dim", "dim"), ("hybrid", "use_hybrid"), ("model", "model")):
        if serving.get(key) != results.get(result_key):
            report["errors"].append(f"Saved model selection disagreement: {key}")
    if not str(serving["model"]).replace("\\", "/").endswith("/model_ft") or not results.get("ship_ft"):
        report["errors"].append("Saved run did not select the requested tuned checkpoint")
    if config.get("model_type") != "embedding_gemma2":
        report["errors"].append("Unexpected architecture")
    weight_files = sorted((run_dir / "model_ft").glob("*.safetensors"))
    shard_index = run_dir / "model_ft/model.safetensors.index.json"
    if shard_index.exists():
        for shard in set(json_read(shard_index)["weight_map"].values()):
            if not safe_child(run_dir / "model_ft", shard).is_file():
                report["errors"].append(f"Missing checkpoint shard: {shard}")
    if not weight_files:
        report["errors"].append("No local checkpoint weights")
    tensors = {}
    for path in weight_files:
        tensors.update(tensor_inventory(path))
    rows = jsonl_read(run_dir / "index/chunks_meta.jsonl")
    vectors = np.load(run_dir / "index/doc_emb.npy", allow_pickle=False, mmap_mode="r")
    ids = [r.get("doc_id") for r in rows]
    if len(set(ids)) != len(ids) or not all(ids):
        report["errors"].append("Duplicate/empty legacy doc IDs")
    if vectors.dtype != np.float32 or vectors.shape != (len(rows), 768):
        report["errors"].append("Legacy vector shape or dtype mismatch")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(vectors).all() or not np.allclose(norms, 1, atol=1e-3):
        report["errors"].append("Invalid legacy vectors")
    chunks_path = run_dir / "chunks.jsonl"
    if chunks_path.is_file():
        original = jsonl_read(chunks_path)
        if [(r["doc_id"], digest_json(r["text"])) for r in rows] != [(r["doc_id"], digest_json(r["text"])) for r in original]:
            report["errors"].append("Legacy metadata differs from corpus order/text")
    report.update({"resolved_model": str(run_dir / "model_ft"), "historical_pointer": serving["model"],
                   "architecture": config.get("architectures"), "dimension": serving["dim"],
                   "parameters": sum(math.prod(v["shape"]) for v in tensors.values()),
                   "tensor_count": len(tensors), "weight_dtypes": sorted({v["dtype"] for v in tensors.values()}),
                   "legacy_index_shape": list(vectors.shape), "legacy_norm_max_error": float(abs(norms - 1).max()),
                   "human_questions": results.get("n_gold_human", 0), "teacher_drafts_reviewed": results.get("drafted_reviewed"),
                   "legacy_checkpoint_vector_parity": "unverified_until_sample_reembedding",
                   "original_files": {p.relative_to(run_dir).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
                                      for p in sorted(run_dir.rglob("*")) if p.is_file()}})
    report["source_tree_digest"] = digest_json(report["original_files"])
    report["warnings"] += ["No October 28 PSI package was found in the project inventory.",
                             "Historical Colab path mapped explicitly to local model_ft; no network substitution.",
                             "A fresh deployment index must bind exact model weights, preprocessing and passage row order."]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/intake.json")
    args = parser.parse_args()
    try:
        report = inspect(args.run_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"errors": [str(error)]}
    json_write(args.out, report)
    print(json.dumps({k: v for k, v in report.items() if k != "original_files"}, indent=2))
    raise SystemExit(1 if report.get("errors") else 0)


if __name__ == "__main__":
    main()
