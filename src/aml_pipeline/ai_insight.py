
import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def explain_view(context: str) -> str:
    """Ask the configured model to explain supplied, already-aggregated facts."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENROUTER_API_KEY is empty. Add your key to .env and restart the app.")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    response = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": (
                    "You are an AML monitoring analyst. Use only the supplied aggregate facts. "
                    "Respond in English. Do not infer criminal intent, invent numbers, or call review priority a probability. "
                    "Give a short explanation, evidence, one sensible next review step, and a limitation. "
                    "Clearly state that a human must review every signal."
                )},
                {"role": "user", "content": context},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"].get("content", "No text returned.")
