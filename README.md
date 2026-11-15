# FlameLedger

An evidence research console for NASA's Flame in Freefall challenge, implemented from [the supplied plan](<FlameLedger_Implementation_Plan (1).md>). A scenario finds relevant experiments, shows condition differences and missing fields, opens source records, compares two observations and exports the ledger. The application works with an empty Gemini key.

Python 3.12, FastAPI, SQLite, NumPy and a static HTML/CSS/JavaScript frontend. The provided fine-tuned EmbeddingGemma 2 checkpoint is exported locally; no retraining or replacement encoder is used. There is no Node build dependency or database server.

The deployed application is **http://169.58.54.125:8097**, installed at `/home/owais/NASA_Space_App` with an isolated PM2 daemon. See [VPS operations](deploy/VPS.md) for service commands and [STATUS.md](STATUS.md) for measured validation and remaining review gates. Existing VPS applications and Nginx configuration were preserved. Direct IP access currently uses HTTP.

## Local start

The project environment is `.venv`. On Windows:

```powershell
.\.venv\Scripts\python.exe -m scripts.run
```

Open **http://127.0.0.1:8000**. The server serves the selected immutable release. API documentation is at `/api/docs`. `GET /api/readyz` reports evidence readiness, dense-index availability and live-encoder capability separately.

For a fresh environment, run `./scripts/bootstrap.ps1 -ForExport`. On Linux use `bash scripts/bootstrap.sh --for-export`. The export-only CPU Torchvision dependency loads the original multimodal processor; the resulting serving model uses only the original text tokenizer.

## Credentials

`.env` and `.env.example` contain all configuration slots. Put the Gemini key in **`GEMINI_API_KEY`** and set **`GEMINI_MODEL`** to a model available to that key, then restart the server. A blank key or model enables the evidence-only fallback. Keys are never sent to the browser. A valid JSON structure is not a scientific review; AI claims are labeled unreviewed.

VPS host, SSH user, SSH key path, public hostname and ACME email have separate blank handoff fields. They are not required for local development. Do not paste credentials into source files or chat.

On the deployed VPS, set Gemini credentials in `/home/owais/NASA_Space_App/shared/flameledger.env` and restart only `nasa-space-app` using the project-specific `PM2_HOME` shown in the VPS operations guide. The server's `.env` points to this protected file; changing the Windows `.env` does not automatically update the VPS.

## Reproduce the build

Use the Python executable inside the virtual environment for every command below (`python` after activating `.venv`). The original uploaded directory remains untouched and is excluded by `.gitignore`.

```text
python -m scripts.inspect_embedder_run --run-dir NASA_Flame_In_Freefall_Final/runs/full
python -m scripts.fetch_sources --nist
python -m scripts.build_evidence --manifest data/manifests/sources.json --out build/evidence
python -m scripts.export_embedder --input NASA_Flame_In_Freefall_Final/runs/full/model_ft --out build/model-text
python -m scripts.build_index --model build/model-text --evidence build/evidence --out build/index
python -m scripts.build_frontend
python -m scripts.assemble_release --evidence build/evidence --index build/index --model build/model-text --frontend frontend/out --out build/release --mode cached_bm25
python -m scripts.verify_release --release build/release
python -m pytest -q
```

`export_embedder` requires a fresh destination. On a builder with less than 4 GiB of available memory, use `--skip-full-parity` explicitly: it still checks every retained tensor, original-processor/tokenizer text parity, local save/reload embeddings and a deterministic legacy-index sample, but records full multimodal inference parity as unmeasured in that export command. Then run `python -m scripts.check_full_parity` for a sequential full/slim comparison at a shared BF16 precision. That separate check passed here with identical embeddings and top-ten rankings; serving and the rebuilt index remain FP32.

Releases are immutable: assemble subsequent builds into a **new** directory and set `FLAMELEDGER_RELEASE_DIR` to it. Original source PDFs, checkpoint weights and generated releases stay out of Git. Source manifests and curated rows are versionable; source-byte checksums are verified during build. `artifacts/intake.json` records a digest of every supplied run file.

An explicit lexical-only release can be built with `assemble_release --mode bm25` while omitting `--index` and `--model`. No dense capability is claimed in that mode.

## Runtime modes

| Mode | Behavior |
| --- | --- |
| `cached_bm25` | Fine-tuned preset vectors plus BM25; fresh queries use BM25. Does not load PyTorch. Default until live inference passes host budgets. |
| `hybrid` | One CPU text encoder, one bounded in-flight encode, exact normalized cosine and positive-score BM25 with RRF. A busy or slow encoder falls back to lexical retrieval. |
| `bm25` | Lexical retrieval only. A query with no matching tokens returns no scored passages. |

The supplied local `.env` selects `build/releases/20261115-final` and live `hybrid` after the measured CPU smoke checks. The VPS environment example starts in `cached_bm25` until actual host budgets pass. Under a burst of fresh queries, the bounded encoder intentionally returns BM25 for busy requests; the response reports that mode.

Applicability ranking is deterministic and independent of LLM or embedding inference. Each request reports the retrieval mode actually used. Corrupt evidence prevents readiness; a dense-only integrity failure disables dense retrieval while preserving evidence and lexical access.

## Verification and scientific limits

```text
python -m scripts.smoke_api --url http://127.0.0.1:8000
python -m scripts.browser_qa --url http://127.0.0.1:8000
python -m scripts.eval_retrieval --release build/release --questions eval/development_questions.jsonl
```

The completed local walkthrough is [artifacts/demo-accepted/flameledger-walkthrough.webm](artifacts/demo-accepted/flameledger-walkthrough.webm), 15.16 seconds. To make another take, install the small recorder once with `python -m playwright install ffmpeg`, then run `python -m scripts.browser_qa --record-only --out artifacts/new-demo-take` against a running server and a fresh output directory.

Browser QA uses the locally installed Chrome in headless mode. It records screenshots at 360, 768 and 1440 px, normal/reduced motion, keyboard focus return, coverage selection, CSV and an artwork-failure path. Rendering metrics use a recorded mobile throttle profile. The transfer estimate and measured browser results are separate artifacts. API smoke uses four concurrent clients; template timing is never called live Gemini latency.

The existing human gold file is a template, and teacher drafts were not reviewed. Development questions are **AI-authored, unreviewed smoke checks**. `eval/human_questions.jsonl` intentionally remains empty until a person supplies independently authored, source-labeled questions. The evaluator refuses an empty set and requires recorded human reviewers for human labels. A three-way development comparison is complete using the exact base revision recorded in the uploaded model card; see [the scorecard](eval/SCORECARD.md). Encoders load sequentially to limit evaluation memory.

```text
python -m scripts.eval_retrieval --release build/releases/20261115-final --questions eval/development_questions.jsonl --base-model build/base-text --base-index build/base-index --out artifacts/retrieval-evaluation-three-way.json
```

To reproduce the reference build in a fresh workspace, run `python -m scripts.download_base_reference`, export `build/base-original` to a fresh `build/base-text` with `--run-dir build/no-legacy-reference --skip-full-parity`, and run `build_index` with that base export and the same evidence snapshot. The downloader pins the revision named in the supplied model card, checks upstream LFS hashes, and never changes the production encoder. Reference assets remain under ignored `build/` paths.

The ready deployment archive is [build/dist/flameledger-20261115-final.tar.gz](build/dist/flameledger-20261115-final.tar.gz), with its digest in the adjacent JSON report. To package a new verified bundle, use `python -m scripts.pack_release --release <fresh-release-directory> --out <fresh-archive-path>`. It includes only bound release files and rejects credentials and unsafe paths. Ledger export follows the active filters and coverage selection; **Export pair CSV** exports the two comparison records with original conditions, protocols, source hashes and citations.

Source-checked rows are an inspectable preview. Independent human verification is pending until a reviewer and date are recorded in curated rows. Default coverage counts only human-verified physical runs; the optional source-checked coverage grid is explicitly labeled. Aggregate observations never inflate run counts. Follow [the source review checklist](docs/SOURCE_REVIEW.md) before judging.

See [STATUS.md](STATUS.md) for the current milestone state, measured results and missing acceptance inputs; [deployment instructions](deploy/README.md) for Linux VPS staging and rollback; [research notes](docs/RESEARCH_NOTES.md) for primary documentation and the event-rule recheck; and [artwork disclosure](docs/ART_DISCLOSURE.md) for the original decorative asset and generation prompt.
