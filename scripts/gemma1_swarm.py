"""Gemma1 Swarm: 10 worker nodes + 1 aggregator.

Each worker node (Gemma3 4b via Ollama) is assigned a random 4-digit × 4-digit
multiplication problem.  Node 11 (also Gemma3 4b) receives all worker answers,
computes the numeric average, and reports the result.

Law V  -- Local Gemma3 via Ollama for edge compute (basic arithmetic).
Law III -- All paths derived from get_maccre_root().
Law IV  -- Output written to 04_Code_Artifacts only.
"""
from __future__ import annotations

import json
import logging
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# ── Path resolver ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
os.environ.setdefault("MACCRE_ROOT", str(Path(__file__).resolve().parent.parent))
from maccre_core.utils.path_resolver import get_maccre_root  # noqa: E402

_ROOT       = get_maccre_root()
_PROJECT    = "Gemma1"
_DC         = _ROOT / "__DATACENTER" / _PROJECT
_ARTIFACTS  = _DC / "04_Code_Artifacts"
_LEDGER_DIR = _DC / "03_Agent_Ledgers"
_ARTIFACTS.mkdir(parents=True, exist_ok=True)
_LEDGER_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging -- strict JSON to Agent_Ledgers ────────────────────────────────────
_log_path = _LEDGER_DIR / "gemma1_swarm_telemetry.json"
_handler  = logging.FileHandler(_log_path, encoding="utf-8")
_handler.setFormatter(
    logging.Formatter('{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":%(message)s}')
)
_console  = logging.StreamHandler(sys.stdout)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                        datefmt="%H:%M:%S"))
logging.basicConfig(level=logging.INFO, handlers=[_handler, _console])
_log = logging.getLogger(__name__)

# ── Ollama constants ──────────────────────────────────────────────────────────
_OLLAMA_URL   = "http://localhost:11434/api/generate"
_GEMMA_MODEL  = "gemma3:4b"
_NODE_COUNT   = 10
_TIMEOUT      = 120  # seconds per Ollama call

# ── Ollama caller (retry on Ollama HTTP 500 overload) ────────────────────────
def _ollama_call(node_id: int, prompt: str, retries: int = 3) -> str:
    """Call Ollama synchronously. Retries up to `retries` times on HTTP 500."""
    payload = json.dumps({
        "model":  _GEMMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},   # Critic-mode for arithmetic accuracy
    }).encode("utf-8")

    req = urllib.request.Request(
        _OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_err = "unknown"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                response_text: str = data.get("response", "").strip()
                return response_text
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP_{exc.code}"
            if exc.code == 500 and attempt < retries:
                _log.warning(json.dumps({"node": node_id, "attempt": attempt,
                                         "warn": "Ollama 500 — backing off 5s"}))
                time.sleep(5)
        except urllib.error.URLError as exc:
            last_err = str(exc)
            break
    return f"GEMMA_CALL_FAILED: {last_err}"


# ── Worker node (nodes 1–10) ─────────────────────────────────────────────────
def _worker_node(node_id: int) -> dict[str, Any]:
    """Generate a random 4-digit * 4-digit problem, solve with Gemma CoT."""
    a = random.randint(1000, 9999)
    b = random.randint(1000, 9999)
    correct = a * b

    # Chain-of-thought prompt: ask Gemma to show its work so it doesn't truncate,
    # then emit a clearly-parseable answer token on the last line.
    prompt = (
        f"You are math worker node {node_id} in a compute swarm.\n"
        f"Problem: {a} * {b}\n"
        "Instructions:\n"
        "  1. Show your multiplication work step by step.\n"
        "  2. On the very last line write EXACTLY: ANSWER: <result>\n"
        "     where <result> is the plain integer product with no commas or spaces.\n"
        "Example last line: ANSWER: 12345678\n"
        "Compute now:"
    )

    t0  = time.monotonic()
    raw = _ollama_call(node_id, prompt)
    ms  = int((time.monotonic() - t0) * 1000)

    # Only parse if not an error response
    parsed: int | None = None
    if not raw.startswith("GEMMA_CALL_FAILED"):
        ans_match = re.search(r"ANSWER:\s*(\d+)", raw, re.IGNORECASE)
        if ans_match:
            parsed = int(ans_match.group(1))
        else:
            # Fallback: last standalone large integer (>= 6 digits avoids noise)
            nums = re.findall(r"\b(\d{6,9})\b", raw.replace(",", ""))
            parsed = int(nums[-1]) if nums else None

    result: dict[str, Any] = {
        "node_id":    node_id,
        "problem":    f"{a} * {b}",
        "correct":    correct,
        "raw_reply":  raw[:300],
        "parsed":     parsed,
        "correct?":   parsed == correct,
        "latency_ms": ms,
    }

    status = "CORRECT" if parsed == correct else (
        f"WRONG(got {parsed} expected {correct})" if parsed is not None
        else f"PARSE_FAIL(raw={raw[:60]!r})"
    )
    _log.info(json.dumps({"node": node_id, "problem": f"{a}*{b}",
                          "parsed": parsed, "correct": correct,
                          "status": status, "ms": ms}))
    return result


# ── Aggregator node (node 11) ─────────────────────────────────────────────────
def _aggregator_node(worker_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Node 11: Gemma reads all worker answers and computes the average."""
    valid   = [r for r in worker_results if r["parsed"] is not None]
    answers = [r["parsed"] for r in valid]

    if not answers:
        _log.error(json.dumps({"node": 11, "error": "No parseable worker results"}))
        return {"node_id": 11, "error": "No parseable answers from workers"}

    # Summarise the answers for Gemma to reason over
    answer_list = "\n".join(
        f"  Node {r['node_id']}: {r['problem']} -> {r['parsed']}"
        for r in valid
    )

    prompt = (
        "You are Gemma Aggregator Node 11. "
        "The following are multiplication answers submitted by 10 Gemma worker nodes:\n\n"
        f"{answer_list}\n\n"
        "Your tasks:\n"
        "1. Compute the mathematical average (mean) of all these answers.\n"
        "2. State each problem and its submitted answer.\n"
        "3. End your reply with exactly this line format: AVERAGE: <number>\n"
        "Be precise."
    )

    t0  = time.monotonic()
    raw = _ollama_call(11, prompt)
    ms  = int((time.monotonic() - t0) * 1000)

    # Extract the AVERAGE line
    avg_match       = re.search(r"AVERAGE:\s*([\d,\.]+)", raw, re.IGNORECASE)
    gemma_avg       = float(avg_match.group(1).replace(",", "")) if avg_match else None
    python_avg      = sum(answers) / len(answers)

    _log.info(json.dumps({
        "node": 11, "role": "aggregator",
        "worker_count": len(valid),
        "python_average": python_avg,
        "gemma_average": gemma_avg,
        "ms": ms,
    }))

    return {
        "node_id":       11,
        "worker_count":  len(valid),
        "answers":       answers,
        "python_average": python_avg,
        "gemma_average": gemma_avg,
        "gemma_full_reply": raw,
        "latency_ms":    ms,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    _log.info(json.dumps({"event": "GEMMA1_SWARM_START",
                          "nodes": _NODE_COUNT + 1,
                          "model": _GEMMA_MODEL}))
    print(f"\n{'='*60}")
    print(f"  GEMMA1 SWARM  |  {_NODE_COUNT} Workers + 1 Aggregator")
    print(f"  Model: {_GEMMA_MODEL}  |  Ollama localhost:11434")
    print(f"{'='*60}\n")

    # ── Model warm-up: pre-load Gemma into VRAM so workers don't hit cold-start 500s
    print("  [WARM-UP] Loading gemma3:4b into VRAM ...")
    warmup = _ollama_call(0, "Reply with exactly: READY", retries=5)
    print(f"  [WARM-UP] Ollama responded: {warmup[:40]!r}\n")
    _log.info(json.dumps({"event": "WARMUP_DONE", "response": warmup[:40]}))

    # ── Fan-out (serialized to 1 at a time — Ollama can only run one 3.3 GB
    # instance at a time; max_workers=1 avoids the HTTP-500 overload while
    # preserving the logical fan-out/fan-in swarm architecture.)
    t_fan_out = time.monotonic()
    worker_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {pool.submit(_worker_node, i): i for i in range(1, _NODE_COUNT + 1)}
        for fut in as_completed(futures):
            result = fut.result()
            worker_results.append(result)
            if result["parsed"] is None:
                tag = "[FAIL]"
                val = "PARSE_FAIL"
            elif result["correct?"]:
                tag = "[OK]  "
                val = f"{result['parsed']:,}"
            else:
                tag = "[ERR] "
                val = f"{result['parsed']:,}"
            print(f"  {tag} Node {result['node_id']:>2}  |  "
                  f"{result['problem']}  ->  "
                  f"Gemma: {val}  "
                  f"(correct: {result['correct']:,})  "
                  f"[{result['latency_ms']:,}ms]")

    fan_out_ms = int((time.monotonic() - t_fan_out) * 1000)
    worker_results.sort(key=lambda r: r["node_id"])

    correct_count = sum(1 for r in worker_results if r["correct?"])
    print(f"\n  Workers done in {fan_out_ms:,}ms  |  "
          f"{correct_count}/{_NODE_COUNT} correct\n")

    # ── Fan-in: aggregator node 11 ────────────────────────────────────────────
    print(f"{'─'*60}")
    print(f"  NODE 11 (Aggregator) -- computing mean over {_NODE_COUNT} worker answers …")
    print(f"{'─'*60}")

    agg = _aggregator_node(worker_results)

    print("\n  Gemma11 full reply:\n")
    for line in agg.get("gemma_full_reply", "NO REPLY").splitlines():
        print(f"    {line}")

    print(f"\n{'='*60}")
    print("  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Workers polled   : {agg.get('worker_count', 0)}")
    print(f"  Python average   : {agg.get('python_average', 0):,.2f}")
    print(f"  Gemma11 average  : {agg.get('gemma_average', 'PARSE_FAIL')}")
    print(f"  Aggregator calls : {agg.get('latency_ms', 0):,}ms")
    print(f"{'='*60}\n")

    # ── Write artifacts ───────────────────────────────────────────────────────
    ts        = time.strftime("%Y%m%dT%H%M%S")
    report    = {
        "session_ts":       ts,
        "model":            _GEMMA_MODEL,
        "worker_results":   worker_results,
        "aggregator":       {k: v for k, v in agg.items()
                             if k != "gemma_full_reply"},  # keep JSON clean
        "aggregator_reply": agg.get("gemma_full_reply", ""),
        "python_avg_verified": agg.get("python_average"),
    }
    out_path  = _ARTIFACTS / f"gemma1_run_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _log.info(json.dumps({"event": "ARTIFACT_WRITTEN", "path": str(out_path)}))
    print(f"  📄 Artifact -> {out_path.relative_to(_ROOT)}\n")


if __name__ == "__main__":
    main()
