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
