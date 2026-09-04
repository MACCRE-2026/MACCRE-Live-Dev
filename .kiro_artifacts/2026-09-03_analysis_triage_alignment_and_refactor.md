# Analysis Triage — Alignment Items and Refactor Candidates

**Written:** 2026-09-03
**Source:** `.kiro_artifacts/2026-09-03_MACCRE_competitive_and_strategic_position.md`
**Nature:** Triage. Sorts that analysis into work. Adds two findings it did not have.
**Status of the source:** its §6.1 list is partly closed already — see §0.

> **Why two lists and not one.** The distinction is not size, it is whether the thing can
> reach correctness *in its current shape*. An alignment item is wrong and can be made right
> where it stands. A refactor candidate is not wrong — it is structurally incapable of the
> job being asked of it, and editing it in place produces a better version of the wrong
> thing. Mixing them is how a project spends a year polishing something it should have
> replaced, or rewrites something that needed one line.

---

## 0. What the analysis asked for that is already closed

Recorded so this document does not re-raise settled work. All 2026-09-03.

| Source item | State | Evidence |
|---|---|---|
| §6.1 #1 Push (public half) | **CLOSED** | `phase/6.13-track-a-d-and-payload-lineage` pushed, upstream set, 0 ahead. 10 commits |
| §6.1 #1 Push (`tests/` backup) | **CLOSED, differently than proposed** | The analysis proposed a *second private* remote. Operator chose to publish. Pre-publication audit: 54 files, 18 patterns, 0 credential findings; 27 `.py` / 11,505 lines tracked, 27 `.pyc` excluded. Commit `a743c18` |
| §6.1 #3 Correct the status gate line | **CLOSED** | §11 appended to the 4.99 artifact; `753/1` recorded with the test named. Dating standard adopted |
| §6.1 #6 DDL register entries | **CLOSED as one entry, not two** | Both exposures in a single entry; the shared root cause is one DDL with three owners, and splitting it would have produced two entries with one remedy |
| §6.2 Addition A had no register entry | **CLOSED** | Event-sourced history now has its own entry, recommended as the Epoch 4 gate |
| Slot-failure lead had no register entry | **CLOSED** | Entry exists, `Verified:` marked observed-not-reproduced |

**Still open from §6.1:** #2 (reproduce the slot test), #4 (registry counts), #5
(`ASSISTANT_NAME`), #7 (register counting rule).

**Still open from §6.1 #1:** `Analysis/` (33 files), `History/` (42), `scripts/` (65),
`__DATACENTER/` (1985) remain on one disk. The analysis's *private* remote recommendation is
unaddressed — publishing `tests/` solved the highest-value case, not the general one.

---

## 1. Two findings the analysis did not have

Both surfaced while executing its §6.1 #1, and both change how its other findings should be
read.

### 1.1 The quality gate had been silently excluding whatever the privacy list excluded

Ruff's `respect-gitignore` defaults to true and honours `.git/info/exclude`. That file is
where this project keeps its private-internals list. So a control meaning *do not publish
this* was also enforcing *do not check this*.

`ruff.toml` line 17 asserts the opposite:

```toml
per-file-ignores = { "tests/*" = ["F841"], "scripts/*" = ["E402", "E401"] }
```

Naming a per-file-ignore for a path states the path is linted. Both were named. Neither was
visited. Seventeen errors were hiding from a **whole-project** `omni qa`, three of them
`F821 undefined-name` in `scripts/maccre_micro_test.py` — a partial rename of
`get_provider_credential` → three stale `get_native_credential` call sites, in `_run()`
probes covering model-registry surfaces and the sentinel health report. Those three probes
could never execute.

**Why this changes the reading of the analysis.** The analysis treats `omni qa` results as
sound, and for `maccre_core` they were — it was always in scope. But it also builds an
argument on *the gates covering everything except the goal* (§1.4, blind-spot table). That
argument is stronger than it knew: the exclusion was not only `pyrightconfig.json` declining
`maccre_tui`, it was a privacy file silently narrowing ruff across four directories, with a
config file claiming otherwise. This is the analysis's own §1.5 pattern — a claim nothing
checks — in the gate itself.

**Also:** every `omni qa PASS` recorded in any artifact before 2026-09-03 was true only of
the non-excluded tree, and none of them say so.

### 1.2 The analysis's §7 "could not determine" list is now shorter by zero, and that is worth stating

Its two reproduction questions — whether `pattern_executor` / `nexus_plex` DDL paths are
live, and whether the slot failure is over-provisioning or slot reuse — are **still
unanswered.** Nothing done today touched them. Recorded explicitly because a triage document
that quietly drops open questions is how they get lost.

---

## 2. List A — Alignment items

Wrong, and fixable where they stand. Ordered by cost of leaving them.

| # | Item | What is untrue now | Done when | Size |
|---|---|---|---|---|
| A1 | **`--no-respect-gitignore` in omni's ruff call** | Privacy exclusions shrink the gate. `ruff.toml` names two paths the tool never visits | `omni qa` reports the 13 remaining `scratch/`+`_legacy/` findings, or they are named in `ruff.toml` `exclude` as a visible decision | S, in `C:\OmniBuilder\omni.py` |
| A2 | **Registry self-counts** (§1.1) | Comment `── Active (16) ──` sits over 17 active rows; `_seed_builtins` docstring says 23 over 25 | A test asserts comment count == docstring count == `len(_BUILTIN_NODES)`, and fails when they diverge | S |
| A3 | **Register counting rule** (§1.5) | Four documents cite four numbers: 51, 53, 56, 33/40. Current true count is 60 headings | Rule stated in the Entry Doctrine; `omni` prints it; documents cite the tool | S |
| A4 | **`ASSISTANT_NAME` indirection** (§6.1 #5) | The literal is scattered. Two artifacts in three days cannot be published without it | One definition site; grep for the literal returns only it | S |
| A5 | **Narrow the "zero-dependency" claim** (§1.2) | False of the project. `requirements-sovereign.txt` declares 13 packages including `google-genai` and `requests`; `live_client.py` imports `google.genai` as a documented exception | Every doc says *the inference path to the primary provider is stdlib-only*. Verifiable in one file | S |
| A6 | **`win10toast` is in sovereign core, not optional** (§1.2) | Risk R1 in the Eisenhower map understates the Windows coupling — it is in the core manifest, not only call sites | R1's wording matches the manifest, or the dependency moves to optional | S |
| A7 | **Name the trust rule after its ancestor** (§3.5 #3) | Doctrine 1 presents ceiling-from-minimum as native. It is Biba 1977 low-water-mark, shipping in FreeBSD as `mac_lomac` | Doctrine 1 names Biba/LOMAC and keeps the incident that derived it | S, doc-only |
| A8 | **Adopt PROV's three words** (§3.5 #2) | The union-of-inputs corollary is W3C PROV-DM, a 2013 Recommendation. Not the RDF — just entity / activity / derivation | Doctrine uses the vocabulary; no fourth private encoding is invented | S, doc-only |
| A9 | **Reconcile the two exclusion lists** | `ruff.toml` deliberately excludes `_archive` and `user_scripts`; `_legacy` and `scratch` are excluded only by accident of git | Each directory's lint status is a stated decision in one file | S |
| A10 | **Answer the 10-minute reachability question** (§7) | Whether `pattern_executor` and the `nexus_plex` DDL path run in normal operation. Decides whether the DDL entry is two defects or two dead branches | The register entry's `Verified:` line says reachable or vestigial, with how it was determined | S, but it is a *measurement*, not a fix |
| A11 | **Private remote for `Analysis/` `History/` `scripts/` `__DATACENTER/`** | 2,125 files on one disk. `tests/` was the highest-value case and is now safe; the general case is not | Those paths exist on a remote that is not `B:` | S, but **operator-only**: it is a publication decision |

**A2 deserves a note on why it is worth an hour.** It is trivially small and it is the file
whose entire purpose is to end hand-maintained node tables. A stale count *in the registry*
is the analysis's Principle-5 finding at its most embarrassing, and Persona 2 dismisses the
project in ninety seconds on "16 control nodes" when the registry says 17 of 25. The fix is
cheap; the test that keeps it fixed is the point.

**A7 and A8 are the cheapest credibility work available.** Both are documentation edits with
no code consequence. The analysis is blunt that publishing the trust ceiling as novel is
"indefensible and easily falsified by any reader with a security background", and that
naming it *the Biba low-water-mark model applied to LLM summarisation* is "strictly more
persuasive." Same idea, better provenance, one paragraph of work.

---

## 3. List B — Refactor candidates

Not wrong. Structurally unable to do the job being asked, so editing in place yields a
better version of the wrong thing. Ordered by what blocks what.

### B1 — Event-sourced execution history · **the gate on everything else**

**Current form.** `task_queue.lock_status` is mutated in place. `open` → `locked` →
`completed`, each transition overwriting the last. There is no `task_events` table anywhere
in the tree.

**Why it cannot get there.** The table answers *what is*. Every provenance ambition in the
register needs *what happened*. You cannot make an append-only provenance record out of a
substrate that overwrites — the doctrine's own append-only corollary is violated by the table
it would run on. This is not a missing column.

**What it unblocks in one move:** the system-wide provenance doctrine; the containerized
session archive (the "immutable record of the session" *is* the event log); CrumbRunner
(nothing to attest over); run reconstruction — which is what session `40sp` stuck at
`active` and the 12-day stranded `locked` row both are.

**And it is the missing half of the pattern already converged on.** Temporal, Durable
Functions, Restate and Obelisk all split deterministic control from non-deterministic
execution, and in every one the split is *load-bearing on replay*. MACCRE took the split and
left the history, so its determinism is a convention about which node types call an LLM
rather than a property anything verifies.

**Shape.** Additive: append-only `task_events` beside the existing `task_queue`, one row per
transition with actor, timestamp, content digest. The queue stays as the fast current-state
index. **Do not touch the claim path** — `BEGIN EXCLUSIVE` is the strongest thing in the
codebase and the analysis calls the claim fully defensible.

**Sequencing consequence, stated as the analysis states it:** building CrumbRunner or any
private provenance implementation before this exists is *the single most likely large mistake
available right now, and the most attractive item in Epoch 4.*

### B2 — One owner for the `task_queue` DDL

**Current form.** Three `CREATE TABLE IF NOT EXISTS task_queue` statements, three column
sets: `local_broker.py` (14 + 8 `ALTER` upgrades, has `output_path` and `UNIQUE`),
`pattern_executor.py` (10, no `output_path`), `nexus_plex.py` (11, no `UNIQUE`, but issues
`INSERT OR REPLACE`).

**Why it cannot get there.** `CREATE TABLE IF NOT EXISTS` is a no-op against an existing
table, so whichever path opens the database first silently decides the schema for every other
path. Adding the missing columns to the other two files produces *three* correct-today DDLs
that will drift again — which is the same Principle 4 failure the node-ID divergence already
recorded. The fix is not three edits; it is one seam the other two read through. The broker
already owns the migration idiom and the recovery index.

**Do A10 first.** If both paths are vestigial this is a deletion, not a refactor, and the
size changes by an order of magnitude.

### B3 — `maccre_tui` inside both gates

**Current form.** Excluded from `pyrightconfig.json` entirely; 112 measured real diagnostics;
F3's two-line `nexus_plex` wiring — the thing that makes the abandoned-pause mechanism live —
has no test and no type check. Now inside ruff as of today, for the first time.

**Why it cannot get there incrementally.** Removing the `exclude` while 112 diagnostics exist
turns the gate red permanently, which trains everyone to ignore it. Staged, and the order is
forced: fix the 112 → remove the `exclude` → add the regression test asserting the *effective*
file set matches the include list.

**Why it ranks high despite being unglamorous.** The end goal is an interface. Both gates
excluded the goal. The analysis names this the one place MACCRE is measurably *behind* cohort
4a — a Langflow user at least has a maintained UI — and marks the cost "High, and rising."

### B4 — Determinism by enforcement rather than convention

**Current form.** `CTRL_` nodes are deterministic because they are written not to call an LLM.
Nothing verifies it.

**Why it cannot get there in place.** No test or sandbox would catch a `CTRL_` handler that
became non-deterministic. The `CTRL_RECURSION` incident is exactly this class — a node named
`FAILED` that was claimed, ran real inference, and fed the next step. That is what replay
verification catches and convention does not. Depends on **B1**: replay needs a history.

**Cheap partial available now:** a test asserting no `CTRL_` handler transitively reaches the
inference client. Not replay, but it converts a convention into a checked claim, which is the
doctrine-5 standard.

### B5 — CTRL_MERGE / CTRL_CONCAT subsumed into a Gather Strategy

**Current form.** Merge and concat are standalone nodes. The operator's decision is *subsume,
not replace* — a Gather Strategy on `CTRL_SCATTER` including `Ungathered`, while keeping
downstream merge/concat able to pull from separate points in a flow.

**Why it is a refactor and not a feature.** It carries two prerequisites the current shape
cannot express: a **temporal-paradox validation** that rejects a configuration creating an
impossible `WAIT` at launch, and a **total-sum configuration readout** that describes the
active flow before the launch button is pressed. Both require the topology to be inspectable
as a whole rather than node-by-node, and the vision behind it — each scatter lane as its own
independent topology that may never merge — changes what a lane *is*. Hard replacement was
already rejected because it breaks saved MacroNodes.

### B6 — Private encodings → standard vocabularies

**Current form.** `flow_vector` is a private lineage encoding; telemetry is structured JSON
plus SQLite in bespoke shapes; node ids, topology CSV and `flow_vector` are three private
encodings already.

**Why deferred, not urgent.** Each is individually reasonable; collectively they make the
project unreadable from outside. Three separable pieces, none urgent: PROV vocabulary (A8
covers the doctrine half cheaply), OTel GenAI spans, and OpenLineage-shaped lineage. The
analysis rates OTel "cheapest possible interoperability, no architectural commitment."

### B7 — Signing at the Sovereign Importer seam only

**Current form.** No DSSE envelope, no signature, no verifier anywhere.

**Why scoped this narrowly.** The analysis is explicit that SLSA and in-toto are the *wrong*
comparison for the internal model — SLSA deliberately declines transitivity, which is the
exact rule MACCRE cares about — and that signing becomes relevant only where an artifact
leaves the operator's trust boundary. That is the Importer seam and nowhere else.
**Trigger:** the first time anything crosses to a party who is not the operator. Depends on
**B1**; a signature over a history you cannot replay is a signature on a summary.

### B8 — The demand estimator, conditionally

**Current form.** `swarm_pool.py:619`,
`target = min(self.max_workers, max(1, self.active_worker_count() + ready))`. With one worker
active and one row visible as ready, `target` becomes 2 — so a linear flow can spawn a second
worker while the first is still finishing.

**Why conditional.** This is a **lead, not a finding**. It is not distinguished from benign
slot-id reuse via `_free_slots`. If reproduction shows genuine over-provisioning it becomes a
refactor and, per the analysis, *the most urgent item in §6.1 ahead of everything except
pushing* — because the estimator is the component UT-0 exists to measure. If it is slot reuse,
it is a one-line assertion fix and belongs in List A.

**First step is instrumentation, not a fix:** make the tracker record whether two slots were
ever simultaneously *inside node execution*. That distinguishes the two in a single run.

---

## 4. The dependency order, since three of these block others

```
A10 (reachability)  ──►  B2 (one DDL owner, or a deletion)

B1 (event history)  ──►  B4 (replay-enforced determinism)
                    ──►  B7 (signing at the seam)
                    ──►  CrumbRunner / provenance doctrine / session archive
                             [all currently in Epoch 4, all blocked]

B8 instrumentation  ──►  either B8 refactor or a List A assertion fix
                    ──►  UT-0 baseline

B3 is independent and can run in parallel with all of it.
```

**The one-sentence version:** B1 is the gate, B3 is the goal, and everything filed under
provenance is waiting on B1 without saying so.

---

## 5. What this triage does not decide

- **Whether to publish anything, and under what name.** A4 is a prerequisite, not a decision.
- **The §6.3 negative list.** Eleven planned items the analysis recommends withdrawing or
  reducing. Each needs its own `WITHDRAWN` entry with rationale under the Second Amendment.
  That is a separate deliberate pass and is deliberately absent here — folding it into a
  triage document would bury eleven judgement calls inside a work list.
- **The three payload-contract questions** from §10 of the 4.99 status document. The analysis
  says they sit ahead of any new work and are unchanged by it.
- **Anything about `B:\SovereignImporter`.** Not read, not written. B5 and B7 touch the
  contract; any work needed on their side is a TFR.
