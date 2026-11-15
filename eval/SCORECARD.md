# Serving-ranker development scorecard

Data: `evidence-0bba52783537175d`, 517 passages. All methods use the production BM25/RRF implementation, stable passage-ID ties and two-per-source cap. The 20 source-specific questions are **agent-authored, unreviewed development probes**, grouped into eight families. There are zero independently human-authored questions. These results are not independent relevance quality or a mission-safety claim.

| Method | Passage Hit@5 | Passage MRR@10 | True passage Recall@5 | Encode-inclusive p95 |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 1.000 | 0.925 | 1.000 | 6.2 ms |
| Base hybrid | 1.000 | 0.902 | 1.000 | 211.5 ms |
| Fine-tuned hybrid | 1.000 | 1.000 | 1.000 | 224.9 ms |

No query has a labeled relevant passage outside the first five in this small draft set. Examples where the base hybrid misses the **first** position: D01 (Saffire VI-2 executed atmosphere, rank 5), D11 (Kapton detector response, rank 3), D12 (Teflon detector response, rank 2). The tuned hybrid places the labeled passage first for these probes. Do not equate this with an improvement on independent human questions. Each question's labels cover one document, so multi-document Recall@10 is not reported. No confidence interval is computed on correlated draft families.

The reference is the original immutable base revision `google/embeddinggemma-2@f9972ac22e696a105c482202646979e33e4b5a1e`, identified in the supplied fine-tuned model card. Its downloaded weights match upstream SHA-256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`. The base export fingerprint is `be34e3d0b64d7393e0ca384749a06c882794346f807295ff7d2ae60518d4b022`; the tuned export is `85ff90ad56da284b380951290c079f53b0d4140f17eabca5612ad934042d6ab4`. Both use FP32, explicit notebook prompts, a 512-token limit, mean pooling and normalized 768-dimensional vectors. Base vectors were built separately over byte-identical passage metadata. The evaluator rejects encoder/index, text, release and row-order mismatches.

Measurements are local Windows CPU results, with models loaded sequentially and two PyTorch threads; model loading is excluded from per-query latency. Linux VPS and live Gemini timing require separate host/provider measurements.

Reproduce with the command in [README.md](../README.md). Detailed question IDs, citations and returned rankings are in [the measured JSON report](../artifacts/retrieval-evaluation-three-way.json). Historical synthetic/teacher results stay in the untouched uploaded run and are not substituted for this scorecard. Complete `human_questions.jsonl` with 15–25 independently authored and source-labeled questions before publishing a human quality claim.
