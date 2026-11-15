#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
if [[ "${1:-}" == --with-model || "${1:-}" == --for-export ]]; then
    .venv/bin/python -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
    .venv/bin/python -m pip install -r requirements-ml.txt
fi
if [[ "${1:-}" == --for-export ]]; then
    .venv/bin/python -m pip install torchvision==0.26.0+cpu --index-url https://download.pytorch.org/whl/cpu
fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
echo 'Ready. See README.md for build and launch commands.'
