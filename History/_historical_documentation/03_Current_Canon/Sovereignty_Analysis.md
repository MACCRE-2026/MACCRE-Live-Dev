# MACCREv2 Zero-Dependency Sovereignty Analysis

> Generated: 2026-04-16 | Status: Strategic Assessment — Awaiting User Decision

---

## Executive Summary

The goal is **achievable**, but must be understood as a **multi-year strangler fig** — not a single sprint.
The current venv contains **189 installed packages** totalling **~961 MB**.
MACCREv2 source code itself **only actively imports 12 distinct third-party packages**.
This gap is the central insight: the bloat is almost entirely **transitive dependencies of those 12**.

---

## What MACCREv2 Actually Uses (The True Surface)

| Package | Used In | Role | Replaceable? | Effort |
|---|---|---|---|---|
| `google-genai` | 11 files | Gemini API client | ✦ Thin HTTP wrapper | **Low** |
| `pydantic` | 4 files | Schema validation + AgentResponse | ✦ Pure Python | **Medium** |
| `chromadb` | 3 files | Vector store (RAG) | ✦ Pure Python possible | **High** |
| `requests` | 3 files | HTTP to Ollama + Brave | ✦ Pure `urllib` | **Low** |
| `openpyxl` | 3 files | Excel workbook r/w | ✦ Pure Python | **Medium** |
| `google-auth-oauthlib` | 1 file | Drive OAuth2 | ✦ Pure HTTP PKCE | **Medium** |
| `win10toast` | 1 file | Toast notifications | ✦ `ctypes` WinAPI | **Very Low** |
| `watchdog` | 1 file | File system watcher | ✦ `ReadDirectoryChangesW` | **Low** |
| `anthropic` | 1 file | Optional: Claude models | ✧ Optional dep only | **Low** |
| `openai` | 1 file | Optional: GPT models | ✧ Optional dep only | **Low** |
| `groq` | 1 file | Optional: Groq models | ✧ Optional dep only | **Low** |
| `setuptools` | 1 file | Build tooling | ✧ Not runtime | **N/A** |

> ✦ = Core functionality  ✧ = Optional vendor client (lazy-imported, guarded)

---

## The Real Problem: Transitive Dependency Avalanche

The 12 packages above **pull in 177 additional packages**. Here's the cascade:

```
chromadb (54,247 lines Python source)
  └── onnxruntime, tokenizers, kubernetes, grpcio, uvicorn,
      opentelemetry (full stack), numpy, pyarrow, mmh3,
      bcrypt, rich, typer, pydantic-settings, httpx, orjson...

google-genai (86,920 lines Python source)
  └── google-auth, httpx, anyio, sniffio, websockets,
      tenacity, pydantic...

pydantic (37,228 lines Python source — includes pydantic_core in Rust)
  └── pydantic-core (written in Rust, compiled C extension — NOT Python)
      annotated-types, typing-extensions, typing-inspection
```

**The hard constraint:** `pydantic-core` and `onnxruntime` contain compiled native extensions (.pyd / .dll files).
They cannot be "vendored as Python source" — they are pre-compiled binaries for a specific Python version + architecture.

---

## Feasibility Assessment: Vendoring vs. Native Replacement

### Part 1: Vendoring (Pulling Sources In-House)

**What vendoring actually means:**
Copy the package source into `maccre_core/_vendor/` and import from there instead of site-packages.
This is how `pip` itself, `requests`, and `boto3` are distributed.

**What is feasible to vendor (pure Python only):**

| Package | Can Vendor? | Source Size | Notes |
|---|---|---|---|
| `requests` | ✅ YES | ~5,000 lines | Pure Python; certs are separate |
| `openpyxl` | ✅ YES | ~25,000 lines | Pure Python + et-xmlfile |
| `watchdog` | ✅ YES | ~10,000 lines | Has optional C extension but works without |
| `win10toast` | ✅ YES | ~600 lines | Tiny; wraps ctypes |
| `google-genai` | ⚠️ PARTIAL | 86,920 lines | Depends on requests, httpx — chain continues |
| `chromadb` | ❌ NO | 54,247 lines | Requires onnxruntime (compiled Rust/C) |
| `pydantic` | ❌ NO | 37,228 lines | Core is compiled Rust (`pydantic-core`) |
| `anthropic/openai/groq` | ✅ YES | Small clients | All pure Python but chain pulls httpx etc. |

**Bottom line on vendoring:** You can vendor the small pure-Python packages trivially.
For `chromadb` and `pydantic`, vendoring the Python layer while keeping the compiled core
is possible but doesn't eliminate the binary dependency — it just internalizes the Python wrapper.

---

### Part 2: Native Replacement (The Sovereignty Endgame)

This is where the real conversation lives. Here is an honest tier-by-tier assessment:

#### 🟢 **Tier 1 — Replace Now (1-2 weeks each, low risk)**

| Package | Native Replacement | Path |
|---|---|---|
| `requests` | `urllib.request` + context managers | Already partially done in Ollama calls |
| `win10toast` | `ctypes` → `WinToastLib` API direct | 60 lines of ctypes |
| `watchdog` | `ctypes` → `ReadDirectoryChangesW` | Single API call in a thread |
| `python-dotenv` | Not used directly — already using vault | Remove |
| `toml`, `PyYAML` | `tomllib` (stdlib 3.11+) / use json | Stdlib already covers it |

#### 🟡 **Tier 2 — Replace in 1-3 months (medium complexity)**

| Package | Native Replacement | Path |
|---|---|---|
| `openpyxl` | Pure Python OOXML writer (zip + XML) | xlsx is just a zip file with XML inside. A write-only sovereign implementation is ~800 lines |
| `google-genai` | Direct `urllib` REST calls to Gemini API | The API is documented. Our router already knows the endpoints. Eliminates 86,920 lines |
| `google-auth-oauthlib` | Direct OAuth2 PKCE flow via `urllib` + `webbrowser` | ~300 lines, token stored in vault |
| `anthropic/openai/groq` | Already thin wrappers — replace with direct HTTP | Each client is just an HTTP wrapper. ~100-200 lines per vendor |

#### 🔴 **Tier 3 — Long-term research (6-18 months, high complexity)**

| Package | Sovereignty Challenge | Realistic Path |
|---|---|---|
| `pydantic` | Core is Rust-compiled; Python validation would be 5-10x slower | Write a `SovereignSchema` class using `dataclasses` + `__post_init__` validation. Sufficient for our AgentResponse use case |
| `chromadb` | Vector search requires math-heavy embedding distance (cosine similarity); storage layer is SQLite underneath | Replace storage with SQLite FTS5 + our own embedding model. **The real problem is the embedding model itself** |
| `onnxruntime` | Used by chromadb for sentence embedding inference | For the S25: use `google-ai-edge` SDK for on-device inference, or call Ollama via HTTP (no binary dep) |

#### ⚫ **Tier 4 — The Irreducible Core**

These cannot be "natively replaced" — they are the physics layer:

| Package | Why Irreducible |
|---|---|
| `grpcio` | Compiled C extension. Google's internal protobuf wire format. Only needed because chromadb uses it. Eliminated when chromadb is replaced |
| `cryptography` / `cffi` | Compiled C. Powers secure vault ops. Can switch to `ssl` stdlib + Windows CNG via ctypes |
| `protobuf` | Compiled. Eliminated when google-genai is replaced with direct HTTP |
| `numpy` | Compiled Fortran/C. Used only by chromadb. Eliminated when chromadb is replaced |

**Key insight:** Almost everything in Tier 4 goes away as a side effect of replacing `chromadb` and `google-genai`.

---

## The S25 / On-Device Model Consideration

For the Samsung S25 deployment, the picture changes significantly:

- **Google AI Edge SDK** (`ai-edge-torch`, `mediapipe`) would replace both `google-genai` AND `onnxruntime` for local inference
- The S25's NPU (Snapdragon X Elite equivalent) runs `.tflite` and `.task` models natively
- This means our sovereign embedding layer should be **a local Gemma 3 model via Ollama HTTP** (already in the router), not a chromadb/onnxruntime stack
- **The sovereignty endgame for the S25 is:** `sqlite3` (stdlib) + `Ollama HTTP` (one pure Python HTTP call) + `urllib` = zero binary deps for core intelligence

---

## The Recommended Execution Strategy: Phased Strangler Fig

> **Rule:** Never break a working system. Replace one thing at a time behind the existing interface.

### Phase A — Immediate (this week): Lock the dependency surface
1. Create `requirements-sovereign.txt` with only the 12 actually-used packages (pinned)
2. Create `requirements-optional.txt` for anthropic/openai/groq (guarded, not auto-installed)
3. Remove all GUI/Flet/Streamlit/Textual packages from requirements.txt — they are dead code
4. **Estimated removal:** ~40 packages, ~300 MB of venv weight gone

### Phase B — Short-term (next 2-4 weeks): Tier 1 replacements
1. Replace `requests` with native `urllib` wrapper (`maccre_core/_net/http_client.py`)
2. Replace `win10toast` with ctypes direct call
3. Replace `watchdog` with `ReadDirectoryChangesW` ctypes
4. Replace `python-dotenv`, `toml`, `PyYAML` with stdlib equivalents
5. Vendor `openpyxl` into `maccre_core/_vendor/openpyxl/`

### Phase C — Medium-term (1-2 months): Kill the big ones
1. Write `maccre_core/_net/gemini_client.py` — direct HTTP Gemini client replacing `google-genai`
2. Write `maccre_core/_net/drive_client.py` — direct HTTP Drive client replacing `google-auth-oauthlib`
3. Write `maccre_core/schemas/sovereign_schema.py` — `dataclasses` + validation replacing `pydantic`
4. **Result:** chromadb is now the only major remaining dep

### Phase D — Long-term (3-6 months): Replace chromadb
1. Write `maccre_core/rag/sovereign_store.py` backed by SQLite FTS5
2. Embeddings via Ollama HTTP (`/api/embeddings` endpoint — already serves nomic-embed-text)
3. Cosine similarity in pure Python (~10 lines)
4. **Result:** Zero compiled binary dependencies in the core path

---

## Direct Answer to Your Questions

**"How feasible is it to pull all dependency sources in-house?"**

For the **12 packages MACCREv2 actually uses:**
- 8 of them (requests, openpyxl, google-genai wrapper, auth, toast, watchdog, anthropic/openai/groq) can be vendored or replaced with pure Python within weeks
- 2 of them (pydantic, chromadb) have compiled Rust/C cores that cannot be vendored as source — they must be **replaced**, not vendored

For the **177 transitive packages:**
- The vast majority vanish automatically when their parent is replaced
- The compiled ones (grpcio, numpy, onnxruntime, protobuf) are all transitive deps of chromadb or google-genai — replace those two and ~150 packages evaporate

**"Is a plan to replace every single dependency with native code feasible?"**

**Yes — with one honest constraint:** "native" for cryptographic operations means `ctypes` to Windows CNG (native WinAPI), not reimplementing AES-256 in Python. That is the correct sovereign interpretation — you are not beholden to PyPI, but you are beholden to the OS security layer (which is appropriate and correct).

The S25 changes the picture cleanly: the target architecture is
`Python stdlib` + `Ollama HTTP` + `SQLite` + `Windows CNG via ctypes`.
That is a **completely achievable**, **fully sovereign** stack.

---

## Recommended Immediate Decision

Before executing anything, the three strategic decisions are:

> [!IMPORTANT]
> **Decision 1:** Do you want to vendor `openpyxl` immediately (copy source in-house), or replace it with a native OOXML writer? The native writer is ~800 lines and gives us full control of the workbook format.

> [!IMPORTANT]
> **Decision 2:** Do you want to replace `google-genai` with a direct HTTP client now? This is the single highest-leverage move — it eliminates protobuf, grpcio, google-auth, httpx, and ~50 transitive packages in one stroke. The Gemini REST API is fully documented and we already know all the endpoints from the router code.

> [!IMPORTANT]
> **Decision 3:** For the RAG layer — do you want to move to `Ollama embeddings + SQLite FTS5` now (eliminating chromadb entirely), or keep chromadb as a known-stable dependency while we build the sovereign replacement behind the `KnowledgeStore` ABC interface?
