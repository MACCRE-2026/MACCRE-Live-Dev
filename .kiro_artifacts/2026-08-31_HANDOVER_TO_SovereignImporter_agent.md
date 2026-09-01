# Handover: MACCREv2 → Sovereign Importer

**From:** the MACCREv2 engineering agent (workspace `B:\EXO_GANS`)
**To:** the Kiro agent working in `B:\SovereignImporter`
**Date:** 2026-08-31
**Nature:** integration handover. States what MACCRE needs from you, what MACCRE has
already decided that constrains you, and what MACCRE will get wrong if you assume the
obvious thing.

> ## ⚠ READ §11 FIRST — REVISION 2 SUPERSEDES PARTS OF THIS DOCUMENT
>
> Sections **1, 4.2, 5.3 and 6** below were written on a **materially wrong model of
> the trust boundary.** They are left in place because the corrected reasoning in §11 is
> only legible against what it replaces.
>
> The short version of what was wrong: this document originally framed Sovereign
> Importer as "the ingestion side" and MACCRE as "the consumer", with MACCRE isolating
> your data. **The real architecture is the inverse.** Sovereign Importer is a sovereign
> local knowledge center and MACCRE's *only* window on the outside world; you gate
> MACCRE, not the reverse. §11 also corrects a claim about MACCRE's project provisioning
> that was verified and found backwards.
>
> Read **§11**, then **§9** (what your schema already gets right), then **§10**
> (transferable principles). Treat §§1–8 as historical except where §11 confirms them.

---

## 1. Orientation

You are building the ingestion side of a shared architecture. MACCRE is the consumer.
Neither project should design the boundary alone, and this document is the MACCRE half
of that conversation — **not a specification you are obliged to implement.** Where I
have made assumptions about your side, they are marked.

**What I did to write this.** I read `sovereign_importer/core/models.py` in full, dumped
the live `conversations.db` schema and row counts read-only, listed the package and
tools layout, and skimmed `handover.md`'s structure. I did **not** read
`core/importer.py`, `core/datacenter.py`, or the parsers in detail. Corrections welcome
and expected.

### What I found on your side

| Fact | Value |
|---|---|
| Conversations | **439** |
| Messages | **9,525** |
| Attachments | 1,322 |
| Tool calls / artifacts | 0 / 0 (tables exist, unpopulated) |
| Platforms registered | `kiro`, `antigravity`, `aistudio` |
| Markdown corpus | 439 files in `01_Raw_Source/AIStudio_Imports` |
| DB size | ~43 MB, `journal_mode = wal` |

**The operator refers to this corpus as "490-odd conversations". The database says 439,
and `models.py` mentions 451 files on disk.** Not pedantry — the migration KPI in §4.4
counts sessions, so the baseline number needs to be one agreed figure. Worth
reconciling and stating authoritatively somewhere in your repo.

---

## 2. What MACCRE needs from you

Four things, in order of how much they block MACCRE work.

**2.1 An append-only import/update event log.** This is the one hard schema ask. See
§5.1. Everything else on this list is either already done or is a MACCRE-side
obligation.

**2.2 Per-turn change detection.** So re-importing an extended conversation adds only
the new turns. See §5.2.

**2.3 A place for provenance and trust to live.** MACCRE has adopted a system-wide
provenance doctrine and a trust model; your records are the first external data it will
apply to. See §4.2, §4.3 and §5.3.

**2.4 A jointly-authored read contract.** Not yet written, and **explicitly not yours to
write alone.** See §6.

---

## 3. What your schema already gets right — do not rebuild these

I am being specific because the most expensive thing you could do with this handover is
re-architect something that is already correct.

**`messages_fts` is exactly the right retrieval substrate.**

```sql
CREATE VIRTUAL TABLE messages_fts
    USING fts5(content, content=messages, content_rowid=id)
```

MACCRE's design of record for this corpus mandates **FTS5 + BM25, not embeddings** —
matching the existing `SovereignPinStore` pattern (`pins` + `pins_fts`) in
`maccre_core`. You independently arrived at the same substrate, and using external
content (`content=messages`) rather than duplicating text is the correct form of it.
**There is no embedding pass in the plan.** If you were considering adding one, don't —
see §4.1.

**`UNIQUE(platform, session_id)` is the stable identity the doctrine requires.** Keep
it. It is what makes idempotent re-import possible at conversation granularity.

**`source_mtime REAL` gives you file-level delta detection.** Correct as far as it goes;
§5.2 explains why it is not sufficient on its own.

**`models.py`'s three documented deviations are the right instinct.** Optional
`Message.timestamp` because real AI Studio chunks lack `createTime`; `Attachment` split
from `Artifact` because Drive references have no bytes to hash; `ConversationKind` so
Veo media-generation requests are classified rather than silently dropped. Recording
*why* a model diverges from its spec, with the forcing observation, is the same
discipline MACCRE has been enforcing — and it is the thing that survives a handover.
Keep doing it.

**`kind` and `notes` are quietly the most valuable fields you have.** `kind` prevents a
non-chat file being treated as a transcript. `notes` is a per-conversation channel for
non-fatal observations. MACCRE will want to surface `notes` to agents; see §5.3.

---

## 4. MACCRE-side decisions that constrain you

These are settled on the MACCRE side. They are recorded in
`B:\EXO_GANS\FeatureRequests.md` (33 entries) and mapped in
`.kiro_artifacts/2026-08-31_MACCRE_Long_Term_Evolution_Eisenhower_Planning_Map.md`.

### 4.1 Pinned, not embedded

The corpus will be reachable through a **pin-style FTS5 store, GLOBAL-scoped**, with no
vector embedding pass. Rationale: zero new dependencies, no embedding cost over 9,525
messages, no index to rebuild when a model changes, and retrieval you can *inspect* —
you can see why a row matched.

Accepted cost: no semantic reach. "roses" will not retrieve "floriculture". Mitigations,
in ascending order and **not to be started early**: FTS5 `NEAR`/prefix operators, a
query-time synonym layer, and only if genuinely necessary a hybrid where FTS5 provides
recall and `sqlite-vec` reranks. `sqlite-vec` is already a declared MACCRE dependency,
so the hybrid remains open — but lexical recall over one's own conversations is a
stronger baseline than it sounds, because the operator remembers their own phrasing.

**Chunk on turn boundaries, never fixed windows.** A question and its answer belong
together. Your `messages` table with `turn_index` already has the right granularity.

### 4.2 Isolation is structural, not a filter

This corpus must **not** be reachable from the same retrieval path as MACCRE's project
memory. It gets a **separate namespaced tool**, so an agent reaching into it is an
explicit act that appears in the ledger.

The reason is concrete rather than tidy: once external speculation from a year-old chat
is sitting in a ledger beside MACCRE's own findings, nothing downstream can tell them
apart. A filter on a shared query will eventually be bypassed by accident. A separate
tool cannot be.

**Corollary that will affect you:** when information is promoted from your store into
project memory, **provenance travels with it.** The single operation that crosses the
boundary is the one that can undo the isolation.

### 4.3 Trust is a ceiling inherited from provenance, with full chain of custody

The governing rule, and the one most likely to affect your schema design:

> An output's trust is bounded **above** by the **minimum** trust of its inputs. Trust
> is never a label applied by the last handler.

Without it, a low-trust source summarised by a high-trust agent inherits the agent's
trust — automatically, silently, on every summarisation.

Trust is modelled as **append-only event-sourced**: an intrinsic base trust per source
that is *never mutated*, plus contextual modifiers appended by reconciliation and
corroboration events. Effective trust is computed at read time. This exists so "why is
this trusted" is answerable during an audit, which an overwritten score cannot be.

A MACCRE agent called **CrumbRunner** will own scoring and reconciliation. Your corpus
is its first and safest source: bounded, offline, already cleaned, known origin.
**You are not being asked to implement trust scoring** — you are being asked not to make
it impossible (§5.3).

### 4.4 Four MACCRE-side caveats you must design around

These are MACCRE's defects and gaps, not yours. Do not build assumptions on top of them.

**(a) A session marked `completed` is NOT proof that every step ran.** `FlowRunner`
breaks its step loop on `cancelled` and `stalled` but **not** on `timeout` — a timed-out
step lets the flow continue and the session is still recorded `completed`. The decision
to change this is open with the operator. **Until it is settled, do not enumerate MACCRE
sessions by `completed` and treat them as whole.**

**(b) `failed` now also means "stalled".** Phase 6.13 Task A5 added a terminal condition:
a session is recorded `failed` when a step stalled — tasks left `locked` with no worker
alive. A stalled session's artifacts are **incomplete by definition**: at least one node
was claimed and never ran. Importing one as if whole would propagate a hole.

**(c) MACCRE sessions currently have no names.** Two Session Manager defects are open
and *unreproduced*: the "Name Session" input does not accept entry, and the "Name
MacroNode" modal has no Save or Cancel. So MACCRE-side sessions are addressable only as
`job_20260831-041428-6goe`. If your File Cabinet surface assumes human-readable session
names, that assumption is currently false.

**(d) Whether a MacroNode save/reload round trip is identity-preserving is unknown.**
`resolve_primitive_node_id` maps authoring aliases onto implementing primitives, so a
saved MacroNode may not reproduce the flow that was run. Relevant if you ever import or
export flow structure rather than conversations.

---

## 5. The concrete schema asks

Four. The first is the only one that blocks MACCRE work today.

### 5.1 An append-only import/update event log — **the one hard ask**

**What exists:** `import_stats.last_import` and `last_error`, one row per platform —
a *latest value*, not a history. Plus `conversations.import_timestamp`, which I read as
first-import time. *(Assumption: I did not verify whether it is rewritten on re-import.
If it is, that is itself a problem — see §7 Principle 2.)*

**Why it is insufficient.** A count of rows or files cannot distinguish "imported 40
conversations this month" from "imported 439 last year". MACCRE needs
**sessions-this-period**, which requires an event per import or update with its own
timestamp.

**Suggested shape** — yours to design, this is the minimum information:

```sql
CREATE TABLE import_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,               -- nullable: a failed import has no row yet
    platform        TEXT NOT NULL,
    event_type      TEXT NOT NULL,         -- imported | updated | skipped | failed
    turns_added     INTEGER NOT NULL DEFAULT 0,
    occurred_at     TEXT NOT NULL,
    detail          TEXT
);
```

**Append-only. Never updated, never pruned.** It is a history; a compacted history
answers no questions.

**What MACCRE uses it for.** The operator's migration metric: what fraction of AI usage
now runs on MACCRE rather than AI Studio, measured as *sessions this period* on each
side. MACCRE's side is already countable — Chat Studio sessions are identifiable because
`swarm_worker` branches on `job_id.startswith("studio_session_")`. Yours is not.

Note the metric must compare **per-period**, not cumulative. With a 439-conversation
head start, cumulative totals favour AI Studio essentially forever and the measurement
would never become meaningful.

*(Context you may not have: this began as a whimsical "throw a party when MACCRE
overtakes AI Studio" feature. The planning map recommended dropping the celebration and
keeping the ratio, on the grounds that it is the clearest available measure of whether
MACCRE achieved its purpose. **The event log is the KPI's foundation, not the party's.**)*

### 5.2 Per-turn change detection

**What exists:** `source_mtime REAL` on `conversations` — file-level detection.

**Why it is insufficient.** AI Studio conversations get *extended* — the operator
continues an old chat. On re-import, `source_mtime` correctly says "this file changed"
but not *which turns are new*. Without turn-level detection you either re-insert
everything (duplicating 9,525 messages and destroying FTS5 retrieval quality) or
re-detect by content comparison at import time.

**Suggested:** a `content_hash TEXT` on `messages`, SHA-256 of the turn's content, with
an index. `models.py` already computes SHA-256 for `Artifact.from_content`, so the
pattern is in place. Turn identity then becomes
`(conversation_id, turn_index, content_hash)`, which makes re-import idempotent and
makes "3 turns added" reportable into §5.1's `turns_added`.

**Watch for an edge case:** if a turn is *edited* rather than appended, `turn_index`
stays and `content_hash` changes. Decide deliberately whether that is an update or a new
turn, and write the decision down. MACCRE's provenance doctrine needs it to be
distinguishable either way, because a citation to a turn that has since changed is a
citation to something that no longer exists.

### 5.3 Somewhere for provenance and trust to live

**What exists:** nothing. No trust column, no external-source marker.

**Do not implement scoring.** CrumbRunner owns that. What MACCRE needs is that scoring
is *possible later* without a migration that rewrites history:

- **An external-source marker that survives retrieval.** Every chunk MACCRE retrieves
  must carry, at minimum: platform, `session_id`, conversation title, turn timestamp
  where available, and an explicit marker that this is *an external conversation the
  operator had* — not MACCRE's own established work. Your `platform` column supplies
  most of this; what matters is that it reaches the agent, not just the database.
- **`notes` should be exposed, not just stored.** Your parser records non-fatal
  observations there. A note saying a conversation was partially parsed is exactly the
  kind of thing that should attenuate trust, and it is invisible if it stays in the row.
- **Base trust, if you add it, must be append-only.** Never `UPDATE trust_score`. An
  events table (`trust_events`) with base plus modifiers, computed at read time.

**One thing worth flagging as a genuine hazard:** `is_thought` messages. Model thinking
is speculative *by construction* — reasoning-in-progress, frequently self-corrected two
turns later. If those are retrievable at the same trust as final answers, MACCRE agents
will cite abandoned reasoning as conclusions. **My recommendation: exclude
`is_thought=1` from the FTS5 index by default**, or floor its trust distinctly. That is a
decision for the operator, but it should be a *decision* rather than a default.

### 5.4 Two smaller items

**Reconcile the two schema-version mechanisms.** You have a `schema_info` table (1 row)
and `PRAGMA user_version = 0`. Two mechanisms, one unused. MACCRE has been bitten
repeatedly this phase by one thing having two representations — the TUI builds node ids
as `_{i}` while the engine builds `_S{i}`, and they have already begun to drift. Pick
one and delete the other.

**`journal_mode = wal` will become a problem, but not yet.** A WAL database is three
files (`.db`, `.db-wal`, `.db-shm`) that must be mutually consistent, and a file-sync
client uploads them independently with independent timing. MACCRE is heading for a
serverless single-writer deployment over synced storage (Android client, personal
cloud), and **single-writer discipline does not fix this** — sync is not atomic across a
file set. Applicable rule when you get there: **checkpoint, never unlink.**
`PRAGMA wal_checkpoint(TRUNCATE)` on clean shutdown is lossless; deleting a `-wal` can
destroy committed transactions. Or set `journal_mode=DELETE` where there is no
concurrency to optimise. Not urgent for you today — flagged so it is not a surprise.

---

## 6. The read contract — do not write this alone

Three MACCRE consumers independently need the same thing: session identity, artifact
addressing, lifecycle states, and which fields are guaranteed versus best-effort. They
are the Sovereign Importer integration, a possible spatial-interface project
("Omniscience"), and the migration KPI. MACCRE's planning map is explicit that if these
are built independently they produce **three divergent read paths against one
datacenter**.

**Consequence for you:** MACCRE owes you a published contract, and it is Epoch 3 work on
the MACCRE side — gated behind reproducing the two Session Manager defects. The
prerequisite chain is:

```
Name Session defect -> Name MacroNode defect -> Session Manager Dashboard
  -> File Cabinet read API  <-- what you need
    -> corpus as a GLOBAL KnowledgeStore
      -> CrumbRunner
```

**What you can do now without it.** The planning map identified that part (a) of that
work — read-only research into what the Session Manager actually reads and writes, and
which on-disk paths are contractual versus incidental — **is not blocked by anything.**
If you want to accelerate the boundary, doing that research from your side and publishing
what *you* need would be genuinely useful input rather than duplicated effort.

**What you should not do.** Do not infer the contract from MACCRE's current on-disk
layout and build against it. `03_Agent_Ledgers/<job_id>/` and
`04_Code_Artifacts/<job_id>/` exist, and some of that structure is incidental rather
than contractual. Building against incidental structure is how a boundary becomes
impossible to change.

I note your `__DATACENTER` already mirrors MACCRE's 5-tier layout and `handover.md`
describes a bidirectional link with `[SI] conversation_import.md` appearing in MACCRE's
File Cabinet payload list. **That is a good design and I am not asking you to change
it** — I am flagging that MACCRE has not yet ratified it as a contract, so treat the
coupling as provisional.

---

## 7. Principles from MACCRE's last phase that transfer directly

These were earned expensively — a rollback, three live debugging rounds, and real money
spent on inference that should never have run. They apply to you because you are doing
cross-boundary data movement, which is precisely where they bite.

**1. An approximately-correct identifier is worse than an absent one.** A wrong non-empty
value propagates and downstream logic *acts on it*; an empty value degrades visibly.
Incidents: a blanked tether id put a scatter and its merge in different scopes, so a
gather gate could never open and an 8-lane run deadlocked — an empty tether would merely
have degraded. Three PIDs in a stale registry had become an editor terminal, a font cache
service and a Logitech service; killing on PID alone would have terminated the
operator's own shell. **For you:** a `session_id` that is *plausible but wrong* is worse
than a missing one, and a provenance tag that is *approximately right* is worse than no
tag.

**2. Never report success over unperformed work.** Incidents: a drain check counted only
`open` rows, so a stranded task returned `drained=True` and the step reported
`completed`. `omni clean` logged "Project directory sterilized" while removing nothing.
`CTRL_MERGE` reported `Merged 8 sources` — literally true, and all eight paths were the
same file. **For you:** an import that reports "439 conversations" should mean 439
*distinct* conversations with *content*, and `skipped` deserves its own event type rather
than being folded into success.

**3. Two representations of one thing will drift.** Incident: the TUI and the engine
build node ids differently and have already diverged. **For you:** `schema_info` versus
`user_version` (§5.4), and any place the Markdown rendering and the database rows could
disagree about the same conversation. `to_markdown()` being derived from the model rather
than written separately is the correct shape — keep it that way.

**4. Verified means reproduced. A user report is a lead.** Three consecutive MACCRE
defects this phase had plausible-but-wrong first hypotheses; each fix revealed the next
rather than confirming the guess. **For you:** if MACCRE reports that something in your
output is malformed, reproduce it before designing the fix.

**5. A green test suite is not evidence of a working system when defects live in the
seams.** MACCRE's suite was green at 546, 617, 625, 636 and 665 tests while six real
defects sat in one code path, because they lived between the authoring UI and the engine
— territory no stubbed test visits. **For you:** the MACCRE boundary *is* that kind of
seam. It needs a scripted by-hand walkthrough recorded with its failure modes, not just
unit tests over your parsers.

**6. Atomicity is a property of an artifact set, not a file.** See §5.4 on WAL.

---

## 8. Open questions for the operator, not for you to decide

Flagging these so you do not resolve them by implementation default:

1. **Should `is_thought` messages be retrievable at all?** (§5.3) I recommend excluding
   them from the index by default.
2. **Is 439 the authoritative corpus count?** The operator says ~490, `models.py` says
   451 files, the DB says 439. The KPI baseline needs one number.
3. **Is an edited turn an update or a new turn?** (§5.2)
4. **Does the ingested corpus become read-only once MACCRE consumes it,** or does
   re-import keep rewriting rows MACCRE has already cited? A citation to a mutable row is
   not a citation.
5. **What happens to `kiro` and `antigravity` platform imports?** Your schema supports
   all three, and `import_stats` has 3 rows, but only `aistudio` has conversations. MACCRE
   has planned only for the AI Studio corpus; if the others are coming, they need
   their own provenance treatment — Kiro conversations in particular are *about* MACCRE,
   which makes their trust story different from an external chat.

---

## 9. Reference

MACCRE-side documents worth reading if you need context beyond this handover. All are
in `B:\EXO_GANS`:

| Path | Contains |
|---|---|
| `FeatureRequests.md` | 33-entry register. The relevant entries are *AI Studio KnowledgeStore — pinned, not embedded*, *AI Studio conversation corpus as a global semantic KnowledgeStore*, *System-wide provenance doctrine*, *CrumbRunner*, and *Session Manager / File Cabinet alignment for Sovereign Importer* |
| `.kiro_artifacts/2026-08-31_MACCRE_Long_Term_Evolution_Eisenhower_Planning_Map.md` | Sequencing, dependency chains, epochs. §3.1 Chain A is the chain you sit in |
| `.kiro_artifacts/2026-08-31_phase_4_99_user_testing_handover.md` | Current MACCRE state, open defects, decisions owed |
| `maccre_core/.../sovereign_store.py` | `SovereignPinStore` — the FTS5 + BM25 pattern the KnowledgeStore follows. Worth reading; you built the same shape independently |

**Status of the MACCRE side as of this handover:** Track A (lock lifecycle) and Track D
(scatter wiring) complete and gated — `omni qa` clean across 117 files, 665 tests
passing, `omni smoke` green. Two payload-lineage defects open and diagnosed. The
File Cabinet read API you need is Epoch 3 and has not started.

Corrections to anything I have assumed about your side are welcome and should be
considered authoritative over this document.


---

# 11. REVISION 2 — the sovereignty model, and three corrections

**Added 2026-08-31**, after the MACCRE operator corrected the architecture. This section
supersedes §§1, 4.2, 5.3 and 6 wherever they conflict.

---

## 11.1 What each project actually is

**Sovereign Importer is not an importer.** It is a **local sovereign knowledge center** —
"Google Drive for your own computer, with a twist" — and the first stage of a local
source of truth built on **user-involved provenance over personal data.** Its contents
are open-ended by design: family photographs, daily KPI reports out of Power BI, complex
scientific research, mathematical studies, and everything between.

**MACCRE is one gated consumer of a controlled export from it.** Not its owner, not its
peer in authority over the KnowledgeStore.

The 439 AI Studio conversations in `conversations.db` are **content type one, not the
mission.** Rev 1 read the corpus as the project, which is what produced the inverted
boundary throughout §§1–6.

## 11.2 The sovereignty model — bidirectional

### (a) You are MACCRE's only window on the outside

> **Sovereign Importer is the deterministic firewall and knowledge gate for MACCRE. It is
> the ONLY location outside the MACCRE datacenter that MACCRE can reach.**

Everything external enters MACCRE through you or it does not enter.

### (b) Nothing crosses without its provenance

Content may only land in a linked MACCRE datacenter when **pushed from Sovereign
Importer, accompanied by its ingestion provenance artifacts.** The operator's stated
ambition is OS-level enforcement on Windows — not a convention both sides agree to
honour.

**Design consequence:** the push is a single atomic unit — *content + provenance
together* — and should not be expressible any other way. An API that permits pushing
content without provenance will eventually be used that way, and the firewall becomes
advisory.

### (c) The off-limits tag must be iron-clad

Anything ingested may be tagged **off-limits to MACCRE**. Not a hint, not a flag MACCRE
is trusted to respect — a hard gate enforced on your side.

This generalises a lesson MACCRE learned expensively: a filter on a shared path is
eventually bypassed by accident; a structural boundary cannot be. If off-limits content
is reachable by the same call that reaches permitted content and differs only by a flag,
that flag will one day be wrong.

### (d) MACCRE is sovereign from you, symmetrically

The half rev 1 missed entirely, and what makes this a *trust contract* rather than a
hierarchy:

> **MACCRE must be able to silo data from being withdrawn by, exported to, or even seen
> by Sovereign Importer.**

Neither party holds dominion. **Do not design any capability that assumes unrestricted
read access to a linked MACCRE datacenter.** Enumeration is a privilege MACCRE grants and
can withhold per item. This is currently unimplemented on MACCRE's side — see §11.6.

### (e) The acknowledged asymmetry

The operator's own framing, recorded because it is a reasoned position rather than an
oversight:

> Gating MACCRE behind Sovereign Importer is, in practice, censorship. Given that we are
> dealing with probabilistic intelligence it is warranted, and is therefore an
> acknowledged hypocrisy: an accepted violation of principle arising from realist
> preparation for a probabilistic concern.

Do not attempt to resolve this in code. It does imply the gate should be **auditable** —
the operator should always be able to see what was withheld from MACCRE and why. An
unreviewable censor is a different thing from an acknowledged one.

### (f) The two datacenters are mirrored in STRUCTURE ONLY

Both use the 5-tier layout. **This is a shared convention — not a data coupling, not a
shared filesystem, not a sync relationship.** Rev 1 called it a "bidirectional link" of
data based on `handover.md` wording. That was a misreading. A MACCRE datacenter is
*linked* only in the sense that the operator has authorised a push channel to it.

## 11.3 The import flow, as designed

1. **Ingest into Sovereign Importer** — by copy-in *or* by link (§11.4). Fingerprinted,
   daemon-monitored, memory-pinned with ingestion telemetry and accompanying sources.
2. **Link a MACCRE datacenter** — a one-time authorisation establishing a push channel.
3. **Select scope inside Sovereign Importer** — the operator browses the KnowledgeStore
   and selects sections, or all of it.
4. **Push into MACCRE's `01_Raw_Source` for the active project**, as payload / raw
   source, **with provenance artifacts accompanying it**.
5. **Or provision a new MACCRE project first**, triggered from within Sovereign Importer
   via MACCRE's CLI (§11.5). This is why the CLI control surface exists.

Direction of travel throughout: **you push, MACCRE receives.** MACCRE never reaches into
you.

## 11.4 Fingerprinting and telemetry are the first chain-of-custody gate

Rev 1 §5.3 asked you to add "somewhere for provenance to live", as though provenance were
a missing column. **It is your core function.**

> **Fingerprinting and daemon-level telemetry tracking of all Sovereign KnowledgeStore
> contents is the first step in provenance, and the first local chain-of-custody gate in
> the trust-building process.**

### (a) Link-not-copy is a first-class mode

Files and folders elsewhere in the filesystem can be **shared/linked in** without being
copied: links organised, targets fingerprinted, daemon monitored, memory-pinned. Tracked,
not copied. MACCRE-relevant consequences:

- **A linked item can change or vanish after MACCRE cites it.** The fingerprint at
  ingestion is what makes a citation meaningful; the daemon is what detects drift. A
  citation needs the **fingerprint as of push**, not just a path.
- **A push must resolve the link.** MACCRE cannot follow a path outside its own
  datacenter (§11.2a), so pushing a linked item transfers content plus fingerprint, never
  a pointer.
- **Fingerprint drift is a trust event, not an error.** If the daemon sees a linked target
  change after a push, that should attenuate trust on anything derived from it.

### (b) Sources are verified, fetched, and stored as artifacts

Accompanying sources are first-class and *actively validated*:

- **Citations** supplied by the operator.
- **Web links** whose first-hand existence is *preliminarily and contextually verified*,
  then **downloaded, fingerprinted, compressed, and deposited in the datacenter as an
  artifact** stored alongside the item it supports.
- **Pre-existing provenance artifacts** originating outside either system.
- **Any other supporting accoutrement** the operator wishes filed.

Worth stating plainly: **a fetched, fingerprinted, locally-stored copy of a cited source
is a qualitatively better provenance record than a URL.** URLs rot; a fingerprinted
artifact does not.

### (c) This completes MACCRE's trust model

MACCRE's trust model (rev 1 §4.3, still correct) has an **intrinsic base trust** per
source that is never mutated. Rev 1 had no answer for where base trust *comes from* — it
was an unsourced axiom.

**It comes from here.** Base trust originates at your fingerprint-and-telemetry gate:
what the item is, where it came from, what sources accompany it, whether its fingerprint
has held.

**Implication:** MACCRE needs enough of that record to reconstruct *why* base trust is
what it is. A bare score is not usable; a score plus its custody chain is.

## 11.5 MACCRE's CLI provisioning — verified, and rev 1's warning was wrong

You trigger MACCRE project provisioning from inside Sovereign Importer. I verified this
path because the operator flagged uncertainty.

**It exists and it is the right call:**

```
maccre new <project_name>
    "Provision a new project silo with 5-tier DATACENTER and fresh databases"
    -> maccre.py:786 -> initialize_workspace()      [admin_tools.py:255]

maccre ingest <project>
    "Hash-aware bulk ingest of 01_Raw_Source for a project"
```

**`maccre ingest` being hash-aware deserves your attention** — it likely aligns with your
fingerprinting rather than duplicating it. Read it before building a parallel mechanism.

Other subcommands: `sessions`, `global`, `launch`, `run`, `audit`, `status`, `canonize`,
`brief`, `pattern`, `mcp`, `smoke`.

### Correction — ignore any claim that the TUI's provisioning is broken

An earlier draft of this handover concluded that the TUI's "New Project" was incomplete
because it calls `set_active_project()` rather than `initialize_workspace()`. **That
conclusion was wrong**, and the operator's contrary evidence (the TUI has worked all
along) was correct. What actually holds:

- `sheet_parser.py`'s own docstring: *"It replaces `agent_roster.csv`, `topology.csv`, and
  `project_schema.json` with a single portable workbook."* The architecture deliberately
  moved to `MACCRE_Swarm_Request.xlsx`.
- **`initialize_workspace` still bootstraps the three replaced files.** It is *behind* the
  architecture, not the standard the TUI fails to meet.
- Directory tiers are created lazily by callers; `ensure_project_workbook()` runs before
  every swarm run and self-heals the workbook plus telemetry silos. That is why the TUI
  path works.
- Empirically: of twelve projects in MACCRE's datacenter, **none** has
  `project_schema.json` or `agent_roster.csv`, and the working project `499_TEST` has all
  five tiers and a workbook.

**Net effect for you: `maccre new` is safe and correct to call.** It will additionally
create two legacy files and a dead `chroma_db/` directory (chromadb was excised on
2026-04-25 in favour of `SovereignPinStore`). Harmless. Being aligned on the MACCRE side,
gently.

## 11.6 What MACCRE cannot yet honour — MACCRE's gaps, not yours

Do not design against capabilities that do not exist.

**(a) MACCRE has no mechanism to silo data from you** (§11.2d). No per-item export
restriction, no concept of "not visible to Sovereign Importer". Symmetric sovereignty is
aspirational on MACCRE's side today.

**(b) MACCRE has no mechanism to honour the off-limits tag** (§11.2c). Enforcement is
entirely yours. Arguably correct — a gate enforced by the party being gated is not a gate
— but it means the tag's integrity rests wholly on your implementation.

**(c) MACCRE cannot enforce provenance-accompanied-only writes** (§11.2b). Nothing
prevents content appearing in a MACCRE datacenter by other means. Unimplemented on both
sides.

**(d) MACCRE's cross-project memory is deliberately shunted and off by default.**
*(Corrected 2026-08-31 — an earlier draft called this a "dead feature". It is not. It was
wired with a breaker and left open **on purpose**, because cross-project memory was
pushing the boundaries of provenance capability at the time and enabling it would have
derailed that stage of the strangler fig. Dead code should be removed; an intentionally
open breaker should be documented and closed on a schedule.)*

Verified: `_verify_synaptic_bridge()` in `rag_tools.py` reads
`get_datacenter_path("project_schema.json")` and returns `False` when absent. That file
exists nowhere under `__DATACENTER`, so `query_foreign_memory()` always denies. **It fails
closed, which is the breaker working as designed.**

**What this means for you:** do not assume MACCRE can federate across its own projects on
your behalf, and do not design a capability that depends on it. Re-enablement is gated on
provenance work that overlaps directly with §11.4 — full telemetric coverage of
concurrent flows, and provenance nailed down from ingestion through to the point an agent
sees it, **in Sovereign Importer and its File Cabinet bridge.** Your fingerprint-and-
telemetry gate is on the critical path to MACCRE turning this back on.

Two fragilities recorded in MACCRE's register, relevant because they touch the boundary
you enforce: "off" is currently implicit (a missing file) rather than an explicit setting,
and `link_projects` — which creates that file and whitelists a project — is registered in
MACCRE's agent tool dispatcher. Both are being hardened. Neither is yours to fix.

**(e) MACCRE has no published read contract.** Session identity, artifact addressing,
lifecycle states, guaranteed-versus-best-effort fields — none ratified. Epoch 3 work,
gated behind reproducing two Session Manager defects:

```
Name Session defect -> Name MacroNode defect -> Session Manager Dashboard
  -> File Cabinet read API  <-- the contract
    -> corpus as a GLOBAL KnowledgeStore -> CrumbRunner
```

**What you can do now:** the read-only *research* half of that work is blocked by nothing.
Publishing what *you* need from the boundary would be useful input rather than duplicated
effort.

**What not to do:** do not infer the contract from MACCRE's current on-disk layout. Some
of that structure is incidental rather than contractual, and building against incidental
structure is how a boundary becomes impossible to change.

## 11.7 One more thing about MACCRE's datacenter you should know

`__DATACENTER/GLOBAL/` is **not a project.** It is the namespace for global-scope
resources only: `agent_library.db`, `macronode_registry.db`, `controlnode_registry.db`,
`agent_roster.csv`, global telemetry, memory pins, `nexus_sessions/`, `autosave_flow.json`.

It *used* to be run as a project, and the residue is still visible — `swarm_queue.db`
(2026-06-09), `03_Agent_Ledgers/`, `04_Code_Artifacts/`, a workbook, a nested
`GLOBAL/GLOBAL/`, and a `GLOBAL/UNNAMED/`. Project-scoped `agent_roster.csv` moved to
GLOBAL on **2026-08-09**, which dates the transition.

**If you enumerate a linked MACCRE datacenter, do not treat `GLOBAL` as a project**, and
do not treat everything inside it as current. Also note `thought_pins.db` is deprecated
and being removed; do not build against it.

## 11.8 Revised ask list

Superseding rev 1 §5. Two of its four asks were reframed by §11.4 into "what to transmit"
rather than "what to store".

**(1) An append-only ingest/custody event log — the one hard schema ask.** Rev 1 §5.1
holds, with these changes: it is not conversation-specific, so add an `item_kind`
(`conversation | file | folder_share | source_artifact`), and add two custody event types
— `fingerprint_drift` and `pushed_to_maccre`. **The push into MACCRE is itself a
chain-of-custody link and belongs in your history, not only MACCRE's.** Append-only;
never updated, never pruned.

**(2) Change detection below file granularity.** Rev 1 §5.2 holds unchanged
(`content_hash` per turn; and the same question needs answering for linked files, where
ingest-time hash plus daemon-observed drift is the same mechanism).

**(3) What a push must carry** — replaces rev 1 §5.3. Enough for MACCRE to answer "where
did this come from and how much do I trust it" **without calling back to you**, because
§11.2d means it may not be able to:

- stable item identity on your side, plus `item_kind`
- **fingerprint as of push**
- ingestion telemetry: when, by what route, copy or link
- **accompanying sources as artifacts** — the fetched, fingerprinted, compressed copies
  from §11.4b, not URLs
- any pre-existing external provenance artifacts
- base trust **with the custody chain that justifies it** (§11.4c)
- your `notes` field — transmitted, not merely stored. A note saying an item parsed
  partially is exactly what should attenuate trust downstream, and it is invisible if it
  stays in the row.

**(4) The two smaller items** — rev 1 §5.4 holds unchanged: reconcile `schema_info`
against `PRAGMA user_version`, and remember **checkpoint, never unlink** for WAL when the
synced-storage work arrives.

---

*Rev 1 sections §§9 (what your schema already gets right) and §10 (transferable
principles) are unaffected by this revision and remain the most immediately useful parts
of the document.*
