# Era 6: Phase 12 — SDK Type Hardening & Tool Isolation (April 2026)

## Chronological Abstract

Phase 12 delivers full production stability for the automated function-calling pipeline. The root cause of the Phase 11 swarm instability was identified as a combination of three interacting runtime defects: SDK-level type introspection failures caused by Python's PEP 563 annotation deferral, event loop collisions between the Google GenAI SDK's internal `asyncio` runtime and the render pipeline's own coroutines, and markdown fence corruption passing raw LLM output directly into tool argument slots. All three are now permanently resolved.

### Key Milestones (Chronological)

| Date | Milestone |
|---|---|
| Apr 3–4, 2026 | Swarm Telemetry Isolation: per-job directory routing + `DualLogger` to capture agent-specific execution logs; sleep-state tracking to prevent log flooding |
| Apr 4, 2026 | Tool Execution Auditing: transparent audit trail replacing SDK automatic function calling black box |
| Apr 4, 2026 | `finops_tools.py` SDK Crash Fix: `estimate_manifest_cost` return type hardened to `str` (JSON-encoded); eliminates SDK `isinstance()` crash on parameterized generic types (`dict[str, float]`) during OpenAPI schema construction |
| Apr 4, 2026 | `render_executor.py` Thread Isolation: `execute_render_pipeline` now spawns a dedicated `threading.Thread` with its own `asyncio.run()` event loop, completely isolated from the SDK's internal loop |
| Apr 4, 2026 | Markdown Fence Strip: `re.sub(r"^```(?:json)?\s*|\s*```$", "", ...)` applied before JSON parse; catches LLM manifests passed with code fences in tool argument slots |
| Apr 4, 2026 | Two-Pass FFmpeg Stitch confirmed production-stable (first landed Phase 11); documented as the canonical render architecture |
| Apr 4, 2026 | **Type-String Purge:** `from __future__ import annotations` removed from all 12 tool and orchestration files. The PEP 563 shim converts type hints to string literals at module load, preventing the Google GenAI SDK from reading real `<class 'str'>` types when building function-calling schemas |
| Apr 4, 2026 | Forward-reference fix in `venv_executor.py`: `__enter__` return type migrated from forward-reference string `PersistentVenvShell` to `typing.Self` (Python 3.11 native, zero import shim required) |
| Apr 4, 2026 | `omni qa maccre_core/tools` — **Ruff + Pyright: PASS. Exit 0.** Full tools directory gates green. |

---

## Core Breakthroughs

### 1. PEP 563 Annotation Deferral — Root Cause of SDK Schema Crashes

`from __future__ import annotations` (PEP 563) was imported at the top of every tool file as a legacy typing convenience. It converts all type annotation strings to lazy-evaluated string literals at module load time. The Google GenAI SDK's automatic function calling feature uses Python's `inspect` module to read the actual type objects (`<class 'str'>`, `<class 'int'>`, etc.) from function signatures in order to construct OpenAPI-compatible JSON schemas. Under PEP 563, `inspect.get_annotations()` returns `{'manifest_json': 'str', 'return': 'str'}` — string literals — not `{'manifest_json': <class 'str'>, 'return': <class 'str'>}`. The SDK's `isinstance()` check against parameterized generics (e.g., `dict[str, float]`) raises `TypeError: Subscripted generics cannot be used with class and instance checks`, crashing the function-calling registration loop entirely.

**Resolution:** Hard delete `from __future__ import annotations` from all tool files. Python 3.11 natively supports all `list[T]`, `dict[K, V]`, and `X | Y` union syntax without the PEP 563 shim.

**Affected files (12 total):**
- `render_executor.py`, `finops_tools.py`, `tool_registry.py`, `text_tools.py`
- `telemetry_tools.py`, `storage_tools.py`, `search_tools.py`, `media_tools.py`
- `factory_reset.py`, `audio_tools.py`, `agent_tools.py`, `venv_executor.py`

### 2. Thread Isolation — Preventing Event Loop Collisions

The Google GenAI SDK initializes and manages its own `asyncio` event loop internally for streaming and async tool execution. When `execute_render_pipeline` called `asyncio.run(_async_execute_render_pipeline(...))` from within an already-running SDK event loop context, Python raised `RuntimeError: This event loop is already running`. 

**Resolution:** `execute_render_pipeline` spawns a new `threading.Thread`, and `asyncio.run()` is called inside the thread's `_thread_worker` function. Each thread owns a completely isolated event loop. The main thread blocks on `t.join()` until the render is complete, returning the result via a `result_container: list[str]` closure. The SDK loop and the render loop never share the same thread.

### 3. Markdown Fence Corruption

The LLM Director agent intermittently wraps its JSON manifest output in markdown code fences (` ```json\n...\n``` `), which is valid for human-readable display but invalid for `json.loads()`. When the manifest is passed as a tool argument to `execute_render_pipeline`, the fences pass through unmodified and crash the JSON parser.

**Resolution:** `re.sub(r"^```(?:json)?\s*|\s*```$", "", manifest_json.strip(), flags=re.MULTILINE)` is applied to `manifest_json` before any parsing. This is a one-way transformation applied on the synchronous entry point so all downstream async code receives clean JSON.

---

## OmniBuilder CI/CD Gate Results (April 4, 2026)

```
omni qa maccre_core/tools
→ Ruff Linter:           PASS
→ Pyright Type Checker:  PASS
→ Exit code: 0
```

**Non-negotiable standards confirmed:**
- All 12 tool files: zero unused imports, no wildcard imports, max line 120
- All function signatures: explicit Python 3.11+ native type hints (no string literals)
- `venv_executor.py`: self-referential return type uses `typing.Self` — zero forward reference strings

---

## Dead Ends & Spaghetti Warnings

- **Never use `from __future__ import annotations` in any file that registers tools with the Google GenAI SDK.** PEP 563 annotation deferral causes the SDK's OpenAPI schema builder to read string literals instead of real type objects, crashing the function-calling registration loop.
- **Never call `asyncio.run()` from a coroutine that may already be running inside an SDK-managed event loop.** Always isolate long-running async pipelines in dedicated `threading.Thread` workers with their own `asyncio.run()` instance.
- **Never pass raw LLM output directly into tool arguments without stripping markdown fences.** Apply `re.sub` fence stripping at the synchronous entry point before any JSON parsing.
- **Python 3.11 does not require `from __future__ import annotations`** for `list[T]`, `dict[K, V]`, `X | Y`, or `type | None` syntax. Remove it from all new files by default.
