# Adversarial Prior-Art Search: The Restrictive Trust Default

**Written:** 2026-09-04
**Nature:** Falsification attempt. Modifies no code.
**Task:** Era 3 plan Task 6 — *try to break* the claim that MACCRE's restrictive trust default
is unclaimed, rather than confirm it.
**Requested framing:** the operator's instruction was *"I dont want to publish a whole thing on
restrictive default capture if its not truly something worth publishing"* — so the search was
run to fail the claim if it could be failed.

> **Content compliance.** All external material is paraphrased and attributed inline. Quoted
> fragments are short and technical. Content was rephrased for compliance with licensing
> restrictions.

---

## Verdict, first

**The claim does not survive. It is comprehensively prior art, and the closest match is a formal
specification in an IETF Internet-Draft.**

The 2026-09-03 competitive analysis called this *"the one genuinely novel position here"* and
recorded that it *"could not find this addressed by any of: SLSA, in-toto, Sigstore, W3C PROV,
NIST AI RMF, the EU AI Act as amended, C2PA, OpenLineage, or OTel GenAI conventions."*

**That statement is true and it was misleading.** Every item on that list is a *standards body*.
The work is in the **agent-security research literature**, which the analysis did not search. Two
searches found it. This was a search-scope error producing a false negative on the single finding
the analysis was most confident about — which is worth recording as carefully as the finding
itself, because it is the second time in two days that a confident claim turned out to rest on an
unexamined premise.

---

## 1. The decisive match

**Bondar, R., *Auditable Data Provenance for AI-Agent Tool-Call Chains*, IETF
Internet-Draft `draft-bondar-wca-00`, March 2026**
([IETF](https://www.ietf.org/archive/id/draft-bondar-wca-00.html))

Its Appendix A states, as formal security properties of the Warrant Certificate Authority:

| WCA property | Statement | MACCRE's Doctrine 1 |
|---|---|---|
| A.1 — No channel-based semantic laundering | `W(p) <= W_institutional(source(p))` | *"An output's trust is bounded **above** by the … trust of its inputs"* |
| A.6 — Composability | `W(final) = min_i(W_institutional(source_i))` | *"bounded above by the **minimum** trust of its inputs"* |
| A.2 — Self-licensing prevention | agent-generated propositions get `W(p) = 0` | *"It is never a label applied by the last handler"* |

**A.6 is MACCRE's rule verbatim, in formal notation, machine-checked.** The draft records a TLA+
model verified with TLC, including a counterexample found in three transitions where an agent
generates content, writes it to a source, and queries it back with warrant above zero — which is
precisely the laundering loop MACCRE's rule exists to prevent.

The draft also formalises what MACCRE's corollary describes. Its **Warrant Erosion Principle**
(§3.1) holds that an interpretive process can only lose observations and inference rules, never
add them — the same direction of travel as *"provenance that evaporates at the first
summarisation is decorative"*, stated as a subset relation.

And it names the threat model: **semantic laundering**, defined as weakly-warranted data
acquiring unwarranted epistemic status by crossing a trusted tool-call boundary, which the draft
calls *channel-to-content trust conflation*.

The concept is credited to two earlier papers:

- Romanchuk, O. & Bondar, R., *Semantic Laundering in AI Agent Architectures: Why Tool
  Boundaries Do Not Confer Epistemic Warrant*, arXiv 2601.08333, **January 2026**
- Romanchuk, O. & Bondar, R., *The Responsibility Vacuum: Organizational Failure in Scaled
  Agent Systems*, arXiv 2601.15059, January 2026

## 2. And it is not an isolated match — it is an active subfield

Found in the same two searches:

| Work | Relevance |
|---|---|
| **Memory Provenance Laundering in LLM Agents: A Non-Amplification Firewall for Persistent Memory**, arXiv [2607.29167](https://arxiv.org/abs/2607.29167), Jul 2026, EMNLP submission | Names **source-authority non-amplification**. Describes an observation rewritten during memory consolidation so that the low-trust source which should limit its authority is erased. Implements **PPMF**, a provenance-preserving memory *firewall* |
| **Benchmarking Authority Collapse at the Memory Consolidation Boundary**, arXiv [2608.01679](https://arxiv.org/html/2608.01679) | Measures the phenomenon: authority collapse in **48 of 49** configurations across seven memory systems and seven backbones; ~50% unauthorized-action rate once authority metadata is lost |
| **Auditing Provenance Sensitivity in LLM Agent Action Selection**, arXiv [2607.20827](https://arxiv.org/html/2607.20827) | Finds models respond to *textual* source-authority cues without that preventing untrusted evidence from influencing actions — i.e. prompt-level trust labels do not enforce a ceiling |
| **Non-Malleable, Origin-Bound Authority with Machine-Checked Guarantees**, arXiv [2606.24322](https://arxiv.org/html/2606.24322) | Memory poisoning across sessions, with machine-checked authority binding |
| **The LLMbda Calculus: AI Agents, Conversations, and Information Flow**, arXiv [2602.20064](https://arxiv.org/pdf/2602.20064) | A lambda calculus making provenance-based defence expressible and provably sound |
| **Source-of-Authority Taxonomy — A Systematic Literature Review**, arXiv [2607.05031](https://arxiv.org/html/2607.05031v1) | **A systematic literature review exists.** A field with an SLR is not unclaimed territory |
| **PROV-AGENT: Unified Provenance for AI Agent Interactions**, arXiv 2508.02866, 2025 | Provenance model for agent interactions |
| **MAIF: Enforcing AI Trust and Provenance with an Artifact-Centric Paradigm**, arXiv 2511.15097, 2025 | Artifact-centric trust and provenance — closest in *shape* to MACCRE's ledger-artifact model |
| **CIV: Contextual Integrity Verification**, arXiv 2508.09288, 2025 | Per-source integrity in agent context |
| **RAG Sign: Cryptographic Authentication for RAG-Enabled LLMs**, Springer LNCS 15692, 2025 | Signing at the retrieval boundary |

Plus the older, pre-LLM lineage on the same question, which the analysis also missed:

- **Dai, Lin, Bertino et al.**, trust scores for data derived from provenance
  (Purdue CERIAS, [2008](https://www.cerias.purdue.edu/assets/pdf/bibtex_archive/2008-18-report.pdf)) —
  the classical framework for computing a datum's trustworthiness from its provenance and its
  sources' trustworthiness.
- **Jäger, M. & Küng, J.**, *New Concepts for Trust Propagation in Knowledge Processing Systems*
  ([CEUR Vol-2154](https://ceur-ws.org/Vol-2154/paper1.pdf)) — asks the question directly: given
  trust values for inputs, *what is the trust value of the output?*
- **PaTAS**, trust propagation through neural networks using subjective logic,
  arXiv [2511.20586](https://arxiv.org/html/2511.20586v3).
- **ClaimTrust**, PageRank-style trust propagation across RAG documents,
  arXiv [2503.10702](https://arxiv.org/html/2503.10702).

---

## 3. What survives, stated without flinching

**Of the trust model: nothing.** The threat model has at least three names in the literature
(*semantic laundering*, *memory provenance laundering*, *authority collapse*), the ceiling rule
is a formally specified and model-checked property, and the handler-cannot-raise-it rule is
*self-licensing prevention*. Publishing any of it as novel would be falsified by a single search
and would cost exactly what the analysis predicted: a reader with a security background stops
reading.

**Two things do survive, and neither is the trust model.**

1. **Independent derivation, again.** MACCRE reached this rule from a concrete incident — a merge
   reporting `Merged 8 sources` over one file eight times, and low-trust material acquiring a
   high-trust label by summarisation — without having read any of this work. That is the same
   category of finding as Biba/LOMAC and W3C PROV: **strong evidence the reasoning is sound, and
   zero evidence of novelty.** It is worth stating and it is not worth publishing as a
   contribution.
2. **The surface is different.** This literature is about *agent memory* and *tool-call
   boundaries*. MACCRE's instance is *derived artifacts inside a multi-agent orchestration flow* —
   a merge node consuming eight lane outputs and emitting one document. I found no paper on
   laundering through **fan-in aggregation in a flow engine**. That is a different *place*, not a
   different idea, which makes it a legitimate case study and not a claim.

**The permissive-default contrast still holds, and is now less interesting.** Google Cloud's
lineage work genuinely does argue for trust inheriting *downward* to save documentation effort
([Google Cloud](https://cloud.google.com/blog/products/data-analytics/governance-on-autopilot-automate-data-governance-with-lineage)).
So the observation that data-governance and agent-security defaults point in opposite directions
is real. But it is an observation about two communities, and the security community has already
and explicitly taken the restrictive side.

---

## 4. The finding that matters more than the negative result

**The Sovereign Importer's central control has a published argument against it.**

Romanchuk & Bondar's *Responsibility Vacuum* is summarised in the WCA draft as establishing that
human oversight shifts from genuine evaluation to ritualised approval once throughput is high
enough — and therefore that **content-evaluating mediators do not scale**. The draft builds its
whole architecture on that conclusion, with §3.3 arguing that any mediator which evaluates
*content* eventually becomes a new laundering channel itself, because its "approved" label
becomes the thing that confers unwarranted status.

**Sovereign Importer is a human gate that evaluates content.** The sovereignty contract makes it
the deterministic firewall and knowledge gate, with no agentic control, precisely so a human
decides what crosses. That is the design this paper argues degrades under load.

This is not fatal, and the reasons are worth stating precisely:

- MACCRE's throughput is one operator, which is the regime where the argument is weakest. The
  phase transition is a function of volume.
- The contract already concedes the gating is an acknowledged violation of principle that must
  stay auditable rather than silent.

But it is a real, citable objection to the strongest control in the design, and it should be in
the register rather than discovered by a reader. **WCA's answer — certify *sources*, not
*content*** — is also a concrete design option for the Importer seam that costs less human
attention than reading everything.

---

## 5. What this changes in the plan

| Plan item | Was | Now |
|---|---|---|
| Task 7 — expand the restrictive default into a defensible statement | Write it up as the one novel position | **Rewrite as a case study**, citing semantic laundering as prior art. No novelty claim |
| Task 8 — attributions log | Five convergences | **Six.** Add semantic laundering / source-authority non-amplification, and note the search-scope error that hid it |
| §3.5 of the analysis — "adopt PROV's vocabulary" | Right instinct | **Right instinct, wrong body of work.** The vocabulary to adopt is *warrant erosion*, *semantic laundering*, *source-authority non-amplification*, *self-licensing* — terms a reader in this field already knows |
| B7 — signing at the Importer seam | DSSE over content digests | **Reconsider against WCA.** It certifies sources rather than content, has a graduated adoption ladder (WAL-0…WAL-3, explicitly analogous to SLSA levels), and is on the IETF track |
| Epoch 4 / CrumbRunner | A private trust implementation | The formal property to implement is already written: `W(final) = min_i(W(source_i))`, with a TLA+ model and a counterexample to test against. **Cheaper to adopt than to invent** |

---

## 6. Confidence and limits

**Confirmed by direct reading of primary sources:** the WCA draft's Appendix A properties A.1,
A.2 and A.6; its Warrant Erosion formalism; its semantic-laundering definition; its citation of
the two January 2026 papers; the PPMF abstract's source-authority non-amplification framing.

**Confirmed by abstract only, not full text:** the remaining nine agent-provenance papers and the
four pre-LLM trust-propagation works. Their *relevance* is established; their exact formulations
are not, and one of them may state MACCRE's rule even more directly than WCA does.

**Not determined:**
- Whether any of this work states the **bounded-artifact-set tractability argument** — that
  transitive trust is computable at session scale even though SLSA declined it at supply-chain
  scale. WCA's A.6 composability over multi-hop chains is close and may subsume it. **This is the
  last unfalsified fragment and it is small.**
- Whether MACCRE's derivation predates January 2026. Probably not, and **it does not matter**:
  priority is unprovable from a private repository and the register's dates would be
  self-attested. Nothing should be built on it.
- Whether the *incident-named doctrine* practice and *terminal states requiring evidence* have
  prior art. Not searched here; they are process contributions rather than technical ones, and
  the earlier analysis called them the most transferable ideas in the project. **Worth their own
  search before any publication, on the same standard just applied to this claim.**

---

# Part 2 — The Other Two Candidates, Searched To The Same Standard

**Added:** 2026-09-04, same session.
**Why:** Part 1 killed the trust-ceiling claim, which promoted two other things to *leading
candidate for MACCRE's actual contribution*: the **incident-named doctrine** and **terminal
states requiring evidence**. Neither had ever been searched. Leaving them unexamined after
writing Part 1 would have been the same error twice.

## Verdict

**Both are prior art. All three candidates are now falsified.** One of the three is *more*
rigorously covered elsewhere than in MACCRE.

---

## 2.1 Append-only register, `SUPERSEDED`, never edited in place → Architecture Decision Records

This is the closest and least arguable match of the three, and it has been standard practice
since Michael Nygard introduced ADRs in 2011.

**Microsoft's Azure Well-Architected Framework**, on maintaining an ADR
([Microsoft](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)),
states the practice in substance identically to MACCRE's *Records are append-only*: the record is
an append-only log, accepted records are not edited, a changed decision becomes a **new** record
that supersedes the original with the two linked, and this preserves the history of the thinking.

A widely-used glossary description of ADRs
([Real Python](https://realpython.com/ref/software-engineering-glossary/architecture-decision-record/))
adds the status lifecycle — Proposed, Accepted, Deprecated, Superseded — and the rule that records
are never edited to flip a decision, a reversal being a new record while the old one remains as
the answer to why the earlier choice was ever made.

**Mapping, which is close to one-to-one:**

| MACCRE | ADR practice |
|---|---|
| Records are append-only, never deleted | Append-only log, accepted records not edited |
| `SUPERSEDED` (naming the replacement) | `Superseded`, with the two records linked |
| `WITHDRAWN` (requiring a rationale) | `Deprecated` / a superseding record carrying the reasoning |
| The Second Amendment's restatement pattern — an entry re-appearing in `COMPLETED` form rather than being edited | A reversal is a new numbered record; the old one stays |
| "A deleted entry takes its reasoning with it" | "the historical answer to *why did we ever do that?*" |

**MACCRE's register is an ADR log with a different status vocabulary and feature-shaped entries
rather than decision-shaped ones.** That is convergence, not invention. Recording it as
attribution #7.

**One genuine difference, and it is small:** MACCRE's `COMPLETED` requires a *Completion Metric* —
evidence — where ADR `Accepted` requires only a decision. But that specific idea is itself prior
art, immediately below.

## 2.2 Terminal states requiring evidence → assurance cases, and they are stricter

**Assurance cases / safety cases** are the mature form of "a claim is not accepted without
evidence", and the field has notation, metamodels and tooling.

- **Goal Structuring Notation (GSN)**, Kelly & Weaver — an assurance case is a structured argument
  composing pieces of evidence to show that system-level goals are satisfied
  ([GSN](https://www.researchgate.net/publication/228990118_The_goal_structuring_notation-a_safety_argument_notation)).
  A goal is not discharged by assertion; it is discharged by evidence, and the argument linking
  them is itself an artifact.
- **OMG SACM** (Structured Assurance Case Metamodel) goes further than MACCRE in the direction
  MACCRE cares about most: its artifact metamodel defines elements for interchanging packages of
  evidence that communicate **how the evidence was collected**
  ([OMG](https://issues.omg.org/secure/attachment/16783/new%201.4%20controlled%20vocabulary.pdf)).
  That is provenance *of the evidence for a claim* — a strictly stronger requirement than a
  Completion Metric line, and notably it is the same idea as MACCRE's provenance doctrine applied
  to its register rather than to its data.
- **Acceptance criteria** under ISO 14971 / IEC 62304 formalise the same discipline in medical
  device software.

**Verdict: prior art, standardised, and more rigorous than MACCRE's version.** MACCRE requires
that a completion claim carry observed evidence and a timestamp. SACM requires that the evidence
carry its own collection provenance. The gap runs the wrong way for a novelty claim.

## 2.3 Principles that name their originating incident → components all exist; the packaging is unnamed

This is the only one of the three where I did not find a direct match, and the honest reading is
that it is **weak negative evidence rather than a finding**.

**What exists:**

- **Blameless postmortem culture** (Google SRE) — an incident's record includes impact, root
  causes and the follow-up actions that prevent recurrence
  ([Google SRE](https://sre.google/sre-book/postmortem-culture/)). The incident is documented and
  it generates rules. The rules and the incident live in **separate artifacts** linked by action
  items, which is the difference from MACCRE — but a thin one.
- **MISRA C** attaches a rationale to each rule. Rationale explains *why*; it does not name a
  specific failure.
- **ADR `Context`** sections carry the situation that forced a decision, which is frequently an
  incident.
- **JPL's Power of 10** (Holzmann) is the sharpest comparison, and it cuts against MACCRE rather
  than for it. Holzmann observes that in existing rule sets, some rules reflect personal
  preference while others exist to prevent very specific and unlikely errors seen in earlier work
  at the same organisation
  ([JPL](http://www.cs.otago.ac.nz/cosc345/resources/NASA-10-rules.pdf)). He names the
  incident-derived-rule phenomenon explicitly — and then deliberately writes ten rules that do
  **not** cite incidents, on the grounds that a short rule set is followed and a long one is not.
  So the practice is not merely known; a leading authority considered it and chose against it.

**What I did not find:** a named practice of a *short standing doctrine, injected into every
working session, where each principle inlines the specific failure that produced it so the rule
can be argued with at the point of use.*

**Why that is not worth much.** Documentation and process practices are systematically
under-published relative to technical ones. Many teams almost certainly do this without giving it
a name, and absence of a name is not absence of the practice. Per the standard applied in Part 1,
this is recorded as **searched, not found** — and explicitly *not* as evidence of novelty.

---

## 2.4 So what is actually MACCRE's?

**Of the technical and process ideas: nothing that survives an adversarial search.** Three
candidates, three falsifications, one of them by a formally verified IETF draft and one by a
standard that is stricter than the MACCRE version.

**The remaining honest answer is not a contribution but a method**, and it is the operator's own
reframing rather than mine: the demonstrable thing here is *walking up to a false indicator of
significance and auditing the premise instead of banking it.* Three withdrawn novelty claims in
two days, each killed by the author's own search rather than by a reviewer, is a stronger and much
rarer artifact than one defensible claim would have been — because the failure mode it
demonstrates resistance to is the dominant failure mode of non-professional builders working with
AI assistance, which is motivated reasoning at scale.

**And it requires no novelty claim at all**, which is what makes it safe to publish. The Persona 2
dismissal risk — a reader with a security background stopping at the first falsifiable claim — was
never about MACCRE's engineering. It was about its claims. Removing the claims removes the risk.

**Consequence for the plan:** Task 2 ("expand the restrictive default into a defensible
statement") is now **superseded twice over**. What replaces it is a single essay whose subject is
the audit itself, with the three convergences as its evidence and the fan-in surface as a closing
technical note rather than a headline. The attributions log is no longer a defensive footnote; it
is the primary artifact.
