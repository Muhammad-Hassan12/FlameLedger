"""Export and reload the provided tuned checkpoint with both unused modality towers disabled."""
from __future__ import annotations

import argparse
import gc
import json
import os
import time
from pathlib import Path

import numpy as np

from backend.retrieval import Encoder, fmt_doc, fmt_query
from scripts.common import ROOT, json_read, json_write, jsonl_read, model_fingerprint
from scripts.inspect_embedder_run import tensor_inventory


def export(input_path, out, run_dir=None, skip_full_parity=False):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from safetensors import safe_open
    from sentence_transformers import SentenceTransformer

    input_path, out = Path(input_path).resolve(), Path(out).resolve()
    if out == input_path or out.is_relative_to(input_path) or input_path.is_relative_to(out):
        raise ValueError("Export must be outside the untouched input checkpoint")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Export directory is nonempty; choose a new destination")
    torch.set_num_threads(2)
    queries = ["How does oxygen and pressure change flame spread?", "Smoke detector response in microgravity", "Droplet extinction with carbon dioxide diluent"]
    docs = [("Combustion", "A thin solid fuel is studied in an orbital microgravity combustion chamber."),
            ("Suppression", "Droplet extinction is an endpoint, distinct from solid material flame spread.")]
    probe = [fmt_query(q) for q in queries] + [fmt_doc(t, d) for t, d in docs]
    start = time.perf_counter()
    full_parameters = int(sum(np.prod(v["shape"]).item() for path in input_path.glob("*.safetensors") for v in tensor_inventory(path).values()))
    full_vectors = None
    # Full and slim use identical FP32 inference, explicit prompts, pooling and truncation.
    if not skip_full_parity:
        try:
            import psutil
            if psutil.virtual_memory().available < 4 * 1024**3:
                raise ValueError("Full multimodal FP32 parity needs at least 4 GiB available RAM. Use --skip-full-parity for an explicitly disclosed text-weight audit, or run on a larger offline builder.")
        except ImportError:
            pass
        print("Loading original local multimodal checkpoint for text parity…", flush=True)
        full = SentenceTransformer(str(input_path), device="cpu", local_files_only=True, trust_remote_code=False,
                                   model_kwargs={"dtype": torch.float32})
        full.default_prompt_name = None
        full.max_seq_length = 512
        full.eval()
        with torch.inference_mode():
            full_vectors = np.asarray(full.encode(probe, batch_size=2, normalize_embeddings=True, convert_to_numpy=True,
                                                 show_progress_bar=False, prompt=""), dtype=np.float32)
        del full
        gc.collect()
    print("Loading text-only checkpoint; audio_config=None and vision_config=None…", flush=True)
    encoder = Encoder(input_path)
    slim_vectors = encoder.encode(probe, batch_size=2)
    if full_vectors is not None and not np.allclose(full_vectors, slim_vectors, atol=2e-5, rtol=2e-5):
        raise ValueError("Full/text-only embedding parity failed")
    state = encoder.model[0].auto_model.state_dict()
    if any("vision_tower" in name or "audio_tower" in name for name in state):
        raise ValueError("Unused modality weights remain")
    # Check every retained tensor against supplied weights, not just a sample output.
    originals = sorted(input_path.glob("*.safetensors"))
    checked = set()
    for original in originals:
        with safe_open(original, framework="pt", device="cpu") as tensors:
            for key in tensors.keys():
                if key in state:
                    if not torch.equal(state[key], tensors.get_tensor(key).to(state[key].dtype)):
                        raise ValueError(f"Retained text weight differs from original: {key}")
                    checked.add(key)
    if checked != set(state):
        raise ValueError("A retained text tensor could not be tied to original local weights")
    slim_parameters = sum(p.numel() for p in encoder.model.parameters())
    transformer = encoder.model[0]
    tokenizer = transformer.tokenizer
    processor_tokens = transformer.processor(text=probe, padding=True, truncation=True, max_length=512, return_tensors="pt")
    tokenizer_tokens = tokenizer(probe, padding=True, truncation=True, max_length=512, return_tensors="pt")
    for key in ("input_ids", "attention_mask"):
        if not torch.equal(processor_tokens[key], tokenizer_tokens[key]):
            raise ValueError("Original processor/plain tokenizer text tokenization parity failed")
    # Preserve the original tokenizer and text-forward contract; omit media processors from serving.
    transformer.processor = tokenizer
    transformer.modality_config = {"text": {"method": "forward", "method_output_name": "last_hidden_state"}}
    encoder.model.save(str(out), create_model_card=False, safe_serialization=True)
    tokenizer_config = json_read(out / "tokenizer_config.json")
    tokenizer_config["processor_class"] = "AutoTokenizer"
    json_write(out / "tokenizer_config.json", tokenizer_config)
    del encoder, state
    gc.collect()
    print("Reloading exported checkpoint strictly from local files…", flush=True)
    reloaded = Encoder(out)
    reloaded_vectors = reloaded.encode(probe, batch_size=2)
    if not np.allclose(reloaded_vectors, slim_vectors, atol=2e-5, rtol=2e-5):
        raise ValueError("Saved export reload parity failed")
    legacy = {"status": "not_present"}
    if run_dir and (Path(run_dir) / "index/doc_emb.npy").exists():
        rows = jsonl_read(Path(run_dir) / "index/chunks_meta.jsonl")
        vectors = np.load(Path(run_dir) / "index/doc_emb.npy", allow_pickle=False, mmap_mode="r")
        sample_ids = np.linspace(0, len(rows)-1, min(16,len(rows)), dtype=int)
        sample = reloaded.encode([fmt_doc(rows[i]["title"], rows[i]["text"]) for i in sample_ids], batch_size=2)
        cosines = np.sum(sample * vectors[sample_ids], axis=1)
        cpu_top = np.argsort(-(sample @ vectors.T), axis=1)[:,:5]
        self_hit = [int(i) in top for i, top in zip(sample_ids,cpu_top)]
        legacy = {"status": "sample_checked" if float(cosines.min()) >= 0.98 and all(self_hit) else "historical_index_not_identity_verified",
                  "sample_size": len(sample_ids), "cosine_tolerance": 0.98, "reason": "Original GPU BF16 vs CPU FP32; this sample is an audit, a new index is always built",
                  "cosine_min": float(cosines.min()), "cosine_mean": float(cosines.mean()), "self_hit_at_5": sum(self_hit)/len(self_hit),
                  "ordered_sample_ids": [rows[i]["doc_id"] for i in sample_ids]}
    elapsed = time.perf_counter()-start
    del reloaded
    gc.collect()
    fingerprint = model_fingerprint(out)
    report = {"original_parameters": full_parameters, "text_parameters": slim_parameters, "retained_tensors_verified": len(checked),
              "dtype": "float32", "dimension": 768, "max_seq_length": 512,
              "processor_tokenizer_input_ids_and_masks": "identical", "serving_processor": "original_tokenizer_text_only",
              "full_slim_max_abs_error": float(abs(full_vectors-slim_vectors).max()) if full_vectors is not None else None,
              "full_modality_parity": "passed" if full_vectors is not None else "not_run_explicit_memory_limited_export",
              "reload_max_abs_error": float(abs(slim_vectors-reloaded_vectors).max()),
              "parity_tolerance": {"atol":2e-5,"rtol":2e-5}, "legacy_index": legacy,
              "elapsed_seconds": round(elapsed,3), "model_fingerprint": fingerprint["digest"],
              "files": fingerprint["files"], "original_input": str(input_path), "network_access": "disabled"}
    # Report is outside the model directory so its digest cannot recursively include itself.
    json_write(out.parent / (out.name + "-export-report.json"), report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--run-dir",type=Path,default=ROOT/"NASA_Flame_In_Freefall_Final/runs/full")
    parser.add_argument("--skip-full-parity",action="store_true",help="Explicitly disclose no full multimodal inference parity; still verify every retained original tensor and local reload")
    args=parser.parse_args()
    report=export(args.input,args.out,args.run_dir,args.skip_full_parity)
    print(json.dumps({k:v for k,v in report.items() if k != "files"},indent=2))


if __name__ == "__main__":
    main()
