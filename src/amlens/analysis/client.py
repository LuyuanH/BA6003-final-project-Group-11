"""Call OpenRouter from a worker. Never expose credentials or upstream error bodies."""

import json
import os
import socket
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values

from amlens.analysis.context import Prompt
from amlens.analysis.response import (
    OVERVIEW_SCHEMA,
    REPORT_SCHEMA,
    AnalysisError,
    validate_overview,
    validate_report,
)
from amlens.config import DATA_DIR, find_project_root

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 120
MAX_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ModelConfig:
    api_key: str = field(repr=False)
    model: str

    @classmethod
    def from_environment(cls):
        # Use the checkout root regardless of cwd; installed wheels use their data directory.
        # Read settings without exporting secrets into the process environment. Disabling
        # interpolation also preserves literal dollar signs in credentials.
        root = find_project_root() or DATA_DIR
        try:
            values = dotenv_values(root / ".env", encoding="utf-8-sig", interpolate=False)
        except (OSError, UnicodeError):
            values = {}

        def setting(name: str) -> str:
            return (os.environ.get(name, values.get(name)) or "").strip()

        return cls(
            setting("OPENROUTER_API_KEY"),
            setting("AMLENS_AI_MODEL"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


def _http_error(status: int, body: str) -> AnalysisError:
    if status in (401, 403):
        code = "authentication"
    elif status == 402:
        code = "credits"
    elif status == 429:
        code = "rate_limit"
    elif status in (408, 504):
        code = "timeout"
    elif status == 413 or (status == 400 and "context" in body.lower()):
        code = "context_limit"
    elif status in (400, 404, 422):
        code = "model_support"
    else:
        code = "unavailable"
    return AnalysisError(code)


def analyze(
    config: ModelConfig,
    context: dict,
    prompt: Prompt,
    language: str,
    deadline: float,
    kind: str = "case",
) -> tuple[dict, float]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AnalysisError("timeout")
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": prompt.text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "output_language": "Simplified Chinese" if language == "zh" else "English",
                        "overview_data" if kind == "overview" else "case_data": context,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            },
        ],
        "stream": False,
        "max_tokens": 8192,
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "amlens_overview_insight" if kind == "overview" else "amlens_case_review",
                "strict": True,
                "schema": OVERVIEW_SCHEMA if kind == "overview" else REPORT_SCHEMA,
            },
        },
    }
    request = Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": "Bearer " + config.api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=remaining) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AnalysisError("invalid_output")
        envelope = json.loads(raw)
        if "error" in envelope:
            error = envelope["error"]
            raise _http_error(error.get("code", 500), str(error.get("message", "")))
        choice = envelope["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise AnalysisError("invalid_output")
        validator = validate_overview if kind == "overview" else validate_report
        report = validator(json.loads(choice["message"]["content"]), context)
        finished = time.monotonic()
        if finished > deadline:
            raise AnalysisError("timeout")
        return report, finished
    except HTTPError as error:
        try:
            body = error.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        finally:
            error.close()
        raise _http_error(error.code, body) from None
    except (TimeoutError, socket.timeout):
        raise AnalysisError("timeout") from None
    except URLError as error:
        code = "timeout" if isinstance(error.reason, TimeoutError) else "network"
        raise AnalysisError(code) from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise AnalysisError("invalid_output") from None
    except OSError:
        raise AnalysisError("network") from None
