"""Verify that the configured Gemini model is available to the server API key; never print the key."""
import json

import httpx

from backend.config import Settings


def main():
    settings=Settings.from_env()
    if not settings.gemini_api_key or not settings.gemini_model:
        print(json.dumps({"configured":False,"message":"Fill GEMINI_API_KEY and GEMINI_MODEL in .env; evidence-only briefing is active."}))
        raise SystemExit(1)
    try:
        with httpx.Client(timeout=8,follow_redirects=False) as client:
            response=client.get(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}",headers={"x-goog-api-key":settings.gemini_api_key})
            response.raise_for_status();model=response.json()
            if "generateContent" not in model.get("supportedGenerationMethods",[]):raise ValueError("Configured model does not support generateContent")
    except (httpx.HTTPError,ValueError):
        print(json.dumps({"configured":True,"verified":False,"message":"Model availability check failed; inspect the model ID and API access. Credentials were not logged."}))
        raise SystemExit(1)
    print(json.dumps({"configured":True,"verified":True,"model":model.get("name"),"message":"Model is available. Live briefing validation and human claim review remain separate checks."}))


if __name__ == "__main__":main()
