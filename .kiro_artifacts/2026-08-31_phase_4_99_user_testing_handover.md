# Phase 4.99 User Testing — Handover & Operator Action List

**Written:** 2026-08-31
**Audience:** the operator, resuming after a break
**Purpose:** what 4.99 is, where it stands, and exactly what you need to do next

---

## 1. What Phase 4.99 actually is

4.99 is the **production boundary certification** — the last gate before MACCRE is
treated as a working system rather than one under construction. It is *user* testing:
actions performed by hand in the TUI, not automated tests. The 665-test suite proves
the code does what it was written to do; 4.99 proves the **system** does what the
operator needs.

That distinction earned itself this phase. The suite was green at 546, 617, 625, 636
and 665 tests while **six** real defects sat in the scatter path, because they lived in
the seam between the authoring UI and the engine — territory no stubbed test visits.

### The source documents

Two layers, both in `.oracle_artifacts/`:

| Layer | Files | Content |
|---|---|---|
| **Test actions** (2026-07-28) | `2026-07-28_phase4_99_user_test_actions_*.md` × 5 | **16 formally enumerated actions** — 8 for Orchestration, 8 for State & Sovereignty |
| **Subsystem audits** (2026-08-09) | `2026-08-09_*_Oracle_phase4_99_audit.md` × 5 | Findings per subsystem, with test actions embedded in matrices rather than numbered lists for Net/Client, Tools/RAG and TUI |

The other three subsystems carry their 4.99 obligations inside their audit structure —
e.g. ToolsAndRAG's *Roadmap Pinning Matrix* maps finding **F-09** to test action
**TA-1** (tool profile confinement during multi-node scatter), and the TUI audit has a
dedicated *Phase 4.99 Production Boundary Feature Audit* section. So the real action
count is higher than 16; the two documents with numbered lists are just the tidiest.

### UT-1 — the round that certifies parallel execution

From `.oracle_artifacts/2026-08-30_phase_6_13_plan_lock_safety_and_multilane.md`.
Six tests, gated on Track A + UT-0:

1. Linear 3-step flow — completes, payload passes between steps, exactly one thread
2. 4-agent scatter — four lanes visible, `4/8` readout, merge waits for all
3. 8-agent scatter — `8/8` readout, measured speedup over sequential
4. `CTRL_REVIEW` mid-flow — pauses, HITL injection lands, step 3 consumes it
5. Cancel mid-scatter — stops promptly, no orphaned rows
6. **Kill a worker mid-node** — task not stranded; flow either recovers or stalls loudly

---

## 2. Where we actually stand

### Complete and gated

**Track A — lock lifecycle safety (A1–A6).** `locked_at` column, heartbeat on a daemon
thread, reclaim aged on lock acquisition rather than enqueue, guaranteed task
resolution, honest drain check with a distinct `stalled` outcome, registry-derived
model failover chains.

**Track D — scatter wiring (D1–D3 plus four follow-on defects).** Found and fixed by
live running, in this order, each revealed by fixing the one before it:

| # | Defect | Symptom |
|---|---|---|
| D1 | All 8 lanes seeded as flow entry points | Every agent executed **twice** — 16 inference calls for 8 lanes |
| D2 | Scatter routed to unhydrated node ids | Second, parallel, un-suffixed copy of every lane |
| D3 | `Tether_ID` dropped in the 15-column flatten | Every queue row had an empty tether |
| D3b | Blank UI field stored `""`, so `.get(k, default)` never fired | Tether still empty after the column existed |
| D3c | Overlay blanket-`update` blanked the topology's tether on control nodes only | Scatter and merge in **different scopes** → gather gate could never open → the run you stopped |
| — | Fan-in miscounted as runaway recursion when a lane failed | Merge cancelled at `loop=3`, never ran |
| — | Recursion limit inserted a node literally named `FAILED` | It was **claimed and ran real inference**, and its output became the next step's input |

**Gate status:** `omni qa` clean across **117 files** (Pyright blind spot closed —
`maccre.py` and `maccre_mcp.py` had never been type-checked and held 6 real errors,
now fixed), **665 tests passing**, `omni smoke` green.

### D-GATE closed

Run `job_20260831-041428-6goe` produced the target result:

```
Fan-in for CTRL_MERGE_S0 gathered 8 predecessor payload(s).
[CTRL_MERGE] CTRL_MERGE_S0: Merged 8 sources
peak_concurrency=8  cycles=10  spawned=8  errors=0  stalled=False
```

11 rows, one execution per agent, one tether on every lane and the merge, no orphans.

### Two defects still open — these are what you resume on

Both found by reading Gretchen's ledger from that same run. She said:

> `CTRL_MERGE_S0` merge acknowledged. Eight sources have been integrated.
> To determine who seems to know the most about roses [...] I require the actual
> content of the merged sources.

She was right on both counts, and her being right is the diagnosis.

**E1 — the merge received eight copies of the same document.** Every lane's
`payload_path` was `unified_session_ledger.md`, because agent nodes with
`Payload_Mode = "Unified Ledger"` route via the shared ledger rather than their own
output. So the gather returned 8 identical paths and the merge combined the same file
eight times — the output holds eight identical `## Source: unified_session_ledger`
sections. `Merged 8 sources` is literally true and semantically wrong. The lanes' real
outputs exist on disk as their own ledgers (`OSINT_Analyst_S0_85.md`,
`TopperBuddy_S0_86.md`, …) and were never read.

**E2 — the merge's output never crossed the step boundary.** The merge row correctly
pointed at `CTRL_MERGE_S0_merged.md` (426 KB), but the next step was queued with
`CTRL_MERGE_S0_93.md` — the merge's **59-byte ledger stub**. That was Gretchen's entire
input, at a cost of $0.000046. Cause: the step boundary reads `_find_final_ledger_path`
(globs the directory, picks by mtime) instead of the terminal node's `payload_path`.

Both are diagnosed to root cause with fix directions in the task list. **E2 is also the
first concrete instance of the provenance doctrine** — the merge's lineage broke, which
is the same failure class as an un-breadcrumbed import.

---

## 3. What you need to do — in order

### Step 1 · Fix E1 and E2 (not user testing; prerequisite to it)

Order matters. E1 decides what the merge *reads*; E2 decides what the next step
*receives*. Fixing E2 alone would faithfully deliver eight duplicates.

This does not need an expensive model — both are specified to root cause with a
665-test suite to check against.

One wrinkle recorded for whoever does E1: `route_task` overwrites the completing row's
`payload_path` with the routing payload, so under Unified Ledger mode the row stops
recording what that lane actually produced. A smarter query may not be enough; an
`output_path` column may be needed.

### Step 2 · UT-0 runs 2 and 3

Three consecutive instrumented 8-agent scatters on `gemini-3.7-flash`. Run 1 exists but
is **not a valid baseline** — it was measured while every agent ran twice and the merge
combined one source.

Record per run: `database is locked` count, peak concurrency, wall clock vs sequential,
worker deaths/stalls (`PoolResult.stalled` and `orphaned_locks` now report these), cost,
per-node latency spread. Tooling is at `scratch/_ut0_report.py` — takes a job id.

Two questions this answers:
- **§6.13 WAL sharding, go or no-go.** Current evidence says no: zero `database is
  locked` across every run so far, and the biggest throughput win came from *removing*
  contention (throttling the demand estimator took an 8-lane scatter from 4.25 s to
  1.26 s), not from adding capacity.
- **Auto-reclaim, go or no-go.** Zero worker deaths observed so far. Reclaim was made
  safe but deliberately left un-wired pending this data.

### Step 3 · Run UT-1 — the six tests above

All six are now unblocked. **Test 6 in particular was impossible before Track A** and
is the single highest-value test in the round, because it exercises the defect class
that caused the original rollback: kill a worker mid-node and confirm the task is not
stranded and the flow either recovers or stalls loudly rather than reporting success.

Practical notes:
- Use a simple payload. The `aevf` run failed a lane because `OSINT_Analyst` received a
  `CTRL_ANCHOR` passthrough as its "source document" and objected that it wasn't a real
  document. That was a payload problem, not an engine one. "Please tell me about roses"
  worked well precisely because nothing trips over its instructions.
- Leave Tether ID blank on both `CTRL_SCATTER` and `CTRL_MERGE`. It is auto-generated
  and propagated; typing one in is honoured but unnecessary, and the `CTRL_MERGE` field
  is not read for the merge the scatter auto-creates.
- A single `CTRL_SCATTER` step auto-wraps the whole scatter→lanes→merge DAG including
  its own merge. A separate standalone `CTRL_MERGE` step is redundant.

### Step 4 · Work the 16+ enumerated 4.99 actions

Once UT-1 passes, the per-subsystem actions are the remaining certification surface.
Start with Orchestration's 8, since that subsystem just changed most:

1. High-concurrency fan-out/fan-in with tether isolation ← *directly exercises D1–D3c*
2. Recursive loop boundary & max iteration guardrail ← *exercises the fan-in/recursion fix*
3. Quadrivector failback routing & fallback cascade
4. Predicate gate with async prerequisite wait & timeout halting ← *see the open timeout decision*
5. Dynamic next-node hydration & missing fallback recovery ← *exercises D2*
6. Swarm worker crash recovery & zombie task reclaim ← *exercises Track A; same as UT-1 test 6*
7. 7-point pre-flight validation under DAG anomaly injection
8. End-to-end context injection & flow lineage breadcrumb audit (`flow_vector`) ← *provenance*

Then State & Sovereignty's 8, then the actions embedded in the Net/Client, Tools/RAG and
TUI audits.

---

## 4. Two decisions owed by you

**(a) Timeout semantics.** `FlowRunner` breaks its step loop on `cancelled` and
`stalled` but **not** on `timeout` — a timed-out step lets the flow continue and the
session is still recorded `completed`. Same silent-success shape Track A removed for
stalls. My recommendation is to stop the flow and mark it `failed`, matching the stall
path. Not done unilaterally because it will fail flows that currently report success.
**This blocks 4.99 Orchestration Action 4**, which tests timeout halting.

**(b) omni disposition.** An independent assessment concluded omni is not
production-grade and not publishable as a repository: the task surface is a
Windows-only, MACCRE-hardcoded reimplementation of what `just`/`nox`/`pre-commit` do
better with pinned tool versions and CI parity. The zombie hunter (~150 lines) is the
one mechanic with no off-the-shelf equivalent. Recommendation was to migrate the task
surface into the repo, keep the hunter as a script, and publish the *audit* rather than
the tool. Full reasoning in `C:\OmniBuilder\omni-proposed-improvements.txt` and
`.oracle_artifacts/2026-08-30_omni_clean_hardening_audit.md`.

Three latent hazards in omni remain unfixed and are worth knowing about before running
it in an unfamiliar directory: it force-kills an image named after the **current
directory name**, unconditionally kills `chromedriver.exe`, and deletes root `*.log`
behind a MACCRE-specific allowlist.

---

## 5. One observation worth carrying forward

The 2026-08-09 Orchestration audit's first listed finding was:

> **CRITICAL BROKER BUG: Missing `tether_id` in `route_task()` & Storage Layer
> Disconnect**

That is D3. The Oracle identified it **three weeks before** it cost three live runs and
a deadlock to rediscover. Its second finding — the `UNIQUE(job_id, current_node)`
collision — is the constraint that shapes Task B2. Its third — worker crash recovery and
zombie lock timeout — became Track A.

The audits were right. The findings were not actioned. Whatever the Eisenhower planning
map recommends, the mechanism that turns an audit finding into scheduled work is worth
more than any individual finding in it.

---

## 6. Environment state on handover

```
Track A                complete, gated
Track D (D1-D3+4)      complete, gated
D-GATE                 closed (Merged 8 sources, run 6goe)
E1 / E2                open, diagnosed, fix directions recorded
omni qa                clean, 117 files, 0 errors
pytest                 665 passed
omni smoke             ALL CHECKS PASSED
tree                   0 stale .pyc, 0 orphaned processes, PID registry pruned
FeatureRequests.md     33 entries, copy in .kiro_artifacts
```

Nothing is committed. Baseline is `f7b326f` on `main`.
