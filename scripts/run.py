"""Start the local single-worker application using .env."""
import os

import uvicorn
from dotenv import load_dotenv

from scripts.common import ROOT


def main():
    load_dotenv(ROOT/".env")
    uvicorn.run("backend.main:app",host=os.getenv("FLAMELEDGER_HOST","127.0.0.1"),port=int(os.getenv("FLAMELEDGER_PORT","8000")),workers=1)


if __name__ == "__main__":main()
