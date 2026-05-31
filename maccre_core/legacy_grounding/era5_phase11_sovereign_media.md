# Era 5: Phase 11 — Sovereign Media Pipeline & Self-Healing Render Executor (April 2026)

## Chronological Abstract

Phase 11 represents the first fully-automated **end-to-end media production run** in MACCREv2 history — a 6-phase DAG that ingests raw source material, routes it through five specialist agents, generates a Gemini-structured JSON media manifest, synthesizes 15 TTS audio clips concurrently, auto-resolves a live Imagen API epoch drift event, generates 15 visual frames, and stitches the entire production into a final `podcast_output.mp4` via a 2-pass FFmpeg pipeline — all without human intervention.

### Key Milestones (Chronological)

| Date | Milestone |
|---|---|
| Mar 30–31, 2026 | Factory Reset & Forensic Burn-In: `factory_reset.py` (zero-data-loss pre-flight archive) + `burn_in_test.py` (4-phase lifecycle validation) |
| Mar 31, 2026 | Persona Bootstrapping: `bootstrap_personas.py` — OSINT persona injection + `Refined_Prompts.txt` parser (supports `#( )#` custom delimiters) |
| Mar 31, 2026 | Forge-Smith Meta-Orchestrator rewrite: stateful HITL proposal/deployment loop with `ForgeProposal` Pydantic Structured Output, conversation history, and UDP `DEPLOY_TOPOLOGY` wake packet |
| Mar 31 PM, 2026 | `render_executor.py` v1: `CloudMediaPipeline` + `LocalMediaPipeline` ABC stubs, asyncio-concurrent TTS + Imagen, Edge FFmpeg stitch |
| Apr 1, 2026 | FinOps Engine expansion: `estimate_manifest_cost()` pre-flight estimator + `calculate_media_cost()` actuals with wildcard substring matching (`"imagen"` key matches any future Imagen version) |
| Apr 1, 2026 | Mega-Test Pipeline v1: `test_mega_pipeline.py` — 6-phase RAG-enabled DAG with per-node ledger persistence, async RAG tool-call loop, direct render pipeline await (no nested `asyncio.run()`) |
| Apr 2, 2026 | Self-Healing Epoch Drift: `CloudMediaPipeline.generate_image()` catches `404 NOT_FOUND`, calls `client.models.list()`, auto-selects `imagen-4.0-fast-generate-001`, emits UDP `MODEL_DRIFT_DETECTED` hook to dashboard port 5555 |
| Apr 2, 2026 | TTS Epoch Drift: discovered `gemini-2.5-pro` does not support `response_modalities=["AUDIO"]` on Developer API tier. Resolved to `gemini-2.5-pro-preview-tts` (dedicated TTS model, confirmed via `client.models.list()`) |
| Apr 2, 2026 | FFmpeg Installation: `winget install Gyan.FFmpeg` (v8.1). `FFMPEG_BIN` auto-resolver added to `render_executor.py` — uses `shutil.which()` then WinGet glob fallback |
| Apr 2, 2026 | Imagen Rate-Limiting Fix: replaced all-concurrent `asyncio.gather()` with **fully sequential** image generation + retry-after backoff parser (reads `retry in Xs` from 429 error body). TTS tasks remain concurrent |
| Apr 2, 2026 | FFmpeg 2-Pass Stitch: replaced single-pass flatten concat (exit code 69) with `Pass 1: per-scene image+audio → clip_NNN.mp4` then `Pass 2: concat all clips → podcast_output.mp4 (18MB)` |
| Apr 3, 2026 | **First Full Pipeline Success:** 15-scene podcast rendered end-to-end. Epoch Drift fired once (imagen-3.0 → imagen-4.0-fast), self-healed, all 15 clips stitched |

---

## Core Breakthroughs

### 1. Hardened Manifest Extractor (3-Tier Parse)
The Diamond Synthesizer's built-in `<compression_log>/<synthesis>` XML persona wrapping corrupted the Phase 5 media manifest call. The fix was dual:

1. **Bypass the compression persona entirely** — Phase 5 now uses a direct `client.models.generate_content()` call with `response_mime_type="application/json"` and a neutral Director system instruction. No persona → no XML wrapper.

2. **Defence-in-depth extractor** — a 3-tier parse chain:
   - Tier 1: Strip markdown fences, attempt direct `json.loads()` → validate `isinstance(result, list)`
   - Tier 2: `parse_json_response()` helper
   - Tier 3: Hard fail with a diagnostic `raw_output_preview[:500]` log entry

**Rule:** Never pass a synthesis persona into a structured-output generation call. Use dedicated Director system instructions for media manifest generation.

### 2. Self-Healing Epoch Drift Protocol
Any 404 on a cloud media model is now a **recoverable event**, not a crash:
```python
# CloudMediaPipeline.generate_image() — simplified
try:
    result = client.models.generate_images(model=self.active_image_model, ...)
except ClientError as e:
    if "404" in str(e) or "NOT_FOUND" in str(e):
        models = [m.name for m in client.models.list() if "imagen" in m.name.lower()]
        self.active_image_model = models[-1]  # newest available
        self._emit_gui_hook()                 # UDP → dashboard port 5555
        result = client.models.generate_images(model=self.active_image_model, ...)  # retry once
```

The `active_image_model` state persists across the entire render batch — the hook fires only once per drift event.

### 3. Sequential Image Generation with Retry-After Backoff
`asyncio.gather()` across 13–15 concurrent Imagen calls saturates the 15 RPM Developer API quota in under 4 seconds. The correct pattern:
- **TTS tasks:** Full concurrency — Gemini 2.0/2.5 TTS has no per-minute RPM issue at this scale.
- **Imagen tasks:** Fully sequential, 5-second inter-call sleep, plus exponential backoff that parses `retry in Xs` from the 429 error message body, adding 2 seconds of margin.

### 4. Two-Pass FFmpeg Stitch
The single-pass `concat` demux cannot handle alternating image+audio files. Correct architecture:
- **Pass 1:** For each scene, `ffmpeg -loop 1 -i image.jpg -i audio.wav -shortest → clip_NNN.mp4`
- **Pass 2:** `ffmpeg -f concat -safe 0 -i clips_concat.txt -c copy → podcast_output.mp4`

Scenes without a `video_prompt` use a `lavfi color=black` source for Pass 1.

---

## Model Discovery (April 2026) — Live API Catalogue Snapshot

Models confirmed available on the Developer API key as of April 2026:
```
gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash, gemini-2.0-flash-lite
gemini-2.5-flash-preview-tts, gemini-2.5-pro-preview-tts  ← dedicated TTS models
gemini-2.5-flash-native-audio-*        ← bidiGenerateContent only (streaming)
imagen-4.0-generate-001, imagen-4.0-ultra-generate-001, imagen-4.0-fast-generate-001
lyria-3-pro-preview                    ← music generation
gemini-3-pro-preview, gemini-3.1-pro-preview  ← next-gen available
```

**Critical API Tier Notes:**
- `gemini-2.5-pro` does **NOT** support `response_modalities=["AUDIO"]` on Developer API — use `gemini-2.5-pro-preview-tts`
- `imagen-3.0-generate-002` is **dead** on v1beta — auto-healed to `imagen-4.0-fast-generate-001`
- `imagen-4.0-fast-generate-001` has a **15 RPM** limit on paid Developer tier — enforce sequential generation

---

## Dead Ends & Spaghetti Warnings

- **Never pass a compression/synthesis persona into a structured-output media generation call.** The `<compression_log>` XML tags will corrupt the JSON output silently and produce an empty string that crashes the render executor downstream.
- **Never use `asyncio.run()` inside a coroutine.** The `_async_execute_render_pipeline` must be `await`-ed directly when called from inside an `async def` test function — no nesting.
- **Never fire all Imagen calls concurrently.** 15 concurrent requests against a 15 RPM quota will guarantee 429s. Sequential with sleep is the sovereign approach.
- **Never use the single-pass `concat` demux for mixed image+audio streams.** FFmpeg exit code 69 means invalid input mapping. Always use the 2-pass per-scene clip approach.
- **Never rely on `PATH` for FFmpeg immediately after `winget install`** — the shell session does not update `PATH`. Use `shutil.which()` with a WinGet glob fallback (`FFMPEG_BIN` constant).
- **Never hardcode Imagen model versions.** Use the `"imagen"` wildcard key in `MEDIA_PRICING_MATRIX` and the `active_image_model` state-driven retry to survive API version bumps transparently.
