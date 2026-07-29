# MACCREv2 Tool Registry — Complete Usage Guide
**Version:** Phase 12 (April 2026)
**Dispatcher:** `maccre_core/tools/tool_registry.py`
**Total Registered Tools:** 23 (+ router-level utilities)

> **Phase 12 Hardening Note:** All tool files have had `from __future__ import annotations` (PEP 563) permanently removed. Python 3.11 native type syntax is used throughout. The Google GenAI SDK requires real type objects — not string literals — to build OpenAPI schemas for automatic function calling. See `ReadMe.md` Law 12 for the full contract.

> **For LLM Agents:** All tools in `TOOL_DISPATCHER` are directly mountable via the Universal Router. Set the `Tools_Allowed` column in `topology.csv` to activate them on a node (pipe-separated, e.g. `read_file|write_file|query_local_memory`). All parameters are primitives (`str`, `int`, `float`, `bool`, `bytes`). No custom classes cross the LLM boundary.
> **For Developers:** Import any function directly from its source module or via `TOOL_DISPATCHER["tool_name"]` from `tool_registry.py`.

---

## Module 1: `text_tools.py`
**Purpose:** Pure, stateless text transformation. No I/O, no network calls. Flash-tier safe.

---

### `parse_json_response`
**Registry key:** `"parse_json_response"`

Strips Markdown code fences from a raw LLM output and parses the inner content as a JSON dictionary. Handles ` ```json ... ``` ` and bare ` ``` ... ``` ` wrappers.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `raw` | `str` | ✅ | The raw LLM response string, optionally wrapped in code fences |

**Returns:** `dict[str, Any]` — the parsed JSON object

**Raises:** `ValueError` if the content cannot be parsed as valid JSON

**Example:**
```python
from maccre_core.tools.text_tools import parse_json_response

result = parse_json_response('```json\n{"status": "ok", "score": 9}\n```')
# → {'status': 'ok', 'score': 9}
```

---

### `build_system_instruction`
**Registry key:** `"build_system_instruction"`

Composes a flat key-value dictionary into a multiline `Key: Value` system prompt string. Empty values are silently omitted.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `fields` | `dict[str, str]` | ✅ | Ordered mapping of label → content |

**Returns:** `str` — multiline system instruction string

**Example:**
```python
result = build_system_instruction({"Role": "Analyst", "Tone": "precise", "Language": ""})
# → "Role: Analyst\nTone: precise"
```

---

### `truncate_history`
**Registry key:** `"truncate_history"`

Returns the most recent `max_turns` entries from a conversation history list. Stateless — does not modify the original list.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `history` | `list[dict[str, str]]` | ✅ | Full conversation history |
| `max_turns` | `int` | ❌ | Maximum turns to retain. Default: `15` |

**Returns:** `list[dict[str, str]]` — trimmed history slice

---

### `format_cost_str`
**Registry key:** `"format_cost_str"`

Formats a raw float API cost into a human-readable dollar string for ledger output.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `cost` | `float` | ✅ | Raw cost in USD (e.g. `0.000123456`) |

**Returns:** `str` — e.g. `"$0.000123"`

---

## Module 2: `audio_tools.py`
**Purpose:** Raw audio byte manipulation for the TTS pipeline. No network calls.

---

### `pack_wav_bytes`
**Registry key:** `"pack_wav_bytes"`

Wraps raw 16-bit PCM bytes from the Google Native TTS API into a valid RIFF/WAV container.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `pcm` | `bytes` | ✅ | Raw PCM audio bytes from the TTS API response |
| `channels` | `int` | ❌ | Audio channels: `1` = mono, `2` = stereo. Default: `1` |
| `sample_rate` | `int` | ❌ | Sample rate in Hz. Default: `24000` (Google TTS native) |
| `sample_width` | `int` | ❌ | Bytes per sample: `2` = 16-bit. Default: `2` |

**Returns:** `bytes` — fully-formed WAV file including RIFF header

**Compatible TTS models (April 2026):** `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`

---

### `make_tts_filename`
**Registry key:** `"make_tts_filename"`

Generates a deterministic, filesystem-safe filename for a TTS audio clip. Same speaker + text always produces the same filename (SHA-256 hash suffix for disk-level caching).

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `speaker` | `str` | ✅ | Display name of the speaker |
| `text` | `str` | ✅ | The spoken text |
| `extension` | `str` | ❌ | File extension without dot. Default: `"mp3"` |

**Returns:** `str` — e.g. `"AI_Host_42e25dd386eb55b5.mp3"`

---

### `build_tts_config` *(Router-level utility, not in TOOL_DISPATCHER)*
Builds a `types.GenerateContentConfig` for Google Native TTS output. Does NOT call the API.

**Compatible models:** `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`

> ⚠️ `gemini-2.5-pro` does **NOT** support `response_modalities=["AUDIO"]` on the Developer API tier. Always use the dedicated `-preview-tts` models.

---

## Module 3: `media_tools.py`
**Purpose:** Media pipeline assembly. Produces FFmpeg-ready command arrays and JSON manifests.

---

### `build_concat_manifest`
**Registry key:** `"build_concat_manifest"`

Takes a list of speaker log dicts and returns an indexed production manifest with guaranteed key structure.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `logs` | `List[Dict[str, Any]]` | ✅ | List of speaker dicts with `"speaker"`, `"audio"`, and optional `"video_prompt"` |

**Returns:** `List[Dict[str, Any]]` — ordered manifest with `index` added

---

### `build_ffmpeg_cmd`
**Registry key:** `"build_ffmpeg_cmd"`

Constructs a complete FFmpeg `filter_complex concat` command list from a production manifest. Returns a `subprocess.run`-ready argument list.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `manifest` | `List[Dict[str, Any]]` | ✅ | Ordered manifest from `build_concat_manifest` |
| `output_path` | `str` | ✅ | Absolute path of the desired output video file |
| `ffmpeg_path` | `str` | ❌ | Path to FFmpeg executable. Default: `"ffmpeg"` |
| `placeholder_video` | `str` | ❌ | Fallback video for missing `"video"` keys |

**Returns:** `List[str]` — complete FFmpeg command as a list of strings

> ℹ️ For end-to-end renders, use `execute_render_pipeline` instead — it handles the full 2-pass stitch internally.

---

### `save_manifest`
**Registry key:** `"save_manifest"`

Accepts a JSON-encoded string of the manifest, deserializes it, and writes it to disk as a formatted JSON file.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `manifest_json` | `str` | ✅ | JSON-encoded string of the manifest list |
| `dest` | `str` | ✅ | Absolute path for the output JSON file |

**Returns:** `str` — absolute path of the written file

---

## Module 4: `agent_tools.py`
**Purpose:** Agent persona CRUD. All LLM-facing functions use `Dict[str, Any]`.

### `AgentRecord` Schema
```json
{
  "name":         "string (required) — unique display name",
  "persona":      "string (required) — role label e.g. 'The Host'",
  "model":        "string — Gemini/Claude/Ollama model ID. Default: 'gemini-2.5-flash'",
  "grounding":    "bool  — enable Google Search grounding. Default: true",
  "instructions": "string — full system directive. Default: ''"
}
```

---

### `load_agent_from_dict`
**Registry key:** `"load_agent_from_dict"`

Validates a plain dict against the `AgentRecord` schema and returns the normalized dict.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `data` | `Dict[str, Any]` | ✅ | Dict with at minimum `"name"` and `"persona"` |

**Returns:** `Dict[str, Any]` — normalized agent dict

---

### `load_agent_from_file`
**Registry key:** `"load_agent_from_file"`

Reads a JSON file from disk and deserializes it through `load_agent_from_dict`.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | `str` | ✅ | Absolute or relative path to a `.json` agent file |

**Returns:** `Dict[str, Any]` — normalized agent dict

---

### `save_agent_to_file`
**Registry key:** `"save_agent_to_file"`

Validates an agent dict, serializes it to `<directory>/<Agent_Name>.json`. Creates the directory if needed.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agent_data` | `Dict[str, Any]` | ✅ | Agent dict (see `AgentRecord` schema). Must include `"name"` |
| `directory` | `str` | ✅ | Target directory path as a string |

**Returns:** `str` — absolute path of the written file

---

### `request_scope_expansion`
**Registry key:** `"request_scope_expansion"`

Signals to the swarm orchestrator that the current agent requires access to a specialized resource or elevated privilege scope that was not declared in the original topology. Writes a structured expansion request to `system_logs.db` for the Quartermaster agent to reconcile.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agent_name` | `str` | ✅ | Registered name of the requesting agent |
| `requested_scope` | `str` | ✅ | Description of the resource or capability needed |
| `justification` | `str` | ✅ | Reasoning for why this scope is required |

**Returns:** `str` — confirmation message with the logged request ID

---

## Module 5: `storage_tools.py`
**Purpose:** Sovereign file I/O via the Strangler Fig `StorageManager` ABC. All paths relative to `B:/MACCREv2`.

---

### `read_file`
**Registry key:** `"read_file"`

Reads a file relative to `B:/MACCREv2` via the default `LocalDiskAdapter`.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | `str` | ✅ | Relative path from `B:/MACCREv2` (e.g. `"__DATACENTER/01_Raw_Source/brief.txt"`) |

**Returns:** `str` — file content as decoded UTF-8 text

---

### `write_file`
**Registry key:** `"write_file"`

Writes UTF-8 text to the given relative path. Creates parent directories automatically.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | `str` | ✅ | Relative path from `B:/MACCREv2` for the destination file |
| `data` | `str` | ✅ | Text content to write |

**Returns:** `None`

---

### `file_exists`
**Registry key:** `"file_exists"`

Checks whether a file exists at the given relative path.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | `str` | ✅ | Relative path from `B:/MACCREv2` |

**Returns:** `bool` — `True` if the file exists

---

## Module 6: `rag_tools.py`
**Purpose:** Sovereign Local RAG Engine. ChromaDB vector store + Ollama air-gapped embeddings. Zero cloud calls.

**Prerequisite:**
```bash
ollama pull nomic-embed-text
```

**DB Location:** `B:/MACCREv2/__DATACENTER/chroma_db` (auto-created on first use)

---

### `query_local_memory`
**Registry key:** `"query_local_memory"`

Embeds the query using local `nomic-embed-text`, cosine-searches the specified ChromaDB collection, and returns a ranked string of matching chunks with distance scores.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | `str` | ✅ | The search term or question to look up |
| `collection_name` | `str` | ❌ | ChromaDB collection to search. Default: `"swarm_memory"` |
| `n_results` | `int` | ❌ | Number of closest chunks to return. Default: `3` |

**Returns:** `str` — formatted results block or empty/error message

**Output format:**
```
--- RECOVERED MEMORIES ---
[Match Distance: 0.1234]
<chunk text>

[Match Distance: 0.2567]
<chunk text>
```

---

### `ingest_document`
**Registry key:** `"ingest_document"`

Embeds a text chunk via local Ollama and upserts it into ChromaDB. Idempotent — the same `doc_id` overwrites rather than duplicates.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `text` | `str` | ✅ | Raw text content to embed and store |
| `doc_id` | `str` | ✅ | Unique identifier for this document. Used as the ChromaDB upsert key |
| `collection_name` | `str` | ❌ | Target ChromaDB collection. Default: `"swarm_memory"` |

**Returns:** `str` — confirmation message with total doc count, or error string

---

### `query_foreign_memory`
**Registry key:** `"query_foreign_memory"`

Read-only semantic query of a linked foreign project's database via the Synaptic Bridge. Does NOT ingest into local memory. Fails if the `project_schema.json` does not whitelist the target project.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `target_project` | `str` | ✅ | The exact name of the foreign project |
| `query` | `str` | ✅ | The search term or concept |
| `n_results` | `int` | ❌ | Chunks to return. Default: `3` |

**Returns:** `str` — formatted results block

---

### `import_foreign_vectors`
**Registry key:** `"import_foreign_vectors"`

Selectively migrates highly relevant semantic vectors from a foreign project into the active DB's `synaptic_bridge` collection.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `target_project` | `str` | ✅ | The exact name of the foreign project |
| `query` | `str` | ✅ | The semantic search term |
| `relevance_threshold` | `float` | ❌ | Max cosine distance. Default is `1.0` (which blocks osmosis entirely). Set lower (e.g. `0.4`) to permit vector migration. |

**Returns:** `str` — migration summary

---

## Module 7: `telemetry_tools.py`
**Purpose:** RBAC-gated telemetry inspection for the Nexus agent and auditor roles. Reads from the four-silo WAL SQLite matrix. No writes.

---

### `read_local_codebase`
**Registry key:** `"read_local_codebase"`

Recursively reads all `.py` files under a given path (relative to `B:/MACCREv2`) and returns their concatenated content. Rate-limited by a max character count to prevent context window overflow.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | `str` | ✅ | Relative directory path to scan (e.g. `"maccre_core/tools"`) |
| `max_chars` | `int` | ❌ | Maximum total characters to return. Default: `50000` |

**Returns:** `str` — concatenated Python source with `# FILE: <path>` headers

---

### `query_telemetry_matrix`
**Registry key:** `"query_telemetry_matrix"`

Queries the `system_logs.db` telemetry silo for recent events matching an optional filter. Uses WAL read mode to avoid blocking active writers.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `action_type` | `str` | ❌ | Filter by action type (e.g. `"MEDIA_RENDER_COMPLETE"`, `"SWARM_ROUTE"`) |
| `limit` | `int` | ❌ | Maximum rows to return. Default: `20` |

**Returns:** `str` — JSON-formatted array of matching log events

---

### `query_thoughts`
**Registry key:** `"query_thoughts"`

Queries the `thoughts.db` scratchpad silo for agent reasoning traces. Allows the Nexus agent to audit what any agent was thinking during a prior inference.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `agent_name` | `str` | ❌ | Filter by agent display name |
| `limit` | `int` | ❌ | Maximum rows to return. Default: `10` |

**Returns:** `str` — JSON-formatted array of thought records

---

### `export_and_purge_thoughts`
**Registry key:** `"export_and_purge_thoughts"`

Exports all current `thoughts.db` contents to a timestamped JSON file in `03_Agent_Ledgers`, then truncates the live database. Used by the Quartermaster at the end of a swarm cycle to persist the cognitive audit trail before clearing the hot silo.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_label` | `str` | ✅ | Human-readable label for the export file (e.g. `"MEGA_TEST_CYCLE_01"`) |

**Returns:** `str` — absolute path of the exported JSON file

---

## Module 8: `finops_tools.py`
**Purpose:** Pre-flight cost estimation and post-call media render cost accounting. Implements the 2026 pricing matrix with wildcard model matching.

---

### `estimate_manifest_cost`
**Registry key:** `"estimate_manifest_cost"`

Pre-flight DAG cost estimator. Calculates the projected USD cost for a media render batch before any API calls are made, using scene count and average TTS character count.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `manifest_json` | `str` | ✅ | JSON-encoded Director manifest array |
| `image_model` | `str` | ❌ | Image model name for cost lookup. Default: `"imagen"` |

**Returns:** `str` — formatted cost estimate string (e.g. `"Estimated render cost: $0.42 (13 images, 4820 TTS chars)"`)

---

### `calculate_media_cost` *(internal — called by render executor)*
Post-call USD cost calculator for a completed render batch. Uses substring wildcard matching on `MEDIA_PRICING_MATRIX` so pricing survives model version bumps.

**Pricing Matrix (April 2026):**
```python
MEDIA_PRICING_MATRIX = {
    "imagen":              0.03,     # USD per image — wildcard: matches imagen-4.0, imagen-5.0, etc.
    "tts":                 0.00005,  # USD per character — matches any gemini-*-preview-tts model
    "gemini-2.5-pro-audio": 0.00005, # legacy key (backwards compat)
}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `num_images` | `int` | ✅ | Number of images generated |
| `tts_text_length` | `int` | ✅ | Total character count of all TTS text |
| `image_model_used` | `str` | ❌ | Model name string (wildcard-matched). Default: `"imagen"` |

**Returns:** `float` — total cost in USD

---

## Module 9: `render_executor.py`
**Purpose:** Dual-pipeline Media Render Executor. Consumes Director JSON manifest, routes generation to `CloudMediaPipeline` or `LocalMediaPipeline`, executes concurrent TTS, rate-limited sequential Imagen, and Edge FFmpeg 2-pass stitch.

**Architecture:**
```
Director JSON Manifest
        │
        ▼
CloudMediaPipeline.generate_audio()  ← gemini-2.5-pro-preview-tts (concurrent)
CloudMediaPipeline.generate_image()  ← imagen-4.0-fast-generate-001 (sequential, rate-limited)
        │                   ↑
        │           404 → Epoch Drift Self-Heal → active_image_model updated
        │                   └─ UDP hook → dashboard:5555
        ▼
FFmpeg Pass 1: scene image+audio → clip_NNN.mp4  (per-scene)
FFmpeg Pass 2: clips_concat.txt → podcast_output.mp4  (stitch)
        │
        ▼
FinOps Injection → system_logs.db (MEDIA_RENDER_COMPLETE)
```

---

### `execute_render_pipeline`
**Registry key:** `"execute_render_pipeline"`

Synchronous entry point. Parses a Director manifest, generates all TTS audio (concurrent) and visual assets (sequential with backoff), then stitches via FFmpeg 2-pass. Wraps the internal `asyncio` coroutine — safe to call from any context.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `manifest_json` | `str` | ✅ | JSON-encoded string of the Director manifest array. Each entry must have `"speaker"`, `"text"`, and `"video_prompt"` keys |

**Returns:** `str` — `"SUCCESS: Render Complete at <absolute_path>"` on success

**Raises:** `RuntimeError` if no valid scene clips are generated; `CalledProcessError` if FFmpeg fails

**Output files (written to `05_Rendered_Media/`):**
- `audio/scene_NNN.wav` — per-scene TTS audio
- `visuals/scene_NNN.jpg` — per-scene Imagen frame
- `segments/clip_NNN.mp4` — per-scene encoded clip
- `podcast_output.mp4` — final stitched production

**Example:**
```python
import json
from maccre_core.tools.render_executor import execute_render_pipeline

manifest = [
    {"speaker": "Host", "text": "Welcome to the show.", "video_prompt": "Studio interior, warm lighting"},
    {"speaker": "Guest", "text": "Thanks for having me.", "video_prompt": "Close-up portrait, bokeh background"},
]
result = execute_render_pipeline(json.dumps(manifest))
# → "SUCCESS: Render Complete at B:\MACCREv2\__DATACENTER\05_Rendered_Media\podcast_output.mp4"
```

**Rate-limiting notes:**
- TTS: No RPM gate — all scenes fire concurrently
- Imagen: 15 RPM gate — sequential + 5s inter-call sleep + retry-after backoff on 429

---

## Module 10: `hybrid_search.py`
**Purpose:** High-throughput parallel web search via the Brave Search API.

**Prerequisite:** `BRAVE_SEARCH_API_KEY` must be set in Windows Credential Manager or `.env`.

---

### `execute_parallel_brave_search`
**Topology key:** `"brave_search"` in `Tools_Allowed` column

Accepts an array of query strings and executes them simultaneously via `ThreadPoolExecutor`, returning all results aggregated as a single formatted string.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `queries` | `list[str]` | ✅ | List of search query strings |
| `count_per_query` | `int` | ❌ | Results per query. Default: `3` |

**Returns:** `str` — all results joined by `====================` separators

---

## Orchestration: `tool_registry.py`
**Purpose:** Single import point for the entire tool ecosystem.

### Complete Tool Manifest (April 2026)

| Registry Key | Module | Tier | Description |
|---|---|---|---|
| `parse_json_response` | `text_tools` | heavy | Strip fences, parse JSON |
| `build_system_instruction` | `text_tools` | heavy | Compose key-value system prompt |
| `truncate_history` | `text_tools` | fast | Trim conversation history |
| `format_cost_str` | `text_tools` | fast | Format USD float to string |
| `pack_wav_bytes` | `audio_tools` | heavy | Wrap PCM bytes in WAV container |
| `make_tts_filename` | `audio_tools` | fast | Deterministic TTS filename |
| `build_concat_manifest` | `media_tools` | heavy | Build indexed scene manifest |
| `build_ffmpeg_cmd` | `media_tools` | heavy | Build FFmpeg command list |
| `save_manifest` | `media_tools` | heavy | Write manifest JSON to disk |
| `load_agent_from_dict` | `agent_tools` | fast | Validate and normalize agent dict |
| `load_agent_from_file` | `agent_tools` | heavy | Load agent JSON from disk |
| `save_agent_to_file` | `agent_tools` | heavy | Write agent JSON to disk |
| `request_scope_expansion` | `agent_tools` | fast | Signal scope expansion to orchestrator |
| `read_file` | `storage_tools` | fast | Read file relative to workspace root |
| `write_file` | `storage_tools` | fast | Write file relative to workspace root |
| `file_exists` | `storage_tools` | fast | Check file existence |
| `query_local_memory` | `rag_tools` | heavy | ChromaDB cosine search |
| `ingest_document` | `rag_tools` | heavy | ChromaDB upsert via Ollama embed |
| `query_foreign_memory` | `rag_tools` | heavy | Synaptic Bridge search across projects |
| `import_foreign_vectors` | `rag_tools` | heavy | Synaptic Bridge vector osmosis |
| `read_local_codebase` | `telemetry_tools` | heavy | Scan .py files, return concatenated source |
| `query_telemetry_matrix` | `telemetry_tools` | heavy | Query system_logs.db |
| `query_thoughts` | `telemetry_tools` | heavy | Query thoughts.db scratchpad silo |
| `export_and_purge_thoughts` | `telemetry_tools` | heavy | Export + truncate thoughts.db |
| `execute_render_pipeline` | `render_executor` | heavy | Full end-to-end media render |
| `estimate_manifest_cost` | `finops_tools` | fast | Pre-flight USD cost estimate |

### Key Exports

| Export | Type | Description |
|--------|------|-------------|
| `TOOL_REGISTRY` | `list[Callable]` | All tools as a flat list for direct SDK injection |
| `TOOL_DISPATCHER` | `dict[str, Callable]` | Name → callable map for dynamic tool resolution |
| `get_tools_from_sheet(tools_str)` | `fn` | Resolves a pipe- or comma-separated string of tool names |
| `get_tools_for_tier(tier)` | `fn` | Returns `"heavy"` or `"fast"` tool subsets |
| `generate_universal_json_schema(func)` | `fn` | Translates any callable into Anthropic/Ollama-compatible JSON Schema |

### `get_tools_from_sheet`
Accepts **pipe-separated** (canonical) or comma-separated (legacy) strings from `topology.csv`:

```python
tools = get_tools_from_sheet("read_file|write_file|query_local_memory")
# → [read_file, write_file, query_local_memory]
```

### `get_tools_for_tier`
```python
heavy_tools = get_tools_for_tier("heavy")  # Pro-class tools
fast_tools  = get_tools_for_tier("fast")   # Flash-class tools
all_tools   = get_tools_for_tier("any")    # Full registry
```

---

## Topology CSV Integration

To activate tools on a swarm node, set the `Tools_Allowed` column in `topology.csv`:

```csv
Node_ID,Prompt,Success_Target,Failure_Target,Wait_For,Temperature,Tools_Allowed,Model
RAG_NODE,THE_NEXUS,ANALYZE,FAILED,none,0.3,query_local_memory|ingest_document,gemini-2.5-flash
WRITE_NODE,THE_ARCHIVIST,DONE,FAILED,none,0.1,write_file|save_agent_to_file,gemma3:9b
RENDER_NODE,THE_DIRECTOR,DONE,FAILED,none,0.1,execute_render_pipeline|estimate_manifest_cost,gemini-2.5-pro
AUDIT_NODE,THE_NEXUS,DONE,FAILED,none,0.2,query_telemetry_matrix|query_thoughts|read_local_codebase,gemini-2.5-pro
```

The `UniversalRouter.generate()` method calls `get_tools_from_sheet(tools_str)` automatically before dispatching to Gemini, Claude, or Ollama.

---

## Developer Setup Checklist

```bash
# 1. Clone and activate venv
cd B:\MACCREv2
python -m venv .venv && .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull Ollama models (required for local RAG + edge routing)
ollama pull nomic-embed-text
ollama pull gemma3:9b

# 4. Store API credentials in Windows Credential Manager
#    Target: MACCRE_Sovereign  → Value: <your Google AI Studio API key>
#    Target: BRAVE_SEARCH_API_KEY → Value: <your Brave key>

# 5. Install FFmpeg (required for render_executor)
winget install --id Gyan.FFmpeg --silent --accept-package-agreements

# 7. Start the Global Nexus Agent CLI
python maccre.py chat

# 8. Start the Native MCP Integration Server
python maccre_mcp.py
```

### Module 11: `admin_tools.py`
**Purpose:** Meta-orchestration tools utilized specifically by the Global Nexus Agent CLI and the `maccre_mcp.py` loop to govern the Swarm via natural language.

| Registry Key | Description |
|---|---|
| `mint_agent` | Validates and constructs new `.json` profiles in the `agent_roster.csv` |
| `build_topology` | Constructs the `topology.csv` DAG flow map |
| `link_projects` | Mutates `project_schema.json` to permit Synaptic Bridge vector access |
| `ignite_swarm` | Injects a payload pointer into the `swarm_queue.db` via `local_broker.py` to start a run |

---

## Security Notes
- All tools are **primitive-typed at LLM boundaries** — no custom classes or ABCs cross the schema boundary.
- File I/O tools use paths **relative to `B:/MACCREv2`** via `LocalDiskAdapter`. Absolute paths outside the workspace will be rejected.
- RAG embedding is **100% local** — `nomic-embed-text` runs on the Ollama localhost server. No text is sent to a cloud embedding API.
- API keys are fetched from **Windows Credential Manager** (`advapi32.dll` via `ctypes`), never from `.env` files.
- The `execute_render_pipeline` tool performs **live cloud API calls** (Gemini TTS + Imagen) and will incur costs. Use `estimate_manifest_cost` for pre-flight budgeting.
- `export_and_purge_thoughts` **destroys** the live `thoughts.db` hot silo after export — ensure the export path is confirmed before calling.


---

---

# Phase 15–18 Tool Additions
**Version:** Updated April 2026 — Phases 15–18 (Diamond Loop, Spreadsheet Pipeline, Admin Expansion)
**New registered tools:** 8 (total now: 32)

---

## Module 12: `design_tools.py`
**Purpose:** Diamond Loop Swarm Design Engine. Converts natural language into fully materialised MACCRE swarms, or produces a portable xlsx specification file.

---

### `design_swarm`
**Registry key:** `"design_swarm"`

Full Diamond Loop execution. Leg 1 (gemini-2.5-pro, temp=1.0) performs creative swarm architecture ideation. Leg 2 (gemini-2.5-pro, temp=0.1) extracts a verified `SwarmDesign(BaseModel)` via `response_schema`. A JSON repair loop using gemini-2.5-flash recovers from truncated responses before propagating a DESIGN_FAULT.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `description` | `str` | YES | Natural-language description of what the swarm should do |
| `answers` | `str` | NO | Follow-up answers to a previous `[DESIGN_NEEDS_INPUT]` response |

**Returns:**
- `[SWARM_READY] Project **<NAME>** ...` — fully materialised, ready to ignite
- `[DESIGN_NEEDS_INPUT] ...` — clarifying questions, swarm not yet materialised
- `[DESIGN_FAULT] ...` — Diamond Loop failed after repair attempt

**Nexus routing:** Call immediately when a user describes a swarm. Let `design_swarm` handle clarification internally.

---

### `fill_swarm_sheet`
**Registry key:** `"fill_swarm_sheet"`

Same Diamond Loop as `design_swarm`, but also writes the materialised specification to a portable `MACCRE_Swarm_Request.xlsx` file openable in Google Sheets, editable, and droppable into the Drive Inbox for execution from any device.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `description` | `str` | YES | Natural-language swarm description |
| `answers` | `str` | NO | Follow-up clarification answers |
| `xlsx_path` | `str` | NO | Output path. Blank = auto-generate in GLOBAL/04_Code_Artifacts/ |

**Returns:**
- `[SWARM_READY] ... [SHEET_READY] Portable xlsx spec written: <path>` on full success
- `[DESIGN_NEEDS_INPUT]` propagated unchanged if clarification needed
- `[NOTE] xlsx export failed: ...` — swarm materialised but xlsx write failed (non-fatal)

**Nexus routing:** Prefer over `design_swarm` when user mentions spreadsheet, xlsx, portable file, or mobile configuration.

---

## Module 13: `sheet_parser.py`
**Purpose:** Parses `MACCRE_Swarm_Request.xlsx` workbooks into verified internal types and materialises project workspaces. Replaces direct `agent_roster.csv` + `topology.csv` writes as the primary intake path.

**Parser contract:**
- Row 1 (title) always skipped.
- Row 2 (column headers) normalised: `★ AGENT_NAME` → `AGENT_NAME`. Order-independent.
- Data begins at Row 3. Empty rows silently skipped.
- `ParsedWorkbook` contains: `agents: list[AgentDesign]`, `topology: list[NodeDesign]`, `agent_extras: dict[str, AgentExtra]` (extended AI Studio params), `pipeline_config`, `memory_config`, `vault_refs`.

---

## Module 14: `drive_watcher.py`
**Purpose:** Google Drive Sovereign Inbox Daemon.

**Activation:** `python maccre.py watch [--inbox <path>]`

**Event sequence:** DETECTED → PARSE → MATERIALISE → IGNITE → RUN_STARTED → RUN_COMPLETE

**Telemetry:** All events written to `GLOBAL/03_Agent_Ledgers/watcher_telemetry.json`.

---

## Module 11 (Updated): `admin_tools.py` — Phase 15+ Additions

| Registry Key | Description |
|---|---|
| `run_swarm` | Executes full swarm for active project; polls queue until complete |
| `create_persona_card` | Writes ROM cartridge JSON to `02_Dynamic_Context/<agent>.json` |
| `initialize_workspace` | Creates 5-tier project silo + copies blank template into project root (Phase 20) |

---

## Updated Tool Manifest (April 2026, Phase 19)

| Registry Key | Module | Phase | Description |
|---|---|---|---|
| `trash_file` | `storage_tools` | 14 | Soft-delete to __TRASH_BIN |
| `prune_semantic_memory` | `rag_tools` | 14 | ChromaDB pruning |
| `switch_workspace` | `admin_tools` | 14 | Switch active project silo |
| `initialize_workspace` | `admin_tools` | 14 | Create project silo |
| `promote_topology_to_library` | `admin_tools` | 14 | Save topology to library |
| `recall_topology` | `admin_tools` | 14 | Load saved topology |
| `generate_telemetry_report` | `telemetry_tools` | 14 | Full session audit report |
| `rotate_logs` | `logger` | 14 | Rotate log files |
| `request_elevation` | `access_control` | 14 | PIN-gated elevation |
| `design_swarm` | `design_tools` | 15 | Diamond Loop -> materialise swarm |
| `run_swarm` | `admin_tools` | 15 | Execute queued swarm nodes |
| `create_persona_card` | `admin_tools` | 15 | Write agent ROM cartridge |
| `fill_swarm_sheet` | `design_tools` | 17 | Diamond Loop -> portable xlsx spec |

**Total registered tools: 32**

---

## Updated Developer Setup Checklist (Phase 19)

```powershell
# 1. Activate venv
cd B:\MACCREv2
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull Ollama models
ollama pull gemma3:9b

# 4. Set API credentials in Windows Credential Manager
#    MACCRE_Sovereign = Google AI Studio API key

# 5. Install FFmpeg
winget install --id Gyan.FFmpeg --silent --accept-package-agreements

# 6. Google Drive junction (one-time, Admin terminal)
cmd /c mklink /J "G:\My Drive\__DataCenter" "B:\MACCREv2\__DATACENTER"

# 7. Generate base spreadsheet template
python scripts/generate_template.py

# 8. Start Nexus
python maccre.py chat

# 9. Start Drive Inbox Watcher (separate terminal)
python maccre.py watch

# 10. Sync project memory from Drive (Phase 19+)
python maccre.py sync --project <PROJECT_NAME>
```
