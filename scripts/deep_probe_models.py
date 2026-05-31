"""
scripts/deep_probe_models.py
Full capability probe of all 55 Gemini API models.

For each model, fetches:
  - supportedGenerationMethods
  - inputTokenLimit, outputTokenLimit
  - supportedActions / capabilities (where available)
  - description, displayName, version
  - temperature range, topP, topK defaults
  - Probes countTokens endpoint to validate live reachability

Writes full results to scripts/model_capability_map.json.
"""
import json
import ssl
import urllib.request
import urllib.error
import sys
from typing import Any

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maccre_core.orchestration.windows_vault import get_native_credential
from maccre_core.utils.path_resolver import get_maccre_root

key = str(get_native_credential("MACCRE_Sovereign")).strip()
ssl_ctx = ssl.create_default_context()
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def fetch_model_detail(model_name: str) -> dict[str, Any]:
    """Fetch the full model spec from GET /v1beta/models/{model}."""
    url = f"{BASE}/{model_name}?key={key}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
            return json.loads(r.read().decode())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        return {"name": model_name, "_probe_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"name": model_name, "_probe_error": str(e)}


def probe_count_tokens(model_name: str) -> dict[str, Any]:
    """Probe countTokens to confirm the model is live and queryable."""
    url = f"{BASE}/{model_name}:countTokens?key={key}"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
            resp = json.loads(r.read().decode())
            return {"live": True, "token_count": resp.get("totalTokens", -1)}
    except urllib.error.HTTPError as e:
        return {"live": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"live": False, "error": str(e)}


# ── Fetch full model list ─────────────────────────────────────────────────────
url = f"{BASE}?pageSize=500&key={key}"
req = urllib.request.Request(url, method="GET")
with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as r:
    data = json.loads(r.read().decode())

all_models = data.get("models", [])
print(f"Total models from API: {len(all_models)}\n")

# ── Deep probe each model ─────────────────────────────────────────────────────
results: list[dict[str, Any]] = []

for m in all_models:
    short_name = m["name"].removeprefix("models/")
    print(f"Probing: {short_name:55}", end=" ", flush=True)

    # Get full detail from REST (includes limits, capabilities, defaults)
    detail = fetch_model_detail(short_name)

    # Probe liveness only for countTokens-capable models
    methods = detail.get("supportedGenerationMethods", [])
    liveness: dict[str, Any] = {"live": "N/A", "reason": "no countTokens support"}
    if "countTokens" in methods:
        liveness = probe_count_tokens(short_name)

    record: dict[str, Any] = {
        "name":                   short_name,
        "displayName":            detail.get("displayName", ""),
        "description":            detail.get("description", "")[:120],
        "version":                detail.get("version", ""),
        "supportedMethods":       methods,
        "inputTokenLimit":        detail.get("inputTokenLimit", -1),
        "outputTokenLimit":       detail.get("outputTokenLimit", -1),
        "temperature":            detail.get("temperature"),
        "topP":                   detail.get("topP"),
        "topK":                   detail.get("topK"),
        "maxTemperature":         detail.get("maxTemperature"),
        # Some models expose these:
        "supportedLanguages":     detail.get("supportedLanguages", []),
        "liveness":               liveness,
        "probe_error":            detail.get("_probe_error"),
    }
    results.append(record)

    live_str = "✅" if liveness.get("live") is True else ("⚡" if liveness.get("live") == "N/A" else "❌")
    tokens_str = str(record["inputTokenLimit"]) if record["inputTokenLimit"] != -1 else "?"
    print(f"{live_str}  ctx={tokens_str}")

# ── Save to JSON ──────────────────────────────────────────────────────────────
import pathlib  # noqa: E402
out = get_maccre_root() / "scripts" / "model_capability_map.json"
out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n[OK] Full capability map written to {out}")
print(f"Total capabilities probed: {len(results)} models")
