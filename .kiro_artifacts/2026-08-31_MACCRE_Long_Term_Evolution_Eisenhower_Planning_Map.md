# MACCREv2 — Long Term Evolution Steering Document

**Eisenhower planning map over the complete feature register**

**Written:** 2026-08-31
**Register mapped:** `B:\EXO_GANS\FeatureRequests.md` — 33 `### Feature Name:` entries
**Audience:** whoever resumes this project cold, months from now
**Nature:** durable steering guidance. Not a status report. Status lives in
`.kiro_artifacts/2026-08-31_phase_4_99_user_testing_handover.md`.

---

## 1. Executive orientation

MACCREv2 is at the transition from *building an engine* to *depending on one*. The
engine works — an 8-lane scatter reached `peak_concurrency=8, errors=0, stalled=False`
on run `job_20260831-041428-6goe`, with one execution per agent and a tether on every
lane. What the register reveals is that almost nothing downstream of the engine is yet
addressable: sessions have no names, artifacts have no published contract, knowledge
has no provenance, and the graph exists in two mutually drifting representations. The
register is not a backlog of features. It is a backlog of *seams*.

That shape is visible in the arithmetic. Of 33 entries, exactly one is Fulfilled. Six
are defect-class. Five carry an explicit `Deferred (needs prerequisite)` or
`Deferred (needs decision)` status, and four more are prerequisite-blocked in their
body text without saying so in their header. The register grew from 15 entries to 33 in
roughly ten weeks — and the newest nine are the largest and most architectural in the
document. This is a project whose ambition is outrunning its foundation, which is not a
criticism: the foundation is being built deliberately and the ambition is what
justifies it. But it means the scarce resource is not ideas. It is sequencing.

**Three decisions constrain everything else.** They are cheap to make and expensive to
defer.

1. **Timeout semantics.** `FlowRunner` does not stop the flow on a `timeout` step and
   still records the session `completed`. Until this is settled, `completed` is not
   evidence that every step ran — which means the Sovereign Importer contract, the
   Session Manager, any spatial map, and the migration KPI are all being designed
   against a status field that lies. This is one operator decision and roughly an
   afternoon of work. It gates Phase 4.99 Orchestration Action 4 and it silently
   weakens four register entries.

2. **Who owns topology authoring.** Two entries build authoring UI over the same graph
   (Phase 6.13 §6.14 multi-lane authoring, and Omniscience's "scope components
   spatially"). The register already records what happens when one graph gets two
   representations: the TUI builds node ids as `_{i}` while the engine hydrates `_S{i}`.
   That divergence is currently harmless because the TUI only draws. Two *authoring*
   surfaces would diverge with writes at stake. This decision costs one paragraph and
   zero code, and it is a hard prerequisite for two epochs.

3. **Whether the datacenter gets one read API or several.** Sovereign Importer needs
   session identity, artifact addressing and lifecycle states. Omniscience needs
   exactly the same thing. The Easter-egg KPI needs a subset. The AI Studio
   KnowledgeStore needs a place to live. If these are built independently they will
   produce three divergent read paths against one datacenter, and the register's own
   assessment says so explicitly. One contract, published once, unblocks the entire
   right-hand half of the register.

**The stated end goal — MACCRE as the operator's interface for ~100% of AI usage,
running on Android — has exactly one hard technical blocker, and it does not have a
register entry.** The credential vault is Windows DPAPI via `crypt32.dll`. It gates
every non-Windows client because it holds the credentials. Everything else on the
Android platform table (`win10toast`, `sqlite-vec`, `cryptography`, `pyperclip`) is a
guard or a build problem. The vault is an architecture problem. It is named inside the
*Android assistant client* entry's body but has no entry, no status and no size, which
means it is invisible to any process that works from entry headers. **My assessment:
give it its own entry.** A prerequisite that only exists inside the description of the
thing it blocks is a prerequisite nobody will schedule.

---

## 2. The Eisenhower matrix — all 33 entries

### 2.1 Classification principles

These are stated so the map can be re-derived, argued with, and re-applied to entries
added after this document.

- **Urgency derives from whether something blocks other work or is actively causing
  harm** — never from how recently it was requested. The register's newest nine entries
  are its most strategic and almost none of them are urgent.
- **Importance derives from whether it advances the stated end goal**: MACCRE as the
  operator's primary daily AI interface. Elegance, cleverness and personal interest are
  not importance. Two of the most interesting items in this register are in Q4 for
  exactly this reason.
- **A verified defect that silently corrupts data or reports false success outranks any
  feature.** Not because defects are sacred, but because this class of defect destroys
  the evidence you would use to plan with.
- **A prerequisite inherits the urgency of the most urgent thing it blocks.** This is
  what puts a session-naming text input in Q1 alongside an engine defect.
- **Verified means reproduced.** An entry marked *user-reported* is a lead, not a
  finding. Three consecutive engine defects this phase had plausible-but-wrong first
  hypotheses. For those entries the first scheduled action is *reproduce*, and the size
  is unknown until it is done.

### 2.2 Q1 — Urgent + Important (do now) — 8 entries

| Feature Name | Status in register | Why Q1 |
|---|---|---|
| **A timed-out step does not stop the flow** | Deferred (needs decision) · verified in code | Silent success over unperformed work, reproduced by reading `execute_flow`/`resume_flow`. It corrupts the meaning of `completed` for every consumer downstream, and it blocks 4.99 Orchestration Action 4. The fix is understood; only the sign-off is missing. |
| **System-wide provenance doctrine — breadcrumb everything, always** | Unfulfilled · doctrine | Urgent because retrofit cost rises with every artifact written, and because its first concrete increment is defect E2 — `CTRL_MERGE_S0` produced a 426 KB document and the next step received a 59-byte stub. Lineage is already broken in the running engine, not hypothetically. |
| **Node-ID convention divergence between TUI and engine** | Unfulfilled · verified in code | Cosmetic only while the visualiser merely draws. Phase 6.13 Task B5 (multi-lane rendering) is scheduled work that will bake the divergent ids into a second, larger surface. Fixing it before B5 is cheap; after B5 it is a rework. |
| **Scatter lane authoring ownership must be settled before two surfaces ship** | Deferred (needs decision) | Zero code, one paragraph, and it is a hard prerequisite for both multi-lane authoring and Omniscience. It is urgent solely because the work it gates is imminent. |
| **Session Manager — "Name Session" input does not accept entry** | Unfulfilled · **user-reported, not reproduced** | Every session is anonymous, so the File Cabinet and Importer work is being designed over `job_20260831-041428-6goe`-shaped identity. First action is reproduce, because the register's own leads span a wiring fix and a schema migration — a 10× size difference. |
| **Session Manager — "Name MacroNode" modal is a dead end** | Unfulfilled · **user-reported, not reproduced** | Traps the operator with no Save and no Cancel, and the register's second half is worse than the first: nobody knows whether saving overwrites, whether it lands in project or GLOBAL scope, or whether the round trip is identity-preserving. A silent overwrite is data loss. |
| **Session Manager / File Cabinet alignment for Sovereign Importer** | Deferred (needs prerequisite) | The single highest-leverage item in the register. It is the read API that Sovereign Importer, Omniscience, the KnowledgeStore and the migration KPI all independently need. Urgent as a prerequisite, not on its own merits. |
| **`omni qa` Pyright blind spot is hiding live type errors** | Deferred (needs decision) · reproduced | **The register is stale here — the handover records this as fixed on 2026-08-31** (117 files clean, 6 errors resolved). Q1 for two reasons: close the entry so nobody rediscovers it, and add the regression test that asserts the gate's effective file set matches `pyrightconfig.json`'s include list. Without that test the blind spot can reopen the same way it opened. |

Q1 contains no large items. Total estimated size is days, not weeks — which is what a
correctly-drawn Q1 should look like.

### 2.3 Q2 — Not Urgent + Important (schedule) — 10 entries

This is where the strategic capability lives. Nothing here should be started before Q1
is clear, and nothing here should be *skipped*.

| Feature Name | Status | Why Q2 |
|---|---|---|
| **Android assistant client — MACCRE as the daily AI interface** | Unfulfilled | This *is* the end goal, which makes it maximally important and — precisely because it is the end goal — not urgent. Its prerequisites are the work. The register's REVISED section is correct that serverless single-writer is sound; the surviving objection (WAL is three files and sync is not atomic across a file set) is a real design constraint, not a blocker. |
| **AI Studio KnowledgeStore — pinned, not embedded; isolated by default** | Unfulfilled | The design of record for the corpus. FTS5 + BM25 over the existing `SovereignPinStore` pattern, zero new dependencies, no embedding pass. Isolation as a **separate namespaced retrieval tool** rather than a query filter is the load-bearing decision here. |
| **AI Studio conversation corpus as a global semantic KnowledgeStore** | Unfulfilled | The payload — ~490 cleaned conversations, 315,035 Markdown lines, confirmed present. Important because it is the largest existing asset the system does not yet use. **Read this entry only through its amendment above**; its own "embed the corpus" framing is superseded and would be the wrong build. |
| **CrumbRunner — provenance and trust agent for scoped knowledge ingestion** | Unfulfilled | The enforcement mechanism for the provenance doctrine, and the entry with the most durable architecture in the register. Not urgent: it has nothing to enforce over until the KnowledgeStore exists. Its four trust hazards are design requirements, not later refinements. |
| **TUI hot-reload of system changes without restart** | Unfulfilled | Operator-identified as the last friction blocker to daily-driver use, and the register scopes it correctly: **tier 1 only.** Config/registry reload is partly built (`TopologyEngine.flush_cache()`, 5 s TTL, `merge_config_overlay`). General Python module reload is a trap and should stay out of scope permanently, not temporarily. |
| **Session Manager Dashboard** | Unfulfilled | The surface the two Q1 defects live inside, and the place session identity becomes visible and canonisable. Important because an unaddressable session history is a dead archive. |
| **Unified Welcome & Session Selection Screen** | Unfulfilled | Forces project and session selection at startup, which is how session identity stops being optional. The deterministic acronym-naming default is the cheap fix for the anonymity problem the Q1 naming defect creates. |
| **Interactive Node Configuration Modal** | Unfulfilled | Per-node Payload Mode (Unified Ledger vs preceding-node ledger) is exactly the lever behind defect E1 — eight lanes all routed via `unified_session_ledger.md` because that was their payload mode. Making this per-node and visible turns an invisible engine behaviour into an authored choice. |
| **Rename Nexus Copilot before any public artifact** | Unfulfilled | Two independent trademark exposures, and publishing is now in scope. Not urgent as a *rename* — urgent as an *indirection*. Do the `ASSISTANT_NAME` constant in the first epoch regardless of its quadrant: the name is spreading into prompts and ledgers, ledgers are persisted, and a late rename leaves historical artifacts permanently inconsistent. **My assessment: this is the cheapest irreversible-cost avoidance in the register.** |
| **Sovereign local model cluster (de-bloated Samsung compute fabric)** | Unfulfilled · hardware in progress | The strong half — one small model per device, one node role per device — fits MACCRE's per-node work assignment almost exactly and is embarrassingly parallel. **Drop the large-model tensor-sharding half** (see §2.6). Sequence as the register says: one device, one role, one model, measured against the cloud path, and the question is "good enough for this role", not tokens/sec. |

### 2.4 Q3 — Urgent + Not Important (minimise, delegate, or consciously accept) — 5 entries

| Feature Name | Status | Disposition |
|---|---|---|
| **Embedded Dynamic Flow Injection (HITL / Pause)** | **Fulfilled** | No remaining build work. Listed here because it needs *re-verification*, not construction: the scatter rework changed the paths it runs through, and UT-1 test 4 already exercises it. Delegate to that test round and do nothing else. |
| **`omni` hardening — deferred items carrying real risk** | Deferred (needs prerequisite — `--dry-run`) | **Consciously accept as unimplemented.** The current behaviour is fail-safe in all three cases: the zombie matcher is too narrow rather than too broad, the PID registry prunes rather than kills, and WAL cleanup looks only at the root. Implement `omni clean --dry-run` because it is cheap and it makes the next audit a single command — then stop. The handover's own recommendation is to migrate omni's task surface into the repo rather than invest further in omni, and that argues against deepening it. |
| **Standardized Modal Catalog** | Unfulfilled | Downgrade to a helper, not a catalog. The concrete evidence for a shared base is that the same dynamic-mount defect appeared in `NodeConfigModal` (scheduled as Task B4) and plausibly again in the Name MacroNode modal. A single `mount_and_refresh()` helper captures that lesson. A full catalog refactor is invisible to the operator and does not advance the end goal. |
| **Drag-and-Drop Node Reordering in Linear Flow Editor** | Unfulfilled | Real friction — reordering currently means delete-and-reappend. Build the cheap variant: move-up / move-down on the selected node. Drag-and-drop in a terminal UI is disproportionate effort for the same outcome, and this is authoring UI, so it must wait behind the authoring-ownership decision anyway. |
| **Blind Code Inspection Swarm Delegation** | Unfulfilled | Fully specified already (5-agent adversarial roster). Downgraded because **the handover's own conclusion is that more audit findings are not the bottleneck — the mechanism for actioning them is.** Run it once after UT-1 as a capability demonstration, on the condition that its findings land in this register as entries. Otherwise it manufactures exactly the backlog that already went unactioned for three weeks. |

### 2.5 Q4 — Neither urgent nor important (defer or drop) — 10 entries

| Feature Name | Status | Disposition |
|---|---|---|
| **Deterministic CI/CD Plan Reasoning Engine & Reasoning Confidence Score (RCS)** | Unfulfilled | **Drop.** A weighted sum over five soft vectors produces a number that cannot be validated against anything, and the weights would be chosen to make plans the operator already likes score well. The real problem it reaches for — cognitive load across five Oracle domains — is genuine, but the handover names the actual gap precisely: converting findings into scheduled work. That is a tracking discipline (see R3), not a scoring formula. The one component with independent value, static contract/schema checking, belongs in `omni qa` as ordinary lint rules. |
| **Advanced Probabilistic Steering Language (Tabled for Future)** | Unfulfilled | **Drop.** The register already shelved it as "unnecessary and overly fragile", and it now actively conflicts with the provenance doctrine: an LLM restructuring topology at runtime via `SPAWN_NODE` / `SKIP_TO` / `FORK` makes lineage unreconstructable. The determinism the system has been fighting for this whole phase is worth more than dynamic topology. |
| **Generative Comic Panel Animation (Temporal Extrapolation)** | Unfulfilled | **Drop from this register.** It is a content-generation feature with no relationship to MACCRE-as-daily-interface, and it needs an image-to-video dependency in a project whose entire discipline is near-zero dependencies. If it is wanted, it is a different project that consumes MACCRE, not a MACCRE feature. |
| **30-day transition Easter egg — MACCRE Chat Studio vs imported AI Studio** | Unfulfilled | **Drop the celebration; keep the metric.** The register says it best itself: "The party is the reward; the ratio is the KPI." The ratio — what fraction of AI usage runs on the operator's own system — is the clearest available measure of whether MACCRE achieved its purpose. Its requirement (Importer records import/update *events* with timestamps, not just final state) should land as a field in the read-API contract. The animation is work with a mid-flight hazard and no payoff. |
| **Multi-Tier Grounding Options & Hybrid Exclusionary Search** | Unfulfilled | **Drop the Brave hybrid and tri-grounding logic.** Sequential Google-then-Brave-excluding-Google roughly doubles latency and cost per grounded call for marginal recall, and the tri-grounding prompt injection is an attempt to solve by instruction what the KnowledgeStore entry solves structurally. The "Grounding with Local Memory" half is superseded: entry *AI Studio KnowledgeStore — pinned, not embedded* mandates a **separate namespaced retrieval tool** rather than a toggle on a shared query, precisely so retrieval is an explicit act visible in the ledger. A toggle would undo that. |
| **Nexus Copilot Sovereign Sandbox Enhancement (antigravity-preview-05-2026)** | Unfulfilled | **Defer, and re-scope.** The valuable 80% needs no sandbox and no model: `topology_graph.describe()` plus `build_from_template()` can validate a MacroNode deterministically before save — which is exactly the round-trip identity question already open in the Name MacroNode defect. Extract that as a small item there. Sandbox code execution by an agent is a large capability with real blast radius, gated on an external preview model, and off the critical path. |
| **`omni` telemetry logger with 30-day semantic compaction** | Unfulfilled · operator flagged not a priority | **Defer; drop the compaction scheme.** The value is in *recording* what omni did — every finding in the 2026-08-30 audit would have shown as a trend. That is a plain append-only run log, a small amount of work. The 30-day semantic compaction with a versioned in-file legend is an elegant design for a problem that does not exist at this scale, and it rewrites the operator's only tool history, which is the one file where a partial write is unrecoverable. |
| **TUI State Container & Asynchronous Rendering Architecture** | Unfulfilled | **Defer until measured.** There is no recorded measurement of the latency it targets, and the one measured throughput win this phase came from *removing* contention (throttling the demand estimator took an 8-lane scatter from 4.25 s to 1.26 s), not from adding buffering. Re-entry trigger: a measured frame-time or modal-mount problem, most plausibly when the TUI runs on phone-class hardware. Building a polling in-memory mirror of SQLite speculatively also creates a second representation of state — the failure mode this codebase has already produced twice. |
| **Generative Recruitment Engine (Prompt Engineer Evolution)** | Unfulfilled | **Defer indefinitely.** Agents generating agents into a recruitment roster is unbounded scope with an unsolved provenance problem: an auto-generated agent has no audited origin, and CrumbRunner exists specifically because unattributed inputs contaminate everything downstream. If it is ever built, promotion to the global roster must be a manual gate and the generated agent must carry a crumb-track. Not before Epoch 4. |
| **Omniscience — spatial system interface for omni** | Deferred (needs prerequisite — File Cabinet read API) | **Defer, trigger-gated.** This is the most attractive and least goal-aligned large item in the register: a desktop Three.js GUI does not advance MACCRE-as-Android-daily-driver, and its assessment is honest that the tomography is the wrong substrate for a labelled DAG. Its genuinely valuable prerequisites (`omni doctor`, the read API, `topology_graph.describe()`) are already scheduled elsewhere or already built. Re-entry trigger: the KnowledgeStore exists and is growing, giving the RadonVec telemetry pane a real consumer — cluster collapse in a memory store is invisible until something measures it. Hold the addressing/dispatch and spatial-authoring layers indefinitely; per its own F4, "kill this process in space" is where it becomes capable of harm. |

### 2.6 Partial drops, collected

Five entries should be built at less than their stated scope. Recorded together so the
cuts are not lost when the entries are read individually.

| Entry | Keep | Drop |
|---|---|---|
| Sovereign local model cluster | One small model per device, one node role per device; per-device datacenter namespace | Large-model tensor sharding across USB/ethernet. Per-token activation exchange dominates; it yields seconds per token. If ever attempted, pipeline-parallel only |
| Multi-Tier Grounding | Nothing — the local-memory need is met structurally by the KnowledgeStore entry | Brave hybrid exclusionary search; tri-grounding prompt injection |
| `omni` telemetry logger | A plain append-only per-run record | 30-day semantic compaction, abbreviation legend, re-expansion contract |
| Nexus Copilot Sandbox | Deterministic pre-save topology validation, relocated into the MacroNode save work | Sandboxed code execution; SDK-adjacent capability uplift |
| 30-day Easter egg | The sessions-this-period ratio, as a contract field | The celebration animation and its 30-day trigger machinery |

### 2.7 Addendum — the un-headed register block

`### Linear Flow & Special Nodes Enhancements` (appended under *Session Manager
Dashboard*) is not one of the 33 `Feature Name` entries — it has no Feature Name,
Date/Time or Status header, so it is invisible to any process that reads entry headers.
It contains six proposals and they do not classify together:

- `DET_FAN_OUT` / `DET_SYNTHESIZE` — **already delivered** in substance by
  `CTRL_SCATTER` / `CTRL_MERGE`. Retire the proposal.
- `DET_FILTER_IN` / `DET_EXTRACT` — cheap, deterministic, genuinely useful. Q2-class.
- `DET_DYNAMIC_ROUTER` — same objection as *Advanced Probabilistic Steering Language*.
  Drop.
- `DET_WEBHOOK` — inbound HTTP conflicts with the sovereign-edge posture. Drop.
- **Local Edge LLM Sync Node (S25 Ultra Integration)** — Q2, and the natural first
  integration point for the local model cluster. The register is right that dispatching
  work *to* an edge device is a different problem from carrying the datacenter
  *between* devices; keep them separate.

**Recommendation:** promote the surviving items to proper entries with headers, or they
will keep being skipped.

---

## 3. Dependency topology

### 3.1 True blocking chains, longest first

**Chain A — knowledge with provenance (7 links).** The longest chain in the register and
the one that ends in its most valuable capability.

| # | Link | Blocks the next because |
|---|---|---|
| 1 | *Session Manager — "Name Session" input does not accept entry* | A cabinet of unnamed sessions is a cabinet of job ids; naming may require a schema column |
| 2 | *Session Manager — "Name MacroNode" modal is a dead end* | Save/reuse round-trip identity is unknown; an importer must not consume a lossy round trip |
| 3 | *Session Manager Dashboard* | The surface both defects live in; session identity has to be visible before it can be contractual |
| 4 | *Session Manager / File Cabinet alignment for Sovereign Importer* | Publishes the stable addressing scheme, guaranteed vs best-effort fields, and lifecycle states |
| 5 | *AI Studio conversation corpus as a global semantic KnowledgeStore* | Needs somewhere contractual to live and a GLOBAL-scoped store |
| 6 | *AI Studio KnowledgeStore — pinned, not embedded; isolated by default* | The design that governs 5; separate namespace, provenance on every retrieval |
| 7 | *CrumbRunner* | Has nothing to score or reconcile until an external source with a known provenance story exists |

*A timed-out step does not stop the flow* cuts across links 4–7: until it is settled,
`completed` is not proof every step ran, and every consumer in this chain enumerates by
status.

**Chain B — MACCRE off the laptop (6 links).**

| # | Link | Blocks the next because |
|---|---|---|
| 1 | Credential vault platform abstraction — **no register entry; recommend creating one** | DPAPI via `crypt32.dll` holds the credentials; nothing runs off Windows without it |
| 2 | Per-deployment `journal_mode` (`DELETE` on synced storage, WAL on the laptop) | A WAL database is three files that must be mutually consistent; sync is not atomic across a file set |
| 3 | Device lease — persisted UUID, heartbeat, clean-release flag | Single-writer is doing all the safety work and must be mechanised, not remembered |
| 4 | Conflict-fork detection (`foo (1).db`) at startup | A silent fork is invisible until data goes missing |
| 5 | *Rename Nexus Copilot before any public artifact* | The assistant is user-facing product identity on the client, and ledgers persist the name |
| 6 | *Android assistant client — MACCRE as the daily AI interface* | — |

Links 2–4 all live inside the Android entry's body. **My assessment: 1 and 3 deserve
their own entries.** A prerequisite buried in a description does not get scheduled.

**Chain C — one graph, one owner (4 links).**

| # | Link | Blocks the next because |
|---|---|---|
| 1 | *Node-ID convention divergence between TUI and engine* | Any layer that *acts* on the rendered graph would address nodes that do not exist in the queue |
| 2 | *Scatter lane authoring ownership must be settled before two surfaces ship* | Two authoring paths over one graph will diverge as the ids already have |
| 3 | Phase 6.13 Task B5/B6 multi-lane rendering and per-lane authoring | Renders and writes the graph |
| 4 | *Omniscience* structural pane, then dispatch | Reads the same graph; must not invent a second read path |

**Chain D — tooling (2 links).** `omni clean --dry-run` → *`omni` hardening — deferred
items carrying real risk*. Short, cheap, low value; see Q3.

**Chain E — the migration KPI (3 links).** Importer import/update event telemetry →
read-API contract (link 4 of Chain A) → *30-day transition Easter egg*. Recommended
resolution: fold the telemetry requirement into the contract and drop the terminal link.

### 3.2 Circular and mutually-blocking pairs

Four, and each has a clean break.

| Pair | The circle | How to break it |
|---|---|---|
| *Session Manager / File Cabinet alignment* ↔ the two Session Manager defects | The entry is Deferred pending the defects, but the defects' *size* (wiring fix vs schema migration) is only knowable from the entry's own part (a) research | **Split the entry.** Part (a) is read-only research and is not blocked by anything. Do (a) first, use it to size the defects, fix them, then do (b) user-test and (c) publish. Only the *publication* was ever blocked |
| *Scatter lane authoring ownership* ↔ multi-lane authoring ↔ *Omniscience* | Each surface waits to see what the other becomes | **Decide on principle, without either existing.** Recommended: the TUI (§6.14) owns authoring; Omniscience is read plus targeted dispatch only, never authoring. This is defensible on the merits — authoring needs precise identity, and the spatial pane's own assessment says approximate identity must never drive an action |
| *Node-ID divergence* ↔ Task B5 multi-lane rendering | B5 is scheduled and will extend the divergent ids; fixing divergence changes what B5 builds on | **Order it: divergence first.** It is a smaller change now than a rework later, and `topology_graph.describe()` already exists for exactly this purpose |
| *Easter egg* ↔ Importer event telemetry ↔ contract | The egg needs telemetry the Importer does not record; the Importer schema is fixed by a contract not yet written | **Break by dropping the egg** and adding the event-timestamp requirement to the contract while it is still being drafted. The register already warns this must land as part of the contract, not bolted on |

### 3.3 Critical path to the stated end goal

MACCRE as primary daily interface, running on Android against a synced personal cloud:

```
E1 / E2 payload-lineage fixes            (open, diagnosed, not in register — prerequisite to all testing)
  -> timeout semantics decision          [A timed-out step does not stop the flow]
  -> UT-0 runs 2 & 3, then UT-1
  -> Session naming reproduced and fixed [Name Session, Name MacroNode]
  -> read API published                  [Session Manager / File Cabinet alignment]
  -> credential vault platform abstraction   <-- NO REGISTER ENTRY. Hardest link.
  -> journal_mode per deployment + device lease + conflict-fork scan
  -> MacroNode-by-name resolver (feasible today: get_macronode_store, resolve_primitive_node_id)
  -> Android client shell                [Android assistant client]
  -> hot-reload tier 1                   [TUI hot-reload]  (friction, not capability)
  -> KnowledgeStore + provenance         [pinned/isolated, provenance doctrine, CrumbRunner]
```

Two observations about this path. First, **nothing on it is on the spatial-interface or
RadonVec track** — those are genuinely orthogonal, which is why they sit in Q4 despite
being interesting. Second, the *shortest* item on the path (a MacroNode-by-name
resolver over the existing store) is already feasible and could be demonstrated long
before the vault abstraction lands. **My assessment: build it early as a de-risking
demo.** It proves the interaction model the whole end goal rests on, at near-zero cost.

### 3.4 Genuinely independent — safe to run in parallel

These touch nothing else in the register and can be picked up by whoever has capacity,
in any order:

- *Rename Nexus Copilot* — the `ASSISTANT_NAME` indirection specifically. One
  definition, mechanical call-site changes.
- *A timed-out step does not stop the flow* — needs only a decision and a one-line
  condition, plus tests.
- *`omni qa` Pyright blind spot* — the regression test and the entry closure.
- *TUI hot-reload* tier 1 — extends an existing `flush_cache()` pattern.
- *Drag-and-Drop Node Reordering* (move-up/down variant) and the modal mount helper —
  local TUI changes.
- *Sovereign local model cluster* pilot — an entirely separate hardware track with a
  procurement gate (bootloader lock) and a thermal ceiling, both independent of any
  software work here.
- *DET_FILTER_IN* / *DET_EXTRACT* from the un-headed block — self-contained
  deterministic nodes.

---

## 4. Evolution epochs

Six epochs. Each is named for what it achieves. Sizes use the Phase 6.13 sizing table's
units where the work is covered by it; everything else is marked as my estimate and
should be treated as order-of-magnitude only.

### Epoch 1 — *The engine tells the truth*

**Defining capability:** no flow can report success over work that did not happen, and
no artifact silently loses its content at a step boundary.

| Entries | Also required (not register entries) |
|---|---|
| *A timed-out step does not stop the flow* · *`omni qa` Pyright blind spot is hiding live type errors* | E1 (merge reads eight copies of the shared ledger) · E2 (merge output does not cross the step boundary) · UT-0 runs 2–3 · UT-1's six tests |

**Exit criterion:** UT-1 passes all six tests, including test 6 (kill a worker
mid-node). An 8-lane scatter's merge shows eight *distinct* sources and the next step
receives the merged document, not the stub. No terminal condition — cancel, stall or
timeout — can leave a session recorded `completed`.

**Size:** UT-1 ready is **~2–3 days** per the sizing table, plus **~1 day** for E1/E2
and **half a day** for UT-0 ×3. E1 carries one recorded wrinkle: `route_task` overwrites
the completing row's `payload_path`, so an `output_path` column may be needed.

### Epoch 2 — *One graph, one owner*

**Defining capability:** exactly one representation of the topology, addressed the same
way by everything that reads or writes it, with a single documented authoring surface.

| Entries |
|---|
| *Node-ID convention divergence between TUI and engine* · *Scatter lane authoring ownership must be settled before two surfaces ship* · *Interactive Node Configuration Modal* · *Standardized Modal Catalog* (helper only) · *Drag-and-Drop Node Reordering in Linear Flow Editor* (move up/down only) |

**Exit criterion:** `maccre_tui/nexus_plex.py` constructs no node ids of its own; a test
asserts every rendered id exists in `topology_graph.describe()`. The register records
one owner for topology authoring. UT-2's five tests pass. Per-node Payload Mode is
authorable, which makes E1's root cause a visible choice rather than an invisible
default.

**Size:** Track B engine (B1–B3) **3–4 days** and Track B UI (B4–B6) **3–5 days** per
the sizing table — *UT-2 ready ≈ 2 weeks* — plus **~1–2 days** for the divergence fix,
the modal helper and reordering. My estimate for the non-tabled parts.

### Epoch 3 — *Sessions are addressable*

**Defining capability:** an external process can enumerate, address and read any session
and its artifacts against a published contract — and every session has a human name.

| Entries |
|---|
| *Session Manager — "Name Session" input does not accept entry* · *Session Manager — "Name MacroNode" modal is a dead end* · *Session Manager Dashboard* · *Unified Welcome & Session Selection Screen* · *Session Manager / File Cabinet alignment for Sovereign Importer* |

**Exit criterion:** an integration report exists stating, with observed evidence rather
than intent: the stable addressing scheme for a session and its artifacts; which fields
are guaranteed versus best-effort; when a session becomes importable and how
`cancelled` / `failed` / stalled sessions are treated; and whether export/import
reproduces a *runnable* flow. Plus a baseline user-test walkthrough recorded including
failure modes, in the manner of UT-0. Plus: every session carries a name, and saving a
session as a MacroNode states its scope, its collision behaviour and whether the round
trip is identity-preserving.

**Size:** ~1–2 weeks — **my estimate**, and the least confident number in this document,
because two of the five entries are user-reported and unreproduced. If session naming
needs a schema column plus migration (the shape of Task A1's `locked_at`), add days; if
it is a wiring fix, subtract them. **Reproduce first, then size.**

### Epoch 4 — *Knowledge carries its origin*

**Defining capability:** external knowledge is usable without contaminating the
system's own findings, because provenance survives every transformation.

| Entries |
|---|
| *System-wide provenance doctrine — breadcrumb everything, always* · *AI Studio KnowledgeStore — pinned, not embedded; isolated by default* · *AI Studio conversation corpus as a global semantic KnowledgeStore* · *CrumbRunner — provenance and trust agent for scoped knowledge ingestion* |

**Exit criterion:** retrieval from the external corpus is a **separate namespaced tool**
whose use is visible in the ledger, never a filter on a shared query. A provenance
artifact is a first-class ledger kind, append-only, and a derived artifact's provenance
is the union of its inputs' plus the transformation. A test asserts the trust ceiling:
an output's effective trust cannot exceed the minimum trust of its inputs. Re-import is
idempotent under a stable conversation id and per-turn content hash. Chunking is on turn
boundaries.

**Size:** ~2–4 weeks — **my estimate**. The doctrine's first increment (E1/E2) is
already in Epoch 1, and the store reuses the existing FTS5/BM25 pin pattern, so the bulk
is CrumbRunner. Note the corpus needs no embedding pass, which removes the largest cost
the original framing implied.

### Epoch 5 — *MACCRE off the laptop*

**Defining capability:** the same code runs on the phone against synced storage, and
the operator names a MacroNode and it runs.

| Entries | Also required (recommend creating entries) |
|---|---|
| *Android assistant client — MACCRE as the daily AI interface* · *Rename Nexus Copilot before any public artifact* · *TUI hot-reload of system changes without restart* · *Sovereign local model cluster (de-bloated Samsung compute fabric)* | Credential vault platform abstraction · device lease (UUID + heartbeat + clean-release) · per-deployment `journal_mode` |

**Exit criterion, staged.** Sub-milestone: MacroNode-by-name resolution demonstrated on
the desktop (feasible today). Sub-milestone: the credential vault has a platform
interface with a Windows DPAPI implementation behind it and one non-Windows
implementation, and a test asserts no Windows-only symbol is imported outside a platform
module. Epoch exit: one MacroNode invoked by name on an Android device, against a synced
datacenter, with the device lease enforced and no persistent `-wal` in the synced tree.

**Size:** months, and the only honest sizing is per sub-milestone. The local model
cluster runs as a parallel track with its own gates: bootloader-unlock availability per
device (procurement, not software) and sustained-throughput measurement under thermal
throttling — which will bind before bandwidth does.

### Epoch 6 — *Observation* (trigger-gated, not scheduled)

**Defining capability:** the operator can see the system's state over time rather than
inspecting it.

| Entries |
|---|
| *Omniscience — spatial system interface for omni* (structural read-only pane, then the RadonVec telemetry pane) · *`omni` telemetry logger with 30-day semantic compaction* (plain run log only) · *TUI State Container & Asynchronous Rendering Architecture* |

**This epoch has no scheduled start.** It begins when a trigger fires, and only then:

- Telemetry pane: the KnowledgeStore exists and is *growing continuously*, so drift and
  cluster-collapse telemetry has a real subject. RadonVec's measured strength is O(1)
  drift and anisotropy over high-dimensional embedding clouds; a static corpus does not
  drift.
- State container: a measured frame-time or modal-mount problem, most plausibly on
  phone-class hardware.
- Structural pane: only after the read API (Epoch 3) exists, and read-only. Addressing
  and command dispatch stay held indefinitely; per the assessment's own F4, that is
  where a spatial interface becomes capable of killing the operator's terminal.

**Size:** not estimated. Estimating it would imply it is scheduled.

---

## 5. Standing architectural principles

These are extracted from the register and the incidents behind it. They are the durable
part of this document — the epochs will be obsolete in six months; these will not.

**1. Trust is a ceiling inherited from provenance, with full chain of custody.**
An output's trust is bounded above by the **minimum** trust of its inputs. It is never a
label applied by the last handler. Without this rule, score laundering happens
automatically, silently, and on every summarisation — a low-trust source summarised by a
high-trust agent would inherit the agent's trust. *Incident:* the register's CrumbRunner
entry identifies this as hazard #1 before the agent exists. *Corollary:* provenance is
append-only, because "why is this trusted" is the only question that matters during an
audit, and an overwritten history cannot answer it. *Corollary:* a derived artifact's
provenance is the **union** of its inputs' plus the transformation — provenance that
evaporates at the first summarisation is decorative.

**2. An approximately-correct identifier is worse than an absent one.**
A wrong non-empty value propagates and downstream logic *acts on it*. An empty value
degrades visibly. *Incidents, four of them:* the D3c overlay blanked the topology's
tether on control nodes only, putting scatter and merge in different scopes, so the
gather gate could never open and an 8-lane run deadlocked — an empty tether would merely
have degraded. Three PIDs in `.session_pids.json` had become an editor terminal, a font
cache service and a Logitech service; killing on a registry PID alone would have
terminated the operator's own shell. The recursion limiter inserted a node literally
named `FAILED`, which was claimed, **ran real inference**, and fed its output to the next
step. And in the Omniscience assessment, inferring which node a recovered density peak
represents would reintroduce ambiguity into the one place a command-dispatch interface
must not have it. *Applied rule:* an address is actionable only when every component
corroborates — for a process, PID **and** creation time **and** command line.

**3. Never report success over unperformed work.**
*Incidents, five of them:* the drain check counted only `open` rows, so a stranded
`locked` row returned `drained=True` and the step reported `"completed"` — the
rollback's signature failure. `omni clean` logged "Project directory sterilized." while
removing nothing, because `shutil.rmtree("__pycache__")` removes one named directory and
there is no root `__pycache__`. `CTRL_MERGE` reported `Merged 8 sources`, which was
literally true and semantically wrong — all eight paths were the same file. A `timeout`
step still records the session `completed`. And the proposed `--smart` implementation
logged "Skipping Ruff" and passed when no files had changed, reporting a green gate over
zero linting. *Applied rule:* a success line must be **conditional on counted work**,
and an ambiguous terminal state gets its own distinct status (`stalled`) rather than
being folded into success.

**4. Two representations of one graph will drift.**
*Incident:* the TUI builds node ids as `f"{a}_{i}"` while `flow_engine._hydrate_topology`
builds `f"{node_id}_S{step_index}"`. Harmless while the TUI only draws; wrong the moment
anything acts on what is drawn. *Applied rule:* one seam, and everything reads through
it — `topology_graph.describe()` exists for exactly this. *Generalisation:* this is why
two authoring surfaces must not ship, why CrumbRunner must reuse `topology_graph` for
cycle detection rather than write a second graph, and why an in-memory SQLite mirror is
a cost as well as a benefit.

**5. Specifications drift from implementations unless mechanically checked.**
*Incidents:* `omni qa --smart` was accepted by argparse, documented in
`OMNI_DESIGN_SPEC.md` under "Current Capabilities (Implemented)", described in the
workspace steering — and `args.smart` was never read. `pyrightconfig.json` named three
include targets while `omni.py` passed an explicit path that overrode them, so two files
had *never* been type-checked and held six real errors. `_FALLBACK_CHAINS` was
hand-maintained and stopped at 3.1, giving any newer model a failover chain of one.
`special_nodes` was the same shape of literal table shadowing a registry that already
knew better. *Applied rule:* every claim a document makes about behaviour needs a test
that fails when the claim goes false. Concretely: a test that asserts the gate's
effective file set equals the config's include list; a test that asserts every model in
the fallback table exists in the live surface.

**6. A green test suite is not evidence of a working system when defects live in the
seams.**
*Incident:* the suite was green at 546, 617, 625, 636 and 665 tests while **six** real
defects sat in the scatter path, because they lived between the authoring UI and the
engine — territory no stubbed test visits. Separately, a single `ImportError` in one
orphaned test module aborted collection repo-wide, so zero tests ran while the report
looked normal. *Applied rule:* seam changes require a scripted by-hand walkthrough (the
UT-0 discipline) recorded with its failure modes, and every pytest run is judged on the
**collected** count, not the pass count.

**7. Verified means reproduced. A user report is a lead.**
*Incident:* the doctrine addendum records that three consecutive engine defects this
phase had plausible-but-wrong first hypotheses — each fix revealed the next defect
rather than confirming the guess. *Applied rule:* the `**Verified:**` line is load-bearing.
Do not size, schedule or design against an unreproduced report; the first task is always
reproduction, and the size is unknown until it completes.

**8. Atomicity is a property of an artifact *set*, not a file.**
*Incident:* a WAL database is three files (`.db`, `.db-wal`, `.db-shm`) that must be
mutually consistent, and a sync client uploads files independently with independent
timing. Single-writer discipline does not help, because sync is not atomic across a file
set. *Applied rule:* **checkpoint, never unlink** — `PRAGMA wal_checkpoint(TRUNCATE)` is
lossless, deleting a `-wal` can destroy committed transactions. Choose the journal mode
per deployment: WAL where there is concurrency to optimise, `DELETE` where there is
none. The same primitive covers the deferred omni WAL item and the Android datacenter.

---

## 6. Risk register

| # | Risk | Why it is likely | Mitigation |
|---|---|---|---|
| **R1** | **Windows coupling versus the Android goal.** The vault is DPAPI via `crypt32.dll`; process management uses `taskkill` and PowerShell; `win10toast` fails to import at all; `sqlite-vec` needs an aarch64 build; `cryptography` is historically painful under Termux | The coupling is load-bearing, not incidental, and it deepens every time a Windows API is the convenient answer. The vault gates everything because it holds credentials | Give the vault abstraction its own register entry and treat it as the Epoch 5 gate. Add a guard test that fails if a Windows-only symbol is imported outside a designated platform module — the same shape as the broker signature-parity guard. Buy one device early and run the *import surface* against it before writing any client, so the platform table stops being a list and becomes a pass/fail |
| **R2** | **Solo-operator bandwidth against 33 open entries.** One person, non-professional, working through AI agents, against a register whose Q2 alone is ~10 strategic items | The register grows faster than it closes. Nothing in it expires on its own | Hard WIP limit of one epoch. Nothing enters Q1 without displacing something. Execute the drop list in §2.5–2.6 as an actual deletion pass, not an intention. **Prefer finishing an epoch to starting the most interesting item** — the interesting items are, by construction of this map, mostly in Q4 |
| **R3** | **The audit-to-action gap.** The 2026-08-09 Orchestration audit's *first listed finding* was the missing `tether_id` in `route_task()`. That is D3. It was identified **three weeks before** it cost three live runs and a deadlock to rediscover. Its second finding shaped Task B2; its third became Track A | The audits are right and are not read. This mechanism failure has already cost more than any single defect in the register. And it fails in **both directions**: the `omni qa` Pyright entry is still open in the register while the handover records it fixed, so a future reader will also waste time on already-done work | Make register entry creation part of an audit's definition of done: every finding lands as an entry with `Status` and `Verified`, or the audit is not complete. Run a reconciliation pass at every epoch boundary that diffs open audit findings against register entries in both directions. This mechanism is worth more than any individual finding in any audit — which is the handover's own conclusion, and it is correct |
| **R4** | **Scope growth in the register itself.** 15 entries to 33 in about ten weeks (+120%), and the newest nine are the largest | Each new entry is individually justified and the operator's vision is genuinely expanding. That is exactly how a register becomes unactionable | Require every new entry to name the epoch it belongs to, or be explicitly marked *unscheduled idea*. Re-run this Eisenhower pass at every epoch boundary and permit entries to be **deleted**, not just deferred — a deferred entry still costs attention on every read. Promote the un-headed `Linear Flow & Special Nodes Enhancements` items to real entries or delete them; invisible scope is the worst kind |
| **R5** | **Sync-substrate data loss on the path to Android.** WAL's three-file consistency versus independent per-file sync; Drive writing `foo (1).db` conflict forks rather than merging; single-writer discipline enforced by memory | The failure is silent. Outcomes range from losing the last N transactions to a database that will not open. And the register notes this phase already spent three runs on two components disagreeing about shared state on a *local* disk | Per-deployment `journal_mode` (`DELETE` on synced storage). Device lease with a **persisted UUID** — never a hostname, per the PID-reuse lesson — plus heartbeat and clean-release flag; refuse startup against a live foreign lease, warn loudly against a stale one. Startup scan for conflict-named siblings. Treat Syncthing over Tailscale as the target substrate rather than the fallback: whole-folder consistency and explicit conflict files |
| **R6** | **Provenance retrofit cost, and silent contamination before it lands.** Untagged data has no origin to recover | Every artifact written before the doctrine lands is permanently unattributed, and the volume grows daily. The corpus about to be ingested is ~490 external conversations whose speculation is indistinguishable from findings once it is in a ledger | Adopt the doctrine before the external source arrives, which is the register's own reasoning. Land E1/E2 as its first increment — they *are* a lineage break, not adjacent work. Make the external store a separate namespaced tool so retrieval is an explicit, ledger-visible act. Enforce the trust ceiling with a test, not a convention |
| **R7** | **Attractive nuisances consuming the critical path.** Omniscience, the RadonVec telemetry pane, cross-device model sharding, and the RCS scoring engine are the four most intellectually appealing items in the register, and none of them are on the critical path | Interest is not proportional to value, and a solo operator's attention is the whole budget. The RadonVec work was built in three hours over a weekend; that success makes reuse feel cheaper than it is | Epoch 6 exists precisely to hold these, and it is **trigger-gated with named triggers**. No work begins until the trigger fires. Where a large item has a small valuable core, extract the core and drop the rest — see §2.6 |
| **R8** | **Nothing is committed.** The handover records the entire phase — Track A, Track D and four follow-on defect fixes — as uncommitted on top of baseline `f7b326f`. There is no CI; `omni` is a local just-in-time gate that runs nothing on push | A single disk or machine failure loses weeks. This is the highest-probability catastrophic risk in the register and it is not in the register | Commit at every epoch boundary and at every gate-green point, on a branch, with the gate result recorded in the commit message (`omni qa` file count, pytest **collected** and passed counts, `omni smoke`). This is the cheapest item in this entire document and it should be done before anything else in §7 |

---

## 7. Recommended immediate sequence

Ten actions, in order, directly actionable by someone resuming cold. Each states why it
is here and how you know it is done. The pipeline gate for every code change is
`omni qa` (whole project) followed by `.\.venv\Scripts\python.exe -m pytest tests -q`
with the **collected** count checked, plus `omni smoke` when execution paths change.

**1. Commit the current tree to a branch.**
*Why:* Track A, Track D and four follow-on defect fixes are uncommitted on top of
`f7b326f`. R8 is the highest-probability catastrophic risk here and this removes it in
minutes.
*Exit:* `git log` shows a commit on a non-`main` branch whose message records
`omni qa` clean across 117 files, 665 tests passed, `omni smoke` green.

**2. Fix E1, then E2 — in that order.**
*Why:* E1 decides what the merge *reads*; E2 decides what the next step *receives*.
Fixing E2 alone would faithfully deliver eight duplicates. Both are diagnosed to root
cause and neither needs an expensive model.
*Exit:* an 8-lane scatter produces a merged document with eight **distinct**
`## Source:` sections, and the following step's input is that document rather than the
59-byte ledger stub. Watch for the recorded wrinkle: `route_task` overwrites the
completing row's `payload_path`, so an `output_path` column may be required.

**3. Decide timeout semantics.**
*Why:* an operator decision, not an engineering one. It gates 4.99 Orchestration Action
4 and it silently weakens the `completed` status that four register entries depend on.
Recommendation stands: stop the flow and mark the session `failed`, matching the stall
path. It will fail flows that currently report success — that is the point.
*Exit:* the decision is written into the register entry, its status changes from
*Deferred (needs decision)*, and the behaviour has a test.

**4. Run UT-0 runs 2 and 3 on `gemini-3.7-flash`.**
*Why:* run 1 is not a valid baseline — it was measured while every agent ran twice and
the merge combined one source. Two go/no-go decisions are waiting on this data
(§6.13 WAL sharding, and auto-reclaim). Current evidence points to *no* on both: zero
`database is locked` across every run so far, and the largest throughput win came from
removing contention, not adding capacity.
*Exit:* three consecutive instrumented runs recorded via `scratch/_ut0_report.py`, with
both go/no-go decisions written down and dated.

**5. Run UT-1, starting with test 6.**
*Why:* test 6 (kill a worker mid-node) exercises the defect class that caused the
original rollback and was impossible before Track A. Run it first because it is the
highest-information test in the round. Use a trivially safe payload — "Please tell me
about roses" worked precisely because nothing trips over its instructions — and leave
Tether ID blank on both `CTRL_SCATTER` and `CTRL_MERGE`.
*Exit:* all six tests pass; the killed-worker case either recovers or stalls loudly, and
under no circumstance reports success.

**6. Add the gate-coverage regression test and close the Pyright entry.**
*Why:* the fix landed but the mechanism that allowed it is untested, and the register
still shows the entry open — which will cost the next reader a rediscovery pass. This is
Principle 5 and Risk R3 in one small action.
*Exit:* a test fails if Pyright's effective file set is narrower than
`pyrightconfig.json`'s `include` list; the register entry is marked Fulfilled with a
date.

**7. Settle topology authoring ownership, in writing.**
*Why:* zero code, one paragraph, and it unblocks Epoch 2 and constrains Epoch 6.
Recommendation: the TUI (§6.14) owns authoring; Omniscience is read plus targeted
dispatch, never authoring.
*Exit:* the register entry's status changes from *Deferred (needs decision)* and names
the owner.

**8. Fix the node-ID divergence before Task B5 lands.**
*Why:* it is cheaper now than as a rework, and B5 is the surface that would double the
problem. `topology_graph.describe()` was built for exactly this.
*Exit:* `nexus_plex.py` constructs no node ids; a test asserts every rendered id appears
in `describe()`'s node set.

**9. Introduce the `ASSISTANT_NAME` indirection.**
*Why:* the rename gets monotonically more expensive, and ledgers are persisted — a late
rename leaves historical artifacts permanently inconsistent. This is not choosing the
name; it is making the choice cheap.
*Exit:* one definition site; a grep for the literal string returns that site only. The
name itself can stay a placeholder indefinitely.

**10. Do part (a) of the File Cabinet research, read-only — and open a register entry
for the credential vault platform abstraction.**
*Why:* part (a) is not actually blocked by the two Session Manager defects (§3.2), and it
is what tells you whether session naming is a wiring fix or a schema migration. The vault
entry matters because the hardest prerequisite on the critical path to the stated end
goal currently has no entry, no status and no size, and therefore cannot be scheduled.
*Exit:* a research note recording what the Session Manager reads and writes through
which broker methods, how the File Cabinet enumerates artifacts, which on-disk paths are
contractual versus incidental, and whether session identity is stable enough to be a
foreign key. Plus a new register entry for the vault abstraction, `Status: Unfulfilled`.

**Do not start anything in Epoch 4, 5 or 6 until items 1–10 are complete.** Every one of
them is small, and each removes a way for later work to be built on something untrue.

---

## 8. Confidence, and what could not be determined

**Confident:**

- **The entry count.** 33 `### Feature Name:` headings, confirmed by pattern search
  across all 845 lines, all of which were read. Every one appears exactly once in §2.
- **Quadrant assignment against the stated principles.** Reasonable people would move
  individual entries between Q2 and Q4; the Q1 set follows mechanically from "verified
  defect that reports false success" plus "a prerequisite inherits the urgency of what
  it blocks".
- **The dependency chains.** Every link is stated in the register or the supporting
  artifacts, not inferred, except where marked as my assessment.
- **The Epoch 1 and 2 sizes**, which come from the Phase 6.13 sizing table verbatim.

**A discrepancy worth recording.** The brief describes the register as having 15 original
entries (2026-06 to 2026-07). I count **14** with `Feature Name` headers, plus the
un-headed `### Linear Flow & Special Nodes Enhancements` block, which carries no Feature
Name, Date/Time or Status. Counting that block gives 15 and gives the document 34 items.
I mapped the 33 headed entries in §2 and handled the block separately in §2.7. The
material point is not the count — it is that an un-headed block is invisible to any
process reading entry headers, which is why its contents have never been scheduled.

**Could not determine:**

- **Whether the two Session Manager defects are wiring or schema.** Neither is
  reproduced, and the register is explicit that its own stated causes are leads. Epoch
  3's size is the least reliable number in this document for that reason.
- **Whether Phase 6.13 Track B has landed.** The handover records Track A and Track D as
  complete and gated, and says nothing about B1–B6. I have assumed B is not landed. If
  B5 has shipped, action 8 in §7 becomes a rework rather than a cheap fix, and Epoch 2
  grows.
- **Exactly what the Pyright fix included** — whether the explicit path argument was
  dropped so `pyrightconfig.json` became authoritative, or only the six errors were
  fixed. The handover's "blind spot closed, 117 files" reads as both. Action 6's test
  settles it either way, which is why it is worth doing.
- **Whether `omni doctor` exists.** It is proposed in NEW ITEM E and referenced as a
  prerequisite by the Omniscience sequence, but it is not a register entry and I found no
  evidence of implementation. If Epoch 6 is ever unlocked, `omni doctor` is its first
  step and it needs an entry.
- **Line counts.** ~66,000 lines of Python, ~7,000 for RadonVec, ~3,800 Python and
  315,035 Markdown for Sovereign Importer — taken from the brief and the register. Only
  the Markdown figure is corroborated in a document I read. None were independently
  verified, and none affect the plan.
- **Whether the local model cluster's procurement gate can be met.** US-market Samsung
  flagships generally ship with locked bootloaders; meaningful de-bloating needs them
  unlocked. That is a per-device fact to confirm before buying spares, and it could
  invalidate the strong half of that entry on hardware grounds alone.

**Marked as my assessment, not the register's:** the recommendation to create register
entries for the credential vault abstraction and the device lease; the three full drops
and five partial drops; placing Omniscience and the TUI State Container in Q4; treating
the register's own staleness (the fixed-but-open Pyright entry) as evidence for R3; and
every size estimate not drawn from the Phase 6.13 sizing table.

---

*This document maps `FeatureRequests.md` as it stood on 2026-08-31 at 33 entries. It
modifies nothing. Re-run the Eisenhower pass at every epoch boundary.*

> **AMENDED 2026-08-31 — entries are never deleted.** The original closing line of this
> document invited deletion at epoch boundaries. That is withdrawn by operator directive.
> See the **Entry Doctrine — Second Amendment** in `FeatureRequests.md`: the register is
> append-only, and terminal states are `COMPLETED` (requiring a Completion Metric and
> timestamp), `WITHDRAWN` (requiring a Withdrawal Rationale), or `SUPERSEDED` (naming the
> replacement).
>
> **Consequence for §2.5 and §2.6 of this document.** The three full drops and five
> partial drops recommended above are **recommendations to mark `WITHDRAWN` with
> rationale**, or to reduce scope in place — not to remove. The reasoning that declined
> an item is evidence, and a deleted entry is an invitation to re-propose the same thing.
>
> **This document is also now stale as a map.** The register has grown from 33 to 40
> entries since it was written (six datacenter/provenance entries plus the Nexus Copilot
> harness). The Nexus Copilot harness in particular is Q1/Q2-class and gates the Android
> epoch, so Epoch 5's entry list is incomplete as drawn. Treat §§2–4 as a 33-entry
> snapshot pending the next pass; §5 (standing architectural principles) and §6 (risk
> register) remain current.
