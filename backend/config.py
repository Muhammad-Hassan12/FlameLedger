from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from scripts.common import ROOT


@dataclass(frozen=True)
class Settings:
    release_dir: Path
    runtime_mode: str = "cached_bm25"
    data_mode: str = "verified"
    torch_threads: int = 2
    encode_timeout_seconds: float = 3
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_timeout_seconds: float = 8
    gemini_max_output_tokens: int = 1000
    gemini_requests_per_minute: int = 10

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        release = Path(os.getenv("FLAMELEDGER_RELEASE_DIR", "build/release"))
        if not release.is_absolute():
            release = ROOT / release
        mode = os.getenv("FLAMELEDGER_RUNTIME_MODE", "cached_bm25")
        data_mode = os.getenv("FLAMELEDGER_DATA_MODE", "verified")
        if mode not in {"hybrid", "cached_bm25", "bm25"} or data_mode != "verified":
            raise ValueError("Production requires verified data and an explicit supported retrieval mode")
        return cls(release.resolve(), mode, data_mode,
                   max(1, min(4, int(os.getenv("FLAMELEDGER_TORCH_THREADS", "2")))),
                   max(0.1, min(10, float(os.getenv("FLAMELEDGER_ENCODE_TIMEOUT_SECONDS", "3")))),
                   os.getenv("GEMINI_API_KEY", "").strip(), os.getenv("GEMINI_MODEL", "").strip(),
                   max(0.1, min(15, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "8")))),
                   max(100, min(2000, int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1000")))),
                   max(1, min(60, int(os.getenv("GEMINI_REQUESTS_PER_MINUTE", "10")))))
