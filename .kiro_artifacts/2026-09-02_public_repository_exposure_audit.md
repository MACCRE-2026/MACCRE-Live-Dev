# Public Repository Exposure Audit

**Date:** 2026-09-02
**Scope:** `github.com/MACCRE-2026/MACCRE-Live-Dev` and the local `B:\EXO_GANS` tree
**Trigger:** Planning the `git-manager` sub-agent surfaced that `.kiro_artifacts/` is
tracked while the remote's `.gitignore` calls itself PUBLIC. This audit establishes what
is actually exposed rather than what is assumed.
**Method:** unauthenticated GitHub API probe; `git grep` against `origin/main` and `HEAD`
across six secret patterns and seven PII patterns.

---

## Verdict in one paragraph

**The repository is public, and nothing dangerous is in it.** No credentials of any kind,
no databases, no real session data, no machine identifiers, no IP addresses. What is
exposed is the operator's real name — published deliberately as an authorship credit —
and his Windows username, leaked incidentally through four dead `file:///` links and one
draft. Severity is **LOW**: none of it is exploitable, and none of it is a secret. Three
further files carrying the username are **committed locally but unpushed**, so they are
still preventable. One item is **time-critical**: GitHub's traffic statistics answer "was
anything pulled" and expire on a 14-day rolling window that closes around 2026-09-06.

---

## 1. Exposure surface — confirmed facts

```
remote        github.com/MACCRE-2026/MACCRE-Live-Dev
private       False          <- PUBLIC
visibility    public
created       2026-08-09
last push     2026-08-23
size          24,086 KB
forks 0   stars 0   watchers 0   open issues 0
```

**Exposure window: 2026-08-09 to 2026-08-23.** `origin/main` is at `7961750` (2026-08-22).

**Six local commits have never left this disk:**

```
c39b9fb  docs: record where 4.99 user testing stands and why it is paused
83950b6  fix(orchestration): stop the merge restating the session ledger
15f5ee4  fix(orchestration,tui): F1/F2/F3 pause path, and timeout now stops the flow
c9b29a5  fix(orchestration): E1/E2 payload lineage
762f614  checkpoint: Phase 6.13 Track A + Track D and four follow-on scatter defects
f7b326f  docs: document Phase 6.12 regression and Aug 19 rollback rationale
```

Everything produced in the 2026-09-01/02 sessions is therefore **unexposed**.

## 2. The database question — answered, and it is good news

The last pushed commit is titled *"add real MACCRE sample databases and ingestion guide
for Kiro RadonVec slicing"*, which reads alarming. It is not:

```
7961750  1 file changed, 51 insertions(+)
  AG_KIRO-Collab-Space/from-ag-maccre/sample_databases/README.md
```

**A 51-line README only.** A full tree scan for `*.db`, `*.db-wal`, `*.db-shm`,
`*.sqlite`, `*.sqlite3` across `origin/main` returns **zero files**. No session data, no
agent ledgers, no `swarm_queue.db`, no `project_registry.db` was ever pushed.

## 3. Credentials — clean, all six patterns

Scanned against `origin/main` **and** the full local tree at `HEAD`:

| Pattern | `origin/main` | local `HEAD` |
|---|---|---|
| Google API key (`AIza…`) | 0 | 0 |
| OpenAI / Anthropic (`sk-`, `sk-ant-`) | 0 | 0 |
| GitHub token (`ghp_`, `github_pat_`) | 0 | 0 |
| Generic `api_key`/`secret`/`password`/`token` assignment | 0 | 0 |
| Private key block (`BEGIN … PRIVATE KEY`) | 0 | 0 |
| Literal `Authorization: Bearer …` | 0 | — |

The vault design is doing its job: credentials live outside the tree, and
`.gitignore` / `.git/info/exclude` cover `.env`, `vault_keys.json`, `secrets/`, `.vault/`
and `mcp_config.json`.

## 4. What IS exposed

### 4a. Real name — deliberate, not a leak

`sovereign_agentic_evolution_report.md:4` carries an `**Author:**` line giving the
operator's full legal name and the title "Senior Project Architect // MACCRE Systems".
Quoted by location rather than by content, so this audit does not itself become a second
public instance of it.

An intentional authorship credit. Flagged only so the decision is conscious: the
operator's legal name is attached to a public repository, which is normal for authored
work and worth knowing before the register's *"Rename Nexus Copilot before any public
artifact"* entry is actioned alongside any wider publication push.

### 4b. Windows username — incidental, in four places

Four dead `file:///` links to local Antigravity transcripts:

```
DETplanning-TUI Refactor-Draft2.md:452,453,455
DETplanning-TUI Refactor-FinalDraft.md:3
  file:///C:/Users/<username>/.gemini/antigravity/brain/<uuid>/implementation_plan.md
```

These leak three things: the username, the fact that Antigravity was the tool, and
internal session UUIDs. All three are low value — the links resolve to nothing for any
other reader, and the UUIDs are meaningless without the local files. They are also simply
broken references in a published document, so removing them improves the document.

One further hit in `.oracle_artifacts/2026-07-25_substack_part5_state_sovereignty.md:22`,
inside prose about agents dumping temp files — a real path used as an illustration in a
Substack draft.

### 4c. Not findings, recorded so they are not re-investigated

- **Four email addresses** — all library-maintainer addresses from vendored metadata
  (`charlie.clark@clark-consulting.eu`, `fredrik@pythonware.com`,
  `openpyxl-users@googlegroups.com`, `xnoguer@rezebra.com`). openpyxl and PIL authors.
  **Not the operator's.** False positives.
- **`C:\Users\...` in `draft_era3_phase9_tui_interface.md:61`** — the literal string used
  as an example of a portability risk. Not a real path.
- **`B:\EXO_GANS` in 126 places across 34 files** — reveals the project root and drive
  letter. Directory structure, not a secret. Informational only.
- **Machine name, IPv4 addresses** — zero hits.

### 4d. A correction to an earlier claim

In session I stated that `.oracle_artifacts/` has no version control because it appears in
`.git/info/exclude`. **That was wrong.** `.git/info/exclude` only prevents *untracked*
files from being added; files already tracked stay tracked. `.oracle_artifacts/` is
therefore in a **mixed state** — older files such as
`.oracle_artifacts/MACCRE_Master_Agent_Library.md` (37.5 KB) and the 2026-07-25 Substack
drafts are tracked and public, while files created after the exclude was added are ignored.

This ambiguity is itself the most important finding in the audit. A directory that is
half-tracked and half-ignored will surprise whoever next assumes either.

## 5. Preventable — three unpushed files

Committed locally, not yet public:

| File | Line | Content |
|---|---|---|
| `.kiro_artifacts/2026-08-28_phase_6.12_full_conversation.md` | 22 | a quoted `C:\Users\<username>\.gemini\GEMINI.md` path |
| `.kiro_artifacts/2026-08-28_phase_6.12_user_requirements.md` | 14 | the same path, quoted |
| `ROLLBACK_2026-08-29_PHASE_6.12_FAILURE.md` | 226 | an `**Approved By**: User (<username>)` attribution |

**How they got there, recorded because it is the exact failure the `git-manager` exists to
prevent.** Commit `762f614` staged `.kiro_artifacts/` **wholesale** — `git add
.kiro_artifacts/` — bringing conversation transcripts under version control without any
content scan. That was my error on 2026-09-01. The commit message lists what it contains
by category and says nothing about having read it. Two days later this audit is what
should have run before that `git add`.

## 6. Was anything pulled? — partially answerable, and time-critical

**What can be established from here:** 0 forks, 0 stars, 0 watchers. No public engagement
signal at all.

**What cannot:** clone and view counts. Those require authenticated owner access.

**Action, and it expires.** GitHub → repository → **Insights → Traffic** shows unique
clones and visitors on a **14-day rolling window**. The last push was 2026-08-23, which is
10 days ago, so the window **still covers the most recent exposure but closes around
2026-09-06.** If the question "did anyone pull this" matters, that page has to be read in
the next four days; after that the data is gone and the question becomes permanently
unanswerable.

Recommend screenshotting or recording the numbers into this artifact regardless of what
they say, since a recorded zero is evidence and an unrecorded zero is not.

## 7. Recommended actions, in priority order

1. **Read Insights → Traffic and record it here.** Time-boxed; expires ~2026-09-06.
2. **Scrub the three unpushed files before any push.** Replace the paths with
   `<user-home>` and `User (operator)`. Cheap, and it is the whole preventable set.
3. **Resolve `.oracle_artifacts/`'s mixed state deliberately** — either `git rm --cached`
   the tracked ones so the directory is uniformly private, or accept that it is public and
   scrub accordingly. Half-and-half is the state that causes accidents.
4. **Remove the four dead `file:///C:/Users/...` links.** Improves the documents
   independently of privacy.
5. **Decide on `git push`.** Six commits sit on one disk; that is risk R8, still open. The
   scrub in (2) should land first.
6. **Do not rewrite public history.** The exposed items do not justify a force-push: the
   name is deliberate, and a username in a dead link is not worth the coordination cost or
   the risk to a repo that is someone's published work. Fix forward.

## 8. What this audit did not cover

- **Commits between `f7b326f` and repo creation were not scanned individually.** The scan
  was against the `origin/main` **tree**, so a secret that was committed and later deleted
  would still be in history and would **not** appear in these results. A full history scan
  (`git log -p` across all refs, or a dedicated tool such as `gitleaks`/`trufflehog`) is
  the honest way to close that gap and has not been run.
- **Binary files were skipped** (`git grep -I`). A credential inside a binary or archive
  would not be found. Note `.kiro_artifacts/kiro-session-*.zip` (2.67 MB) is tracked
  locally and unpushed — its contents were **not** inspected and it is a session archive,
  which is the most likely place for transcript PII.
- **No claim is made about the tree's lint/type state**; no gate was run for this audit.

---

## 9. Addendum — independent verification by the `git-manager` agent

The `git-manager` sub-agent was created immediately after §1–8 and run on a read-only
state report as its first exercise. **It found four things the manual pass above missed or
under-quantified.** Recorded here rather than silently folded in, because the delta is the
argument for the agent existing.

### 9a. The branch has no upstream at all

```
Branch    phase/6.13-track-a-d-and-payload-lineage
Upstream  none configured  (fatal: no upstream configured)
```

§1 reported "6 unpushed commits" from `git rev-list --count origin/main..HEAD`, which works
only because `origin/main` was named **explicitly**. The branch itself tracks nothing, so
`git push` with no arguments would not know where to go, and any tooling relying on `@{u}`
fails rather than reporting zero. The correct count of commits reachable from no remote is
**6 of 128 total local commits**.

### 9b. `.oracle_artifacts/` is 39 tracked, not "some older files"

**39 tracked / 12 ignored.** §4d described the mixed state qualitatively; the number is
what makes it actionable. The tracked set is `.gitkeep`, five `2026-07-25_substack_part*`,
five `2026-07-28_ctrl_scatter_review_*`, five `2026-07-28_phase4_75_7_roadmap_audit_*`,
five `2026-07-28_phase4_99_user_test_actions_*`, five `2026-08-09_*_Oracle_phase4_99_audit`,
`MACCRE_Master_Agent_Library.md`, two `audit_release_*`, five `draft_era3_phase9_*` and
five `draft_era3_roadmap_*`.

So **the majority of the Oracle audit history is public**, not a stray handful.

### 9c. `scripts/` is also MIXED — missed entirely above

**1 tracked / 64 ignored.** The remnant is `scripts/migrate_det_to_ctrl.py`. §4d named only
`.oracle_artifacts/`, so the manual pass found one of the two mixed directories. A
second-order lesson: having found one instance of a pattern, the manual pass stopped
looking. The agent enumerated every rule in both ignore files and found the other.

### 9d. `.kiro_artifacts/` and `.kiro/` are tracked and are not excluded at all

`.kiro_artifacts/` 12 tracked of 13 on disk; `.kiro/` 10 of 11. Neither appears in
`.git/info/exclude`. These are the directories that accumulate **conversation transcripts
and session material**, and they are fully inside version control pointed at a public
remote. That is the same shape as the `762f614` incident, still live — the incident was not
a one-off mistake but the predictable result of a tracked directory that grows transcripts.

The agent named this unprompted as an ongoing hazard rather than a past event, which is the
sharper framing and is adopted here.

### 9e. It refused to run `git fetch`, and said why

`git fetch` mutates local refs, so the agent declined it under its own read-only remit and
**stated the consequence**: `origin/main` is known only as of 2026-08-22 21:09, `.git/FETCH_HEAD`
is absent, and therefore it cannot tell whether the remote has moved since. §1's exposure
window rests on that same unrefreshed state and inherits the same caveat.

### 9f. And it caught this audit leaking the PII it documents

A scan of the newly written §1–8 found the operator's username reproduced in **four
places** — the author line, the `file:///` example, and two rows of the §5 table — plus the
full legal name quoted verbatim. A privacy audit that reproduces its own findings is worse
than no audit, because it carries the appearance of diligence.

Scrubbed to `<username>` placeholders and location-only references before this file was
staged. Recorded rather than quietly fixed: the failure mode is *documenting* an identifier
being indistinguishable, to a grep, from *leaking* one — and any future scanner will flag
this file, correctly, unless the placeholder convention is known.

**Convention adopted:** audit artifacts refer to identifiers as `<username>`,
`<machine-name>`, `<uuid>` and by `path:line` location, never by literal value.

### Net effect on §7's priority list

Unchanged in order, with two additions: **configure an upstream** before any push is
attempted, and **resolve `scripts/` alongside `.oracle_artifacts/`** since both are MIXED.
The `.kiro_artifacts/` and `.kiro/` tracking decision is now the largest open question —
those two directories are where transcripts land, and they are currently public by default
rather than by decision.
