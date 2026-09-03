# Phase 4.99 — Where User Testing Stands, and Why It Is Paused Here

**Written:** 2026-09-02
**Supersedes as a status report:** `.kiro_artifacts/2026-08-31_phase_4_99_user_testing_handover.md`
(that document remains the better explanation of *what 4.99 is* and of the Track A / Track D
history; this one replaces its §2 "where we actually stand" and §6 "environment state")
**Audience:** whoever resumes 4.99, including the operator after a break
**Nature:** status plus the reasoning for the pause. It is not a plan.

---

## 1. The one-paragraph version

4.99 user testing **started** on 2026-09-01 and is **paused after four live runs**, with
**four of UT-1's six tests effectively passed** and **UT-0 not begun**. Five defects were
found and fixed in those two days — two of them (E1, E2) diagnosed earlier and now confirmed
fixed *in production*, three of them (F1, F2, F3) discovered by the testing itself. The pause
is **not** because testing hit a wall. It is because live running exposed that **the contract
governing which payload a node receives is not settled**, three defects were found inside
that one contract in 48 hours, and two of the open questions are operator decisions rather
than engineering ones. Continuing to certify behaviour against a semantic that is about to
change would produce evidence with a short shelf life.

---

## 2. UT-1 — four of six

From `.oracle_artifacts/2026-08-30_phase_6_13_plan_lock_safety_and_multilane.md`.

| # | Test | Status | Evidence |
|---|---|---|---|
| 1 | Linear 3-step flow — completes, payload passes between steps | **Pass**, with a caveat | `tjrd`: 3 steps, boundary handoff visible in the log |
| 2 | 4-agent scatter — four lanes, `4/8` readout, merge waits for all | **Not run** | — |
| 3 | 8-agent scatter — `8/8` readout, measured speedup | **Pass on width only** | `tjrd`: `peak_concurrency=8`, `errors=0`. **Speedup never measured** |
| 4 | `CTRL_REVIEW` mid-flow — pauses, HITL injection lands, step 3 consumes it | **Pass on the letter**, fails the intent | `tjrd`: pause held, injection landed, step 3 consumed it — see §5 |
| 5 | Cancel mid-scatter — stops promptly, no orphaned rows | **Pass** | `ico6`: 9 completed + 1 cancelled, no orphans |
| 6 | **Kill a worker mid-node** — task not stranded; recovers or stalls loudly | **Not run** | Still the highest-information test in the round |

**Test 1's caveat and test 4's failure are the same defect**, and they are the reason for the
pause. Both "passed" against their written criteria while delivering something the operator
did not intend. See §5.

**Test 3's speedup half is a real gap**, not a technicality. Width is proven deterministically
by `threading.Barrier(8)` in the suite and by `peak_concurrency=8` live. Elapsed-time benefit
has never been measured on a real run, and the only wall-clock test in the suite is
load-sensitive (§8).

## 3. UT-0 — not begun, and it needs three runs rather than two

The 2026-08-31 handover says "runs 2 and 3", assuming run 1 counted. **It does not**, and the
count is now three fresh runs, for two compounding reasons:

1. Run 1 (`6goe`) was explicitly declared not a valid baseline — it was measured while every
   agent executed twice and the merge combined a single source.
2. Everything measured before 2026-09-02 predates E1/E2/F1/F2/F3 and commit `83950b6`, which
   changed merged-artifact size materially (§4). Nothing measured earlier is comparable to
   anything measured later.

None of the four runs below is a valid UT-0 datapoint: `ico6` and `40sp` were deliberately
interrupted, `tjrd` was a 3-step HITL flow rather than a clean instrumented scatter, and none
was recorded through `scratch/_ut0_report.py`.

**Per-run recording obligation, unchanged:** `database is locked` count, peak concurrency,
wall clock against the sequential equivalent, worker deaths and stalls (`PoolResult.stalled`,
`orphaned_locks`), cost, per-node latency spread.

**Two go/no-go decisions still waiting on this data:** §6.13 WAL sharding, and wiring
auto-reclaim. Evidence so far points to *no* on both — zero `database is locked` across every
run to date, and the largest measured throughput win this phase came from *removing*
contention rather than adding capacity.

## 4. The four live runs, as evidence

| Run | Intent | Outcome | What it established |
|---|---|---|---|
| `job_20260831-041428-6goe` | D-GATE | `completed`, 11 rows | Closed D-GATE. Also produced E1/E2: `Merged 8 sources`, all eight the same file, and a 59-byte stub crossing the step boundary |
| `job_20260901-204957-ico6` | **cancel** mid-run | `cancelled`, 9+1, no orphans | UT-1 test 5. First live evidence E1 was fixed |
| `job_20260901-205047-40sp` | **pause** mid-run | **`active`** — see §9 | Produced F1, F2 and F3 in one keypress |
| `job_20260902-132101-tjrd` | clean 3-step + HITL | `completed`, 12 rows, $0.052553 | **E1 and E2 both confirmed fixed in production.** UT-1 tests 1, 3, 4 |

### The E1 / E2 confirmation, stated precisely

E1's acceptance shape was "eight **distinct** `## Source:` sections naming eight different
lanes". `tjrd` delivered exactly that:

```
## Source: OSINT_Analyst_S0_116      ## Source: Testy_S0_121
## Source: TopperBuddy_S0_117        ## Source: Regular_Joe_S0_122
## Source: TopperAngry_S0_118        ## Source: TestAgent_S0_123
## Source: TopperShepherd_S0_119     ## Source: NewGuy_S0_120
```

E2's was "the following step receives the merged document, not the 59-byte stub":

```
[FLOW_ENGINE] Output captured: ...CTRL_MERGE_S0_merged.md
[FLOW_ENGINE] Queued entrypoint: CTRL_PAUSE_MANUAL_S1 with payload '...CTRL_MERGE_S0_merged.md'
```

68,082 bytes crossed the boundary, with `CTRL_MERGE_S0_124.md` (59 bytes, newer mtime) sitting
in the same directory and not chosen. **Both defects are closed on live evidence, not on unit
tests.**

`tjrd` also exercised F1 without anyone noticing: the HITL pause calls
`_set_vcr_state("paused")`, which is the exact render that crashed the app on `40sp`. It
survived.

## 5. Why it is paused here

Three defects were found inside one contract — *which payload does a node receive* — in 48
hours: E1 (a lane's output was unrecorded), E2 (a step's output did not cross the boundary),
and then the two below. That is not a run of bad luck; it is a contract that was never
specified.

### (a) `Payload_Mode` has never been honoured at a step boundary

The unified session ledger is written to `04_Code_Artifacts/<job>/unified_session_ledger.md`.
Step boundaries read the terminal node's recorded output, which lives in
`03_Agent_Ledgers/<job>/` — and the pre-E2 mtime glob only looked in `03_` as well. **So the
unified ledger has never crossed a step boundary, before or after E2's fix.** `Payload_Mode`
is consulted only for agent→agent hops *inside* a step, and there it reads the **successor's**
mode.

Consequence: a single downstream agent authored as "Unified Ledger" does not inherit the
session ledger. It receives the previous step's terminal output. This is why the run's final
agent behaved as though it had no source material.

**This is a semantic decision, not a bug fix.** Making step boundaries honour `Payload_Mode`
changes what *every* multi-step flow passes.

### (b) `Preceding Node Only` is offered in the UI and implemented nowhere

`nexus_plex.py:2071` offers `Unified Ledger` and `Preceding Node Only`. No branch anywhere
reads the second value. It works by falling through to the default path, which happens to
retain the completing node's own ledger — accidentally correct for intra-step hops, absent at
step boundaries.

This blocks the operator's stated HITL design directly, because that design is *conditioned on
the mode*: "if Unified Ledger is selected the downstream agents see an entry on the ledger from
the user; if Preceding Node is selected then the node ledger preceding `CTRL_REVIEW` **and**
the HITL injection pass downstream." You cannot condition on a mode that only works by
omission.

### (c) The HITL injection replaces the payload instead of accompanying it

`_hitl_resume_with_context` writes the operator's text to `HITL_injection.md` and calls
`resume_paused_task(job_id, hitl_payload_path)`, which **overwrites** the paused row's
`payload_path`. On `tjrd` the 68 KB merged document was displaced by 125 bytes, the pause node
recorded no `output_path`, and the next step was queued with the injection alone. The final
agent asked for the source document it had never been given.

Stated intent is **accompany, not replace** — and the correct behaviour is defined in terms of
(a) and (b). All three are one design, which is why fixing (c) alone was declined.

### (d) The architectural question underneath all of it

The operator's vision for `CTRL_SCATTER` is **topological**: each Flow Lane an independent
topology, nestable scatters, downstream agents on individual lanes, deterministic and
conditional routing *between* lanes, and lanes that **may never merge** — ending in an output
ledger collected later by a `CTRL_WAIT` node aimed at a specific agent on a specific lane.

Checked against `.kiro/specs/phase-6-13-multi-flow-lane/`:

| Vision element | Status in the spec |
|---|---|
| Nested scatter, depth/lane limits | **Present** — Requirement 19 |
| Per-lane node insertion, tether inheritance | **Present** — Requirement 18 |
| Lanes as `FlowStep.children` sublists, recursive serialisation | **Present** — Requirement 17 |
| **A scatter that never merges** | **Contradicted** — Req 19.4 mandates that all scatter branches have a corresponding `CTRL_MERGE` *before execution is allowed* |
| **Routing between lanes** | **Absent.** The tether hierarchy is a containment tree, not a routing graph |
| **`CTRL_WAIT`** | **Absent.** No occurrences anywhere; not among the 16 `CTRL_` types |

This matters for 4.99 specifically because **E2's fix assumes one output per step**, and
`_capture_step_output` treats multiple terminal nodes as an anomaly to warn about. Under the
topological vision, N un-merged lane terminals is the *normal* case and "the step's output"
stops being a single thing. Certifying the step boundary now would certify an assumption the
architecture is scheduled to break.

### Why pausing is the right call rather than pressing on

Two of UT-1's remaining tests (**2** and **6**) do not touch the payload contract and could be
run today — see §7. But the 4.99 Orchestration action list is largely *about* payload and
lineage: Action 1 (fan-out/fan-in with tether isolation), Action 5 (dynamic hydration), Action
8 (end-to-end context injection and `flow_vector` lineage audit) all certify behaviour that
questions (a)–(c) would change. Certifying them twice is worse than certifying them late.

## 6. What was fixed during this testing

| ID | Defect | Commit |
|---|---|---|
| E1 | Fan-in gathered the shared session ledger instead of each lane's own output | `c9b29a5` |
| E2 | A step's output did not cross the step boundary (mtime glob chose the 59-byte stub) | `c9b29a5` |
| F1 | The VCR pause button crashed the entire TUI (zero-width content box) | `15f5ee4` |
| F2 | A held pool rebuilt a full worker ~20×/second, indefinitely | `15f5ee4` |
| F3 | A hold nobody could release ran to budget, then reported `completed` | `15f5ee4` |
| — | **Timeout decision closed**: a timed-out step now stops the flow and records `failed` | `15f5ee4` |
| — | The merge restated the session ledger, doubling its own output | `83950b6` |
| — | `_hydrate_topology` had three call sites drifted three ways | `83950b6` |

Every one was reproduction-verified by reverting the fix and confirming the new tests fail with
the production signature. Detail in `.oracle_artifacts/2026-09-01_e1_e2_payload_lineage.md` and
`.oracle_artifacts/2026-09-01_f1_f2_f3_pause_path.md`.

**`failed` now covers four conditions** — exception, stall, timeout, abandoned pause — and
`job_sessions` has no reason column, so the distinction lives only in the log. Accepted
deliberately: a wrong `failed` is conservative, a wrong `completed` propagates. Two SOPs were
raised to the Sovereign Importer team, the second withdrawing the
`completed`-is-not-proof caveat and widening `failed`.

## 7. What is runnable without any decision

If testing resumes before the design questions are settled, these are safe and additive:

1. **UT-1 test 6 — kill a worker mid-node.** Independent of the payload contract, impossible
   before Track A, and the highest-information test in the round. It exercises the defect class
   that caused the original rollback.
2. **UT-1 test 2 — 4-agent scatter.** Checks the `4/8` readout and that the merge waits. Also
   independent.
3. **Press pause once in a live TUI.** F1 is verified as arithmetic, not pixels, and **F3's
   two-line wiring in `nexus_plex.py` is covered by no test at all** — `maccre_tui` is outside
   both the Pyright include list and the suite's reach. Those two lines are what make the
   whole abandoned-pause mechanism live. Ten seconds of work.
4. **UT-0 ×3** could technically start, but any baseline taken before (a)–(c) land will not be
   comparable to post-decision runs. Deferring is the better economy.

## 8. Environment state, 2026-09-02

```
branch          phase/6.13-track-a-d-and-payload-lineage
commits         5 ahead of origin/main — NOTHING PUSHED
                83950b6  merge dedupe + hydrate drift
                15f5ee4  F1/F2/F3 + timeout
                c9b29a5  E1/E2
                762f614  Track A + D checkpoint
                f7b326f  (was already unpushed)
omni qa         PASS, whole project
pytest          754 collected / 754 passed, 22 test files
omni smoke      ALL CHECKS PASSED
register        51 entries
C: free         2.26 GB   (was 0.11 GB — see below)
pip cache       F:\pip_cache   (%APPDATA%\pip\pip.ini)
npm cache       F:\npm_cache   (~\.npmrc)
```

**The disk incident, recorded because it produced a false gate result.** Mid-session a gate run
reported `PYRIGHT FAILED` and 259 pytest errors. Neither was real: C: had 0.11 GB free, so
pyright's npm shim could not write (`ENOSPC`) and every test using `tmp_path` failed, because
`tests/conftest.py` points `MACCRE_ROOT` at `tmp_path` and that lives on C:. Re-running with
`TEMP` on B: gave 754 passed. Caches have since been relocated to F: and the gate above is a
genuine run. **`tests/conftest.py` still puts 754 datacenter trees on C: on every run** — a
one-line change would remove MACCRE from that failure mode entirely.

**Two risks unchanged from 2026-08-31:**

- **Nothing is pushed.** Five commits exist only on this disk.
- **`tests/` is not in version control at all**, along with `Analysis/`, `scripts/` and
  `.oracle_artifacts/`, excluded by `.git/info/exclude` as a deliberate public/private split.
  So the 754-test suite and every audit artifact have no backup. A second private remote is the
  obvious answer; changing the exclude file would publish private internals to a public remote
  and is not an agent's call.

## 9. Residuals and loose ends

- **`job_20260901-205047-40sp` is stuck at session status `active`.** Its process was killed
  during the F2 runaway, so the `finally` that records a terminal status never ran. Worth
  knowing because anything enumerating sessions by status will see a session that looks live
  and is not — including the Session Manager work and any Importer integration.
- **A stranded `locked` row from `studio_session__job_20260820-020251-xj6z`**, dated
  2026-08-20. One task claimed and never resolved, twelve days old. Relevant because Chat Studio
  session concurrency is a stated near-term goal and this is a pre-existing zombie in that path.
- **The flaky wall-clock test.**
  `test_eight_lane_scatter_beats_sequential_wall_clock` asserts an 8-lane scatter finishes in
  under 60% of sequential. It fails under full-suite load (measured 1.70 s against a 1.20 s
  bound) and passes in isolation and 32/32 in its own file. The companion barrier test pinning
  `peak == 8` passes in the full run, so width is intact. Untouched: loosening the bound,
  raising the simulated node time, or accepting the flake is an operator decision. **It also
  means UT-1 test 3's speedup criterion has no trustworthy automated proxy.**
- **Two verified defects still owed register entries**: `Payload_Mode` not honoured at step
  boundaries, and `Preceding Node Only` unimplemented. Diagnosed in `83950b6`'s commit message.
  Recording them is the R3 discipline this project has already paid for twice.
- **Three leads recorded but unreproduced**: the agent overrides modal not loading the selected
  agent's profile; `FlowExecutionPanel` as a dead duplicate with a colliding `btn-vcr` id; the
  `maccre_tui` Pyright exclusion, measured at 112 real diagnostics.

## 10. Resuming

**Answer the three questions first.** They are in §5 and they are cheap to answer and expensive
to defer:

1. Should a step boundary honour `Payload_Mode`?
2. Implement `Preceding Node Only` properly?
3. Write up the topological-scatter vision as register entries — including that Requirement 19.4
   currently forbids the no-merge lane the vision requires?

**Then, in order:** implement (a)–(c) as one design → run UT-1 tests 2 and 6 → UT-0 ×3 on a
stable payload contract → the 16+ enumerated 4.99 actions, Orchestration's eight first.

**Tooling that exists and will save time:**

- `scratch/_latest_session.py 499_TEST 3` — recent sessions with both path columns
- `scratch/_inspect_runaway.py <job_id>` — full queue dump for one job
- `scratch/_ut0_report.py <job_id>` — the UT-0 instrumentation
- `scratch/_pyright_tui_probe.json` + `_summarise_tui_probe.py` — re-measure the TUI exclusion

**The single fastest confidence check on resume** is to press pause once in a live TUI. It
covers F1, F2 and F3 at once, and F3's wiring currently has no automated coverage whatsoever.
