"""One preprocessing contract for offline indexing, evaluation and CPU serving."""
from __future__ import annotations

import asyncio
import math
import re
import threading
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from scripts.common import FORMATTING_VERSION, json_read, jsonl_read, ordered_id_digest, sha256


def fmt_query(query):
    return "task: search result | query: " + " ".join(str(query).split())


def fmt_doc(title, text):
    return f"title: {' '.join((title or '').split()) or 'none'} | text: {str(text).strip()}"


def scenario_query(scenario):
    parts = [scenario["question"]]
    for key, label in (("oxygen_pct", "oxygen percent"), ("pressure_kpa", "pressure kPa"), ("g_level", "gravity g"), ("flow_cm_s", "airflow cm/s")):
        if scenario.get(key) is not None:
            parts.append(f"{label}: {scenario[key]:.4g}")
    if scenario.get("material", "all") != "all":
        parts.append(f"material: {scenario['material']}")
    if scenario.get("endpoint"):
        parts.append(f"endpoint: {scenario['endpoint']}")
    return "; ".join(parts)


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*", text.casefold())


class BM25:
    def __init__(self, passages):
        self.passages = passages
        self.counts = [Counter(tokens(p["title"] + " " + p["text"])) for p in passages]
        self.lengths = np.array([sum(c.values()) for c in self.counts], dtype=np.float32)
        self.avg = float(self.lengths.mean()) if len(self.lengths) else 1.0
        self.df = Counter(token for c in self.counts for token in c)

    def rank(self, query, allowed=None):
        n = len(self.passages)
        query_tokens = sorted(set(tokens(query)))
        ranked = []
        for i, counts in enumerate(self.counts):
            if allowed is not None and i not in allowed:
                continue
            score = 0.0
            for token in query_tokens:
                tf = counts[token]
                if tf:
                    idf = math.log1p((n - self.df[token] + 0.5) / (self.df[token] + 0.5))
                    score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * self.lengths[i] / max(self.avg, 1)))
            if score > 0:  # Never give an RRF rank to a zero-score lexical candidate.
                ranked.append((i, float(score)))
        return sorted(ranked, key=lambda item: (-item[1], self.passages[item[0]]["id"]))


def fuse(dense, lexical, passages, limit=10, per_source=2):
    if not lexical:
        ranking = dense  # Preserve the dense ordering if no lexical evidence exists.
    elif not dense:
        ranking = lexical
    else:
        scores = Counter()
        for ordered in (dense, lexical):
            for position, (i, _) in enumerate(ordered, 1):
                scores[i] += 1.0 / (60 + position)
        ranking = sorted(scores.items(), key=lambda item: (-item[1], passages[item[0]]["id"]))
    selected, counts = [], Counter()
    for i, score in ranking:
        sid = passages[i]["source_id"]
        if counts[sid] >= per_source:
            continue
        counts[sid] += 1
        selected.append({**passages[i], "score": float(score)})
        if len(selected) == limit:
            break
    return selected


def validate_matrix(path, passages, manifest):
    vectors = np.load(path, mmap_mode="r", allow_pickle=False)
    if vectors.dtype != np.float32 or vectors.shape != (len(passages), 768):
        raise ValueError("Index must be float32 with one 768-dimensional row per passage")
    if len({p["id"] for p in passages}) != len(passages) or any(not p["id"] for p in passages):
        raise ValueError("Index passage IDs must be nonempty and unique")
    if manifest.get("ordered_id_digest") != ordered_id_digest(passages):
        raise ValueError("Index row-ID order mismatch")
    if manifest.get("vectors_sha256") != sha256(Path(path)):
        raise ValueError("Index vector checksum mismatch")
    if manifest.get("formatting_version") != FORMATTING_VERSION:
        raise ValueError("Index preprocessing contract mismatch")
    if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-3):
        raise ValueError("Index contains nonfinite or non-unit vectors (norm tolerance 1e-3)")
    return vectors


class Encoder:
    def __init__(self, path, threads=2):
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(threads)
        self.model = SentenceTransformer(str(path), device="cpu", local_files_only=True, trust_remote_code=False,
                                         config_kwargs={"vision_config": None, "audio_config": None},
                                         model_kwargs={"dtype": torch.float32})
        self.model.default_prompt_name = None
        self.model.max_seq_length = 512
        self.model.eval()

    def encode(self, formatted, batch_size=4):
        import torch

        with torch.inference_mode():
            output = self.model.encode(formatted, batch_size=batch_size, normalize_embeddings=True,
                                       convert_to_numpy=True, show_progress_bar=False, prompt="")
        output = np.asarray(output, dtype=np.float32)
        if output.ndim != 2 or output.shape[1] != 768 or not np.isfinite(output).all():
            raise ValueError("Encoder returned invalid vectors")
        return output


class Retriever:
    def __init__(self, release, passages, mode="cached_bm25", threads=2, timeout=3):
        self.passages, self.mode, self.timeout = passages, mode, timeout
        self.bm25 = BM25(passages)
        self.vectors = self.encoder = None
        self.capability_error = None
        self.cache = OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flameledger-encode")
        self.slot = threading.BoundedSemaphore(1)
        index = Path(release) / "index"
        if mode != "bm25":
            try:
                manifest = json_read(index / "manifest.json")
                indexed = jsonl_read(index / "passages.jsonl")
                if ordered_id_digest(indexed) != ordered_id_digest(passages):
                    raise ValueError("Evidence/index row-ID mismatch")
                self.vectors = validate_matrix(index / "vectors.npy", indexed, manifest)
                for query, vector in json_read(index / "preset_vectors.json").items():
                    vector = np.asarray(vector, dtype=np.float32)
                    if vector.shape != (768,) or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-3):
                        raise ValueError("Preset vector integrity failure")
                    self.cache[query] = vector
                if mode == "hybrid":
                    self.encoder = Encoder(Path(release) / "model", threads)
            except (OSError, ValueError, ImportError, RuntimeError) as error:
                self.capability_error = type(error).__name__
                self.vectors = self.encoder = None
                self.cache.clear()

    def rank(self, query, *, lane="all", limit=10, vector=None, method=None):
        allowed = {i for i, p in enumerate(self.passages) if lane == "all" or p["lane"] == lane}
        lexical = self.bm25.rank(query, allowed)
        dense = []
        if vector is not None and self.vectors is not None and method != "bm25":
            scores = self.vectors @ vector
            dense = sorted(((i, float(scores[i])) for i in allowed), key=lambda x: (-x[1], self.passages[x[0]]["id"]))[:100]
        return fuse(dense[:100], lexical[:100], self.passages, limit=limit)

    async def query_vector(self, query):
        if self.mode == "bm25" or self.vectors is None:
            return None, "bm25"
        if query in self.cache:
            return self.cache[query], "cached_tuned_hybrid"
        if self.encoder is None or not self.slot.acquire(blocking=False):
            return None, "bm25"

        def compute():
            try:
                return self.encoder.encode([fmt_query(query)])[0]
            finally:
                self.slot.release()

        future = self.pool.submit(compute)
        try:
            vector = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), self.timeout)
            self.cache[query] = vector
            if len(self.cache) > 128:
                self.cache.popitem(last=False)
            return vector, "tuned_hybrid"
        except (TimeoutError, ValueError, RuntimeError):
            return None, "bm25"

    async def search(self, query, lane="all", limit=10):
        vector, mode = await self.query_vector(query)
        return {"results": self.rank(query, lane=lane, limit=limit, vector=vector), "retrieval_mode": mode}

    async def balanced(self, query):
        vector, mode = await self.query_vector(query)  # Reused across lane filters.
        selected, ids = [], set()
        for lane in ("prevention", "detection", "suppression"):
            for item in self.rank(query, lane=lane, limit=3, vector=vector):
                selected.append(item)
                ids.add(item["id"])
        for item in self.rank(query, limit=10, vector=vector):
            if item["id"] not in ids and len(selected) < 10:
                selected.append(item)
                ids.add(item["id"])
        return selected, mode

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
