# MACCRE — Attributions and Convergences

**What this document is.** A record of every idea in MACCRE's doctrine or architecture that
turned out to have an established name in the literature, together with **the specific incident
that produced it here** and an explicit statement that MACCRE claims no novelty for it.

**Why it exists.** MACCRE's architecture was substantially derived from first principles, in
response to concrete failures in a running system, by an operator who had read almost nothing
about the field until 2026. That produced a run of independent derivations. It also produced a
blind spot: *no habit of checking whether a derived idea already had a name.* That blind spot has
now cost three withdrawn claims.

**The distinction this document exists to hold.** Deriving an idea independently and inventing it
are different acts with different evidential value:

- **Independent derivation is evidence about the reasoning.** Arriving at Biba's 1977 integrity
  model from a merge bug, without having read Biba, says something real about whether the
  reasoning was sound.
- **Invention is a claim about priority.** MACCRE makes no such claim anywhere in this document,
  and priority would be unprovable from a private repository regardless.

**The standard applied.** Each entry below was searched adversarially — the goal was to *find*
prior art, not to confirm its absence. Where nothing was found, the entry says **searched, not
found**, which is a statement about the search and not about the world. That phrasing is
deliberate: the failure that produced this document was a true statement about where someone had
looked being read as a statement about what existed.

---

## The convergences

### 1. Trust is bounded above by the minimum trust of its inputs

**Established name:** the **Biba integrity model** with a **low-water-mark** policy (Kenneth
Biba, MITRE, 1977) — the integrity dual of Bell–LaPadula. The dynamic-demotion variant ships in
FreeBSD as `mac_lomac`, where a subject reading lower-integrity data has its own integrity level
decreased. In a different vocabulary it is also **taint propagation**.

**Also, and more directly:** IETF Internet-Draft `draft-bondar-wca-00` (March 2026) states it as a
formal, model-checked security property — `W(final) = min_i(W_institutional(source_i))` for
multi-hop chains, and `W(p) <= W_institutional(source(p))` for any single hop.

**The incident here:** a `CTRL_MERGE` node reported `Merged 8 sources` — literally true, and all
eight paths were the same file. Low-trust material acquiring a trusted label by passing through a
summarising step, with nothing preventing it.

**Claim:** none. Independently derived; formalised 49 years earlier and specified formally in the
same year MACCRE derived it.

### 2. The threat model: a probabilistic transformation launders its source's trust

**Established name:** **semantic laundering** — Romanchuk & Bondar, *Semantic Laundering in AI
Agent Architectures: Why Tool Boundaries Do Not Confer Epistemic Warrant*, arXiv 2601.08333,
January 2026. The same authors' *Warrant Erosion Principle* formalises the corollary: an
interpretive process can only lose observations and inference rules, never gain them.

Related and independent: **memory provenance laundering** / **source-authority non-amplification**
(arXiv 2607.29167, July 2026), and **authority collapse** (arXiv 2608.01679), which measures the
phenomenon at 48 of 49 configurations tested. A systematic literature review of the surrounding
taxonomy exists (arXiv 2607.05031).

**The incident here:** the same merge defect as above, plus the recognition that the enterprise
data-lineage default runs the *opposite* way — trust inheriting downward to save documentation
effort — which is right for deterministic SQL and wrong for an LLM.

**Claim:** none. MACCRE reached the threat model but not first, and the security literature had
already taken the restrictive side.

### 3. A derived artifact's provenance is the union of its inputs' plus the transformation

**Established name:** the **W3C PROV** data model — PROV-DM and PROV-O, W3C Recommendations since
2013 — which models entities, activities, agents and derivation relationships specifically so
provenance can be interchanged between systems. Note what PROV deliberately declines: it supplies
the derivation graph and leaves any trust arithmetic to the consumer.

**The incident here:** provenance evaporating at the first summarisation, so a merged document
carried no trace of the eight lane outputs that produced it.

**Claim:** none. This is the one convergence where re-deriving privately had a real cost —
interoperability — because the whole value of a provenance vocabulary is that other systems
already speak it. MACCRE now uses PROV's three words: **entity**, **activity**, **derivation**.

### 4. Deterministic control flow wrapping non-deterministic execution

**Established name:** the **durable execution** pattern. Temporal's workflow/activity split, where
workflow code must be deterministic because it is replayed from event history and model calls
belong in activities so they are not re-executed; Azure Durable Functions; Restate; and Obelisk,
which enforces the split through WASM. Mistral Studio's determinism model is the same idea.

**The incident here:** a recursion limiter inserted a node named `FAILED`, which was then claimed,
**ran real inference**, and fed its output to the next step. The `CTRL_` primitives exist so the
control layer cannot do that.

**Claim:** none — and this one is worth being precise about, because it is where MACCRE is
*mechanically weaker* than the established form. MACCRE's determinism is a convention about which
node types call a model. Temporal's is a property enforced by replay against an event history.
MACCRE has the split and not the history.

### 5. SQLite as the durable substrate for agent work

**Established name:** the position argued by **Obelisk** — whose post on SQLite sufficing for
durable workflows reached the front page of Hacker News in June 2026 — and by **DBOS**, whose
framing is that a trusted database removes the need for a separate orchestration tier.

**The incident here:** needing atomic single-ownership of a unit of work on one machine with no
server, after a shared connection was measured handing the same task to two workers (12 tasks
producing 15 claims).

**Claim:** none. Independently arrived at, and as of mid-2026 no longer distinguishing.

### 6. Human-in-the-loop pause with persisted state and resume

**Established name:** **LangGraph**'s `interrupt()` with a checkpointer, which pauses inside a node
with state persisted, enabling HITL, time-travel debugging and fault-tolerant resumption.

**The incident here:** needing an operator to inject context mid-flow without losing the run.

**Claim:** none. LangGraph's ergonomics are better; MACCRE's durability is better, because the work
lives in a queue rather than in a process. Both statements are comparisons, not claims of priority.

### 7. An append-only register where reversals are new records, never edits

**Established name:** **Architecture Decision Records**, introduced by Michael Nygard in 2011.
Microsoft's Azure Well-Architected Framework states the discipline in substance identically: the
record is an append-only log, accepted records are not edited, and a changed decision becomes a new
record superseding the original with the two linked. The standard status lifecycle is
Proposed / Accepted / Deprecated / Superseded.

**The incident here:** a rollback to an earlier baseline lost the *reasoning* behind prior work and
forced a full rebuild; and an audit finding correctly recorded three weeks early was rediscovered
the expensive way because nothing kept it in view.

**Claim:** none. MACCRE's register is an ADR log with a different status vocabulary
(`COMPLETED` / `WITHDRAWN` / `SUPERSEDED`) and feature-shaped rather than decision-shaped entries.

### 8. A terminal state requires evidence, not assertion

**Established name:** **assurance cases** / **safety cases**. Goal Structuring Notation (Kelly &
Weaver) composes evidence into a structured argument that goals are satisfied, so a goal is
discharged by evidence rather than by claiming it. **OMG SACM** goes further in exactly the
direction MACCRE cares about: its artifact metamodel interchanges packages of evidence that record
*how the evidence was collected*. ISO 14971 / IEC 62304 acceptance criteria formalise the same
discipline for medical device software.

**The incident here:** a drain check that counted only `open` rows, so a stranded task returned
`drained=True` and the step reported `completed`. A cache purge that logged "sterilized" while
removing nothing.

**Claim:** none, and here the established form is **stricter than MACCRE's**. A Completion Metric
requires that evidence be cited. SACM requires that the evidence carry its own provenance.

### 9. A hardware token that must remain present during a session

**Established name:** the pattern behind **FIDO2 / U2F**, YubiKey-backed GPG, and full-disk-encryption
key files.

**The incident here:** wanting credential access abstracted away from the system itself, behind a
physical object the operator holds.

**Claim:** none. What is mildly unusual is stamping the *authorisation result* into an NTFS
Alternate Data Stream so a directory listing does not reveal which topologies are approved — and
that is storage steganography rather than a new access-control idea, and it is the weakest part of
the design. See the register entry *Paranoia Mode — finish the hardware-token topology gate*.

---

## Searched, not found

Recorded separately because these are **statements about a search**, not findings. Each may well
have prior art that a better search would surface, and one of them is close to something that
argues against it.

| Idea | Search result |
|---|---|
| **Trust laundering through fan-in aggregation in a flow engine** — N artifacts of differing provenance merged into one document that carries none of their trust | Searched, not found. The literature covers agent *memory* and *tool-call boundaries*; fan-in aggregation is a different surface. A different *place*, not a different idea |
| **A short standing doctrine, injected into every working session, where each principle inlines the specific failure that produced it** | Searched, not found *as a named practice*. All the components exist — blameless postmortems, MISRA rationale, ADR `Context`. And JPL's *Power of 10* explicitly names the incident-derived-rule phenomenon, then deliberately writes ten rules that cite no incidents, because a short rule set gets followed. **A leading authority considered this and chose against it.** Weak negative evidence: process practices are systematically under-published |
| **Transitive trust over a bounded artifact set**, where SLSA declined transitivity for tractability at supply-chain scale but a session graph is bounded | Searched, not found — but WCA's composability property over multi-hop chains may subsume it entirely. Treated as probably-covered |

## Convergences noted but not yet searched

Listed so they are not mistaken for claims. Each needs the same treatment as the nine above
before it appears in anything public.

- **Governance tooling living outside the governed environment** (`omni` outside the repository).
  Resembles build-system independence and separation of duties.
- **A human gate the automated system cannot operate.** Resembles air-gap practice and
  separation of duties.
- **An approximately-correct identifier being worse than an absent one.** Resembles fail-safe
  defaults and the fail-fast principle.
- **Atomicity as a property of an artifact set rather than a file.** Resembles well-known
  guidance about SQLite WAL files and sync clients.

---

## What MACCRE does claim

Nothing in the list above. What the record supports is narrower and, in the operator's framing,
sufficient: **nine ideas derived from first principles as responses to real failures in a running
system, rather than read and implemented.** Independent derivation of nine things that turn out to
have established names is evidence that the reasoning was sound. It is not evidence of priority,
and this project does not assert any.

*Maintained under the Entry Doctrine's Third Amendment, which requires a prior-art line on any
register entry asserting a general principle. Convergences are added here when found, including
when found late.*
