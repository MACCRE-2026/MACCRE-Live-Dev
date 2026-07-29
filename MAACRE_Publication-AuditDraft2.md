# GitHub Publication: Document Audit Report

The swarm has completed reading and analyzing the 36 historical files and 2 directories staged in `B:\EXO_GANS\History\`. Below is the synthesized strategy for how we will handle these files for publication.

> [!IMPORTANT]
> **User Approval Required**
> Please review the categorization and specific redaction targets below. Once you approve, I will execute the scrubs, merges, and scaffolding to prepare the final repository.

---

## 1. The Graveyard (DO NOT PUBLISH)
These files will be excluded entirely from the GitHub release to keep the repository professional and focused.
- `DETplanning.md` (Exact duplicate of `DETplanning-TUI Refactor.md`)
- `_archive/` (Entire directory: Contains legacy pre-reset environment backups, raw SQLite DB dumps, temporary session logs, and physics/TIGR test data payloads which distract from the core orchestration engine).

## 2. Redaction Targets (EDIT_TONE & EDIT_TEST_DATA)
These documents contain valuable history but require specific scrubbing before they can be merged or published.
- **`MACCRE_Operator_Manual.md`** 
  - *Action:* Scrub sensitive geopolitical example payloads (e.g., "Summarise the Iran situation") and replace with generic engineering payloads ("Summarize key operational findings").
- **`MajorAgentChat-Victory_d6adb53.md`** 
  - *Action:* Rephrase dramatic, informal storytelling language ("massive tantrum", "heartbreaking UI glitch", "Victory is ours") into objective engineering retrospective tone.
- **`ReFactor_Redux-1a933d9.txt`** 
  - *Action:* Scrub the self-referential AI blame narrative ("fault of the Antigravity engineering agent") into a neutral technical post-mortem.
- **`Philosophical_Proposal.md`** 
  - *Action:* Retain the core vision for neuronal node dynamics, but scrub abstract philosophical speculations on artificial sentience, Integrated Information Theory, and moral obligations to focus strictly on technical graph mechanics.

## 3. The Living Docs (UPDATE REQUIRED)
These documents act as the current documentation for the system but contain outdated references (e.g., legacy CLI usage, pre-TUI workflows, outdated phase statuses). They will be rewritten for Era 2 accuracy and published in the root repo. (Their original un-updated forms will be pushed to the History log).
- `README.md` (MACCREv2)
- `MACCRE_Operator_Manual.md`
- `Era2_architectural_roadmap.md`
- `omni_system_state_doctrine.md`
- `FeatureRequests.md`
- `auth_security_analysis.md`

## 4. The Core History (MERGE)
These files represent the chronological evolution of the architecture. They will be merged into a massive, cohesive `Project_History.md` that serves as the definitive record of how EXO_GANS was built.
* **Phase 4.75 / TUI Evolution:** `TUI_REFACTOR_PLAN.md`, `DETplanning-TUI Refactor.md`, `Phase4_75_6-CompletionWalkthrough.md`, `ctrl_node_analysis*` (v2 & draft), `ctrl_scatter-expansion plan*` (v1-v3).
* **Phase 5 Planning:** `PhASE5-implementation_plan*` (Final, Draft1, Draft2).
* **Search Backend Evolution:** `Search_Backend_Plan-Phase3_1.md`, `Search_Backend_Plan-Implementation.md`, `search_overhaul_roadmap.md`.
* **Foundational Architecture & Handovers:** `EXO_GANS_Wishlist_Architecture.md`, `exo_gans_handover.md`, `exo_gans_nexus_handover.md`, `oracle_review.md`, `Oracle_Hardening-Features-implementation_plan.md`, `ROUTER_RESOLUTION_HANDOVER.md`.
* **Legacy Eras (from `_historical_documentation/`):** `PHASE_HISTORY.md` (Phases 1-19), `OMNI_DAEMON_FOUNDING_DOCTRINE.md`, `Sovereignty_Analysis.md`, `MACCRE_Phase_Roadmap.md`.

---

## Next Steps upon Approval:
1. I will execute the redactions on the 4 files in Section 2.
2. I will merge the 30+ files in Section 4 into `docs/Project_History.md`.
3. I will draft the Sovereign Architect Manifesto.
4. I will scaffold the root `README.md`, `LICENSE` (AGPLv3), and `CONTRIBUTING.md`.
