# 2026-09-04: Memory, Embeddings and the Cost Surface — Measured

**Raised by:** operator questions during Era 3 tracker #9 (the payload contract), asking
whether pin-only vectorisation beats full-ledger vectorisation, what the embedding cost
difference is, how far off the breadcrumb-grounding design is, and what density-scaled
memory pins would cost.

**Method:** read the code. Where a number came from outside the repo it is cited. Nothing
here is recalled from training data — which is the point, because the operator's own
diagnosis is that the FinOps engine was built during a period when a coding assistant's
priors about Google's models were silently substituting for its documentation.

**Status of this document:** findings only. No code changed in producing it. The
consequences are split across Era 3 (immediate) and Era 4 (the memory overhaul) in §7.

---

## 1. The headline: embeddings are billed, and MACCRE records them as free

`maccre_core/tools/finops_tools.py:247-253`:

```python
_FREE_MODEL_KEYWORDS: tuple[str, ...] = (
    "gemma",             # all Gemma models are free via Gemini API
    "llama",             # local Ollama
    "gemini-embedding",  # embedding models are free
    "aqa",               # legacy QA model
)
```

`calculate_actual_cost` (`finops_tools.py:310-312`) short-circuits to `0.0` on a keyword
match, before any rate is consulted. `calculate_predicted_cost` does the same
(`finops_tools.py:339-341`).

**`gemini-embedding-001` is priced at $0.15 per 1M input tokens** — stated in
[Google's GA announcement for Gemini Embedding in the Gemini API](https://developers.googleblog.com/gemini-embedding-available-gemini-api/),
and corroborated by an independent
[pricing listing](https://futureagi.com/llm-cost-calculator/google/gemini-embedding-001)
which additionally gives the model's context window as **2,048 tokens**.
*(Content rephrased for compliance with licensing restrictions.)*

So the comment is false on the paid tier, and every embedding the system has ever issued
was billed and recorded as `$0.00`. This is the operator's diagnosed failure mode
precisely: embeddings *were* free during the preview period a 2024-2025-trained assistant
would have learned from, and the comment encodes that as a permanent fact.

**Compounding it, embeddings are not merely mis-priced — they are entirely outside the
accounting.** `EmbeddingResponse` (`gemini_client.py:155-160`) carries only `.values`;
there is **no `usage_metadata` on an embedding response at all**, so no token count exists
to bill from even if the keyword were removed. Fixing this requires estimating the token
count locally, which the repo cannot currently do (§5).

## 2. The 2,048-token window is a correctness problem, not a cost problem

`get_gemini_embedding` (`rag_tools.py:62-81`) is the single embedding entry point. It sets
**no `outputDimensionality`** — the request body is exactly
`{"model", "content", "taskType"}` (`gemini_client.py:576-580`) — and there is **no
chunking anywhere on the embed path**. `ingest_document` embeds a whole file in one call
(`rag_tools.py:120-140`).

A 68 KB unified ledger is roughly 17,000 tokens at ~4 chars/token. The API truncates at
2,048. Therefore:

> **The stored vector represents about 12% of the document, while the store returns 100%
> of its text.**

That is not inefficiency. It is a vector that misrepresents what it indexes, and a
semantic hit scored on the opening section is returned as though it matched the whole.
The codebase half-knows this: `fts_search_memory`'s docstring admits *"the embedding of the
first ~2000 tokens"* (`rag_tools.py:224-227`) and offers BM25 as the escape hatch rather
than chunking as the fix.

**Two further documentation falsifications found while establishing this:**

- **The "256-dim" claim is false.** `rag_tools.py:64` says "Generates a 256-dim embedding
  vector"; `README.md:89` and `MACCRE_Operator_Manual.md:132` repeat it. Nothing requests
  256 dimensions. The in-repo RadonVec measurement report
  (`Kiro_Antigravity-RadonVec_MACCRE-Collab/RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md:31`)
  found the live vectors in `nexus_memory.db` to be **3072-dimensional**. Storage is
  dimension-agnostic — `_vec_to_blob` packs `<{len(vector)}f` — which is why the mismatch
  never raised. Consequence: 12,288 bytes per vector, and 4× the pure-Python cosine work
  per row on a store that **full-scans the collection on every query**
  (`sovereign_store.py:262-296`).
- **Batching exists and is unused.** `GeminiClient.batch_embed_contents`
  (`gemini_client.py:593-628`) hits `:batchEmbedContents` and has **no caller anywhere**.
  Every embedding is one serial HTTP round-trip.

## 3. Pins are not vectorised at all

The operator's model was "we only vectorise memory_pins, not full ledgers." The code does
the opposite of both halves.

**The pin table has no vector column and no index** (`memory_engine.py:60-75`):

```sql
CREATE TABLE IF NOT EXISTS memory_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    ledger_path TEXT NOT NULL,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    significance TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

No `vector_blob`, no FTS5 virtual table. A pin cannot be found by semantic *or* keyword
search. Retrieval is by exact `job_id` only (`get_pins_by_job`), and that method has
**exactly one consumer in the entire tree** — the TUI modal
`project_canon_modal.py:118`. **No registered agent tool reads the pin table.**

**What *is* vectorised** is the thing the operator believed had been stopped:
`vectorize_ledger` (`rag_tools.py:646-675`) embeds each agent's **full final response**,
one call per turn, wired live at `maccre_router.py:771`. Plus `ingest_project`
(`rag_tools.py:901-1010`), which walks `01_Raw_Source`, `04_Code_Artifacts` **and**
`03_Agent_Ledgers` and embeds whole files.

**So the ranking the operator asked for, answered on the merits rather than on cost:**
pins-if-vectorised would be *better* than full ledgers — for a reason nobody has stated.
A ~40-token pin fits inside the 2,048-token window, so its vector actually represents it.
A 17,000-token ledger's vector does not. The advantage of pin-level granularity is
**honesty of the index**, not storage or speed.

**Also refuted: project memory is not only canonised session data.** Three write paths
populate project vector stores without canonisation — `ingest_project`, the
agent-callable `ingest_document` tool, and `import_foreign_vectors`
(`rag_tools.py:519`, cross-project osmosis into a `synaptic_bridge` collection). The
*triplet table* is canonisation-only; the *vector corpus* is not.

## 4. The breadcrumb design is not "close to refining" — its retrieval half is absent

Operator's intent, as stated: pins for the selected project are read, then the agent uses
a local memory search tool to treat pins as breadcrumbs pointing to **where the session
artifact lives** and **where inside that artifact to look**.

Measured against the schema in §3:

| Locator | Present? |
|---|---|
| Which artifact | **Yes** — `ledger_path`, but it is the *same absolute path for every pin in a session* |
| Which job | **Yes** — `job_id`, likewise identical across the session |
| Which node | **No.** The `### <node_name>` headers exist in the ledger and are flattened before extraction |
| Byte offset | **No.** Nothing computes or stores one |
| Section anchor | **No.** `significance` is model-written prose, not a citation |
| A searchable index | **No.** No vector, no FTS |
| A tool that reads pins | **No.** One TUI modal, zero agent tools |

So the "which artifact" half exists at session granularity, and **the "where inside"
half exists in no form.** Both things that could supply it are discarded before the pin
is written: the per-node headers in the unified ledger, and the per-node files in
`03_Agent_Ledgers/<job_id>/` that the unified ledger is assembled from.

**And what actually reaches an agent today is not the pin table.**
`swarm_worker._load_memory_pins()` (`swarm_worker.py:221-236`) globs `*.json` in
`02_Dynamic_Context/memory_pins`, **unfiltered by project or by job**, takes the **10
most recently modified files**, and pastes their raw text into the system prompt
(`swarm_worker.py:999-1001`).

### 4.1 The section that is always empty

`flow_engine.py:2188-2196` builds the unified ledger's *"Extracted Knowledge Triplets"*
table by globbing `pin_*_{job_id}*.json`. The only code that writes pin JSON writes
`global_pin_{doc_id}.json` (`rag_tools.py:396`, `collection_ingest.py:190`,
`antigravity_ingest.py:199`) — which **cannot match a glob anchored on `pin_*`**.

**Therefore the "Extracted Knowledge Triplets" section of every swarm session's unified
ledger is empty, always, and has been.** A heading with a table header and no rows.

This is a **hard dependency for the payload contract work (tracker #9)**: the 3b design
hands the unified ledger forward as accompanying context. Shipping that while the section
is permanently empty means shipping a payload with a decorative heading — and a decorative
heading in a payload is the readout problem from Requirement 33 wearing different clothes.

## 5. There is no way to measure any of this today

- **No tokenizer, no heuristic.** No `tiktoken`, no sentencepiece, no `len(text)//4`
  estimate. The only `Tokenizer` in the tree is openpyxl's vendored *Excel formula*
  tokenizer.
- **No payload size recorded anywhere.** `task_queue` (`local_broker.py:182-231`) holds
  paths and no sizes. No telemetry silo has a bytes or chars column
  (`telemetry_db.py:92-152`).
- **`countTokens` exists and is not on the execution path.** `calculate_predicted_cost`
  (`finops_tools.py:327-374`) makes a real `countTokens` call — and its **only caller is
  a burn-in test** (`maccre_core/tests/story_synthesis_burn_in.py:259`). It also returns
  `tokens = 0` and swallows the exception on failure, so a caller cannot distinguish
  "empty payload" from "count failed".
- **The one size observation in the codebase is a log line nothing reads.**
  `flow_engine.py:2303-2306` logs `"%d chars, %d turns, %d pins"`. Nothing consumes it.
- **Input tokens *are* recorded, but anonymously.** The two `INFERENCE_COST` sites
  (`maccre_router.py:396-403`, `:653-663`) pass real `input_tokens`/`output_tokens` from
  the provider — and pass **neither `session_id` nor `source_node`**, so the rows default
  to `""` and are not attributable to a node or a run.

**This is why the payload-contract change must be instrumented before it is made.**
Landing 3b today would raise the real bill — `actual_cost` derives from the provider's own
`promptTokenCount` (`maccre_router.py:382-390`) and would move automatically — while
leaving no way to say by how much or where. That is a success claim over unmeasured work.

## 6. The cost math the operator asked for

Assumption stated because the repo cannot do better: **~4 characters per token**, since no
tokenizer exists (§5). Every figure below is therefore an order-of-magnitude claim, not a
measurement, and is superseded the moment `countTokens` is on the path.

### 6.1 Embedding cost — full ledger vs pins

| | Calls | Billable tokens | Cost @ $0.15/M |
|---|---|---|---|
| One 68 KB unified ledger | 1 | 2,048 (server-truncated) | **$0.000307** |
| ~20 pins @ ~40 tokens | 20 | ~800 | **$0.00012** |

**Difference: ~$0.00019 per session — about two hundredths of a cent.**

The truncation is what makes the comparison lopsided in an unexpected direction: the
ledger costs *more* while indexing *less*, because billing stops at 2,048 tokens and so
does comprehension.

### 6.2 Per-run embedding cost, current behaviour

`vectorize_ledger` fires once per agent turn, capped at 2,048 billable tokens:

- one turn ≤ **$0.000307**
- an 8-lane scatter plus merge (9 turns) ≈ **$0.0028**
- a 3-step flow containing one 8-lane scatter (~11 turns) ≈ **$0.0034**

**Embeddings are not a cost problem at MACCRE's scale.** At a thousand agent turns the
bill is about **31 cents**. The reason to care about the free-keyword defect is that it
reports a false zero, not that the zero is expensive.

### 6.3 Density-scaled memory pins

The cost driver is **not the pins** — it is the extraction call. `gemini-2.5-flash` over
the **entire uncapped ledger** (`memory_engine.py`, `extract_from_canonized_ledger`), at
Flash rates of $0.075/M in and $0.30/M out.

| Scenario | Input | Output | Cost |
|---|---|---|---|
| Today (~20 pins) | ~17,000 tok | ~800 tok | **$0.00151** |
| Density-scaled, chunked, ~3× pins | ~17,000 tok | ~2,400 tok | **$0.00200** |

**Delta: ~$0.0005 per canonised session.** Five hundred canonisations to the dollar.

**So money is not the constraint on density-scaled pins — and the recommendation is to
not do it yet regardless.** More pins with no locator (§4) and no index (§3) makes recall
*worse*: what reaches an agent is the 10 most-recently-modified JSON files in one
directory, unfiltered by project. Tripling pin density triples the noise in an unfiltered
paste. **Density scaling is worth doing after pins are addressable, and harmful before.**

Two cost notes recorded because they are invisible today:

- The extraction call **bypasses the router** (`CognitiveMemoryEngine` holds its own
  `GeminiClient`), so `calculate_actual_cost` is never invoked on it and its
  `usage_metadata` is discarded. **Canonisation currently costs an untracked Flash call
  over an unbounded document.**
- The extraction has **no input cap**, unlike `ingest_global_archive` which caps at
  `text[:30000]`. It is the one path that feeds an unbounded document to a model.

## 7. Consequences, split

### 7.1 Era 3 — now, because Phase 4.99 or tracker #9 depends on it

| Finding | Why it cannot wait |
|---|---|
| §1 embeddings billed as free | A false zero in the cost surface, and the operator asked the cost question directly |
| §5 no attribution, no size | **Prerequisite:** the 3b change is unmeasurable without it |
| §4.1 empty triplets section | **Dependency:** 3b hands this ledger forward |
| The budget modal's false claims | Operator-facing text asserting "historical metrics" where none are consulted, and a hardcoded model |

### 7.2 Era 4 — the memory overhaul, as one design

Deferred at the operator's direction and recorded in the planning map: pin locators
(requires per-node extraction rather than flattened-ledger), pin vectorisation and
indexing, an agent tool that reads pins, chunking on the embed path, unifying the two
classes both named `SovereignPinStore`, resolving the documented-but-absent RRF, and
density-scaled pins — which depends on all of the above.

### 7.3 Recorded as false claims needing correction, wherever they are eventually fixed

- "256-dim" in `rag_tools.py:64`, `README.md:89`, `MACCRE_Operator_Manual.md:132` —
  actual width 3072.
- "embedding models are free" in `finops_tools.py:250` — $0.15/M.
- RRF / reciprocal rank fusion in `README.md:89`, `MACCRE_Operator_Manual.md:135`,
  `Era3_architectural_roadmap.md:37,117`, `sovereign_agentic_evolution_report.md:70` —
  `hybrid_search.py` is a concurrent fetch joined by **string concatenation**, with no
  rank arithmetic and no BM25 side. Five documents, zero code.
- `canonize_session`'s comment *"This is the ONLY place thought-pins are vectorized,
  keeping per-session cost to zero"* (`rag_tools.py:685-687`) — wrong on both halves:
  pins are not vectorised there at all, and per-session cost is not zero because
  `vectorize_ledger` embeds every agent output during the run.
- `canonize_session`'s docstring claims it merges "agent_thoughts and agent_ledgers"; the
  loop handles ledgers only.
- `sovereign_store.py`'s module docstring names `thought_pins.db` while the constructor
  defaults to `memory_pins.db`.

### 7.4 Two structural hazards found in passing, neither fixed here

- **Two classes named `SovereignPinStore`** (`memory/sovereign_store.py:126` and
  `orchestration/memory_engine.py:54`), both defaulting to `memory_pins.db` in the same
  directory, with incompatible schemas. They coexist only because
  `CREATE TABLE IF NOT EXISTS` is per-table. Principle 4, live.
- **`fts_query` disables every FTS5 operator it advertises.**
  `sovereign_store.py:305` wraps the query as `f'"{query_text}"'` — a hard phrase quote —
  while `fts_search_memory`'s docstring tells agents they may use `AND`, `OR`, `NOT`,
  `NEAR` and prefix `*` (`rag_tools.py:229-231`). Every one of those is inert.

## 8. Limits of this document

- **Token figures are ~4 chars/token estimates, not measurements.** No tokenizer exists.
  Every dollar figure in §6 should be re-derived once `countTokens` is on the path.
- **The 3072 dimension is inferred plus corroborated, not directly measured here.** It
  follows from the absent `outputDimensionality` and is confirmed by the in-repo RadonVec
  report; a blob-length check against a live `memory_pins.db` would settle it outright and
  was not run.
- **Whether Google is currently billing this key for embeddings was not verified against
  an invoice.** The rate is cited from Google's announcement; the claim here is that
  MACCRE records `$0.00` regardless, which is true either way.
- **No live run was made for this document.** It is a reading of the code.
