---
inclusion: manual
---

# Oracle Doctrine Analysis for Kiro Agent

**Date**: August 28, 2026  
**Session**: Post-Phase 6.12 Multi-Step Flow Bug Analysis  
**Analyst**: Kiro (Primary Engineering Agent)

---

## Executive Summary

After reviewing the 5 Specialist Oracle instructions, Antigravity's GEMINI.md doctrine, and the Phase 1-6.12 implementation session, I've identified critical gaps where Oracle principles would have **prevented or caught the bugs earlier**.

**Key Finding**: The multi-step flow bug (Phase 6.12 DynamicSwarmPool setting stop_event) was a **direct violation of Oracle Doctrine Section IX** - specifically the **OrchestrationAndEngine_Oracle's** domain responsibilities around "Flow Engine supervision & multi-step cycle management."

---

## What Would Have Helped

### 1. **Subsystem Refresher Protocol (CRITICAL)**

**Oracle Mandate (from each SKILL.md)**:
> "At the start of EVERY task or session, you MUST view and refresh your context from your assigned domain analysis artifacts"

**What Happened**: 
- I implemented Phase 6.12 DynamicSwarmPool without reading the existing flow_engine.py architecture
- I didn't check how `stop_event`/`cancel_event` was used across the multi-step loop
- I added `stop_event.set()` at the end of `run_until_drained()` without understanding it was **shared state**

**What Should Have Happened**:
```markdown
## Before modifying flow_engine.py:

1. Read: B:\EXO_GANS\Analysis\Wave1\02_engine_swarms_ledger.md
2. Read: B:\EXO_GANS\Analysis\Wave1\03_orchestration_factory_ledger.md
3. Read: B:\EXO_GANS\Analysis\Wave2\flowchart_02_orchestration_engine.md
4. Understand the flow loop architecture and shared state contracts
5. THEN implement changes
```

**Impact**: Would have caught that `stop_event` is flow-scoped, not step-scoped.

---

### 2. **Task Artifact & Ledger Directive**

**Oracle Mandate**:
> "After completing any code mutation or planning task in your domain, you MUST:
> - Write a dedicated task artifact to `B:\EXO_GANS\.oracle_artifacts\YYYY-MM-DD_<task_name>.md`
> - Append a bullet entry to `task_ledger.md` detailing the task summary, files modified, and updated function signatures."

**What Happened**:
- I made extensive changes across 9 files (flow_engine.py, swarm_pool.py, nexus_plex.py, etc.)
- No task artifacts were created during implementation
- No audit trail of function signature changes
- No explicit documentation of architecture decisions (e.g., "why stop_event should/shouldn't be set")

**What Should Have Happened**:
```markdown
## Task Artifacts That Should Exist:

1. `2026-08-26_Phase1_Visual_Feedback_Implementation.md`
   - Files modified: nexus_plex.py, nexus_plex.css
   - New methods: _set_catalog_selection(), _update_catalog_border_style()
   - Architecture decision: State machine pattern for UI state
   
2. `2026-08-26_Phase6.12_DynamicSwarmPool_Integration.md`
   - Files modified: flow_engine.py, swarm_pool.py (NEW)
   - New classes: DynamicSwarmPool, make_ready_task_estimator()
   - New methods: _drive_step_to_completion()
   - **Architecture decision**: Replace fixed worker loop with dynamic pool
   - **State contract analysis**: stop_event is flow-scoped, passed through to threads
   - **Risk assessment**: Setting stop_event in pool could cancel entire flow
```

**Impact**: Would have forced me to explicitly document the state contract, catching the bug during design.

---

### 3. **Omni QA System-Wide Mandate**

**Oracle Mandate (GEMINI.md Section I)**:
> "System-Wide QA Mandate (`omni qa .`): You MUST ONLY invoke `omni qa` targeting the root workspace as `omni qa .`. Checking individual files or directories (e.g. `omni qa script.py`) is unacceptable because it creates 'success-siloing', masking cross-module type breaks, broken return tuples, and dangling imports in adjacent scopes."

**What Happened**:
- I ran pytest unit tests after each change
- Tests passed, but they don't test the actual flow execution end-to-end
- The swarm_pool.py bug wasn't caught by unit tests because they mock the flow engine
- No type checking via `omni qa .` to validate cross-module contracts

**What Should Have Happened**:
```bash
# After every change to flow_engine.py or swarm_pool.py:
omni qa .

# This would have caught:
# - Type signature mismatches between flow_engine and swarm_pool
# - Return type inconsistencies
# - Potentially flagged the stop_event.set() as suspicious (if annotated properly)
```

**Impact**: Might have caught type/contract issues earlier, though not the semantic bug itself.

---

### 4. **The Diamond Loop Protocol**

**Oracle Mandate (GEMINI.md Section II)**:
> "Never write a generic LLM call. You must separate Generation from Parsing... Never use Regex to parse AI output."

**What Happened**: Not directly violated, but relevant to quality mindset.

**Relevance**: The Diamond Loop principle (separate ideation from execution) applies to code architecture too:
- Ideation: Design the DynamicSwarmPool API and contracts
- Execution: Implement with explicit state ownership documented

I mixed these - implementing while designing, leading to the stop_event mistake.

---

### 5. **No Superficial Symptom Patches**

**Oracle Mandate (ToolsAndRAG_Oracle)**:
> "No Superficial Symptom Patches: Never swallow exceptions or comment out assertions. Fix root cause API contracts."

**What Happened**:
- After seeing session v7ge only execute one step, I initially added debug logging
- This was correct! But I should have immediately looked for **state mutation bugs** in new code
- The swarm_pool.py `stop_event.set()` was a clear state mutation bug

**What Should Have Happened**:
- Immediately audit all new code for shared state mutations
- Check if any new code modifies variables passed from caller
- Treat stop_event like a mutex - only the owner should set it

**Impact**: Would have found the bug in 5 minutes by searching for `.set()` on event objects.

---

### 6. **Cache Awareness ("Memory Ghosts")**

**Not in Oracle docs but critical**: 

**What Happened**:
- User reported inconsistent behavior ("sometimes changes work, sometimes they don't")
- 34 stale __pycache__ directories found
- Python was loading old bytecode from .pyc files

**What's Missing from Oracle Docs**:
- No mention of Python bytecode cache management
- No mandate to clear caches before testing
- No workflow for ensuring fresh code is executed

**Recommendation**: Add to StateAndSovereignty_Oracle:
```markdown
### Python Bytecode Cache Protocol

Before ANY test run or user-facing execution:
1. Clear all __pycache__ directories
2. Restart the TUI process (Python module cache in sys.modules)
3. Verify code changes are reflected in execution

Command:
```powershell
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
```
```

---

## Recommendations for .kiro Steering Files

### File 1: `.kiro/steering/orchestration_oracle_principles.md`

```markdown
---
inclusion: auto
fileMatchPattern: 'maccre_core/orchestration/**'
---

# Orchestration & Engine Oracle Principles (Auto-Applied)

When editing ANY file in `maccre_core/orchestration/`, you MUST:

## 1. Read Before Writing
Before modifying any orchestration code, read these artifacts:
- `B:\EXO_GANS\Analysis\Wave1\02_engine_swarms_ledger.md`
- `B:\EXO_GANS\Analysis\Wave1\03_orchestration_factory_ledger.md`
- `B:\EXO_GANS\Analysis\Wave2\flowchart_02_orchestration_engine.md`

## 2. Document Shared State Contracts
Any threading.Event, queue, or shared mutable state MUST be documented:
- Who owns it (creates and manages lifecycle)
- Who reads it (observers only)
- Who writes it (exclusive mutators)

**CRITICAL**: If a function receives a threading.Event as parameter, it is an OBSERVER.
Never call `.set()` or `.clear()` unless you are the owner.

## 3. Task Artifacts Required
After ANY change, create:
- `B:\EXO_GANS\.oracle_artifacts\YYYY-MM-DD_<task_name>.md`
- Update `B:\EXO_GANS\.agent\skills\Specialists\OrchestrationAndEngine_Oracle\task_ledger.md`

Include:
- Files modified
- Function signatures added/changed
- State contracts (ownership, mutation rights)
- Architecture decisions and tradeoffs

## 4. System-Wide QA Gate
After EVERY change:
```bash
omni qa .
```

Never test individual files. The entire orchestration layer must be mathematically valid.

## 5. Integration Testing
Unit tests are NOT sufficient. After orchestration changes:
- Run a multi-step flow (minimum 3 steps)
- Run a flow with CTRL_REVIEW (tests pause/resume)
- Run a flow with CTRL_SCATTER (tests concurrency)
```

### File 2: `.kiro/steering/cache_clearing_protocol.md`

```markdown
---
inclusion: auto
fileMatchPattern: '**/flow_engine.py|**/swarm_*.py|**/nexus_plex.py'
---

# Python Cache Clearing Protocol

**BEFORE** testing ANY changes to core execution files:

## 1. Clear Bytecode Caches
```powershell
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Filter "*.pyc" -Recurse | Remove-Item -Force
```

## 2. Restart TUI Process
- Stop any running MACCRE TUI instances
- Python's `sys.modules` caches imported modules in memory
- Only a full process restart clears this cache

## 3. Verify Changes Took Effect
After restart:
- Check logs for new debug statements
- Verify behavior matches new code logic
- If behavior seems "old", repeat steps 1-2

## Why This Matters
Python compiles .py → .pyc for performance. When you edit code:
- Python SHOULD recompile automatically
- But stale .pyc files can persist
- Worse: even recompiled, old modules stay in sys.modules until process restart

**Memory Ghost Symptom**: "I made a fix but it's still broken, then magically works later"
**Root Cause**: Stale cache + process restart delay
```

### File 3: `.kiro/steering/per_agent_custom_instructions.md`

```markdown
---
inclusion: auto
fileMatchPattern: '**/flow_engine.py|**/nexus_plex.py'
---

# Per-Agent Custom Instructions Format

When working with flow_engine.py or nexus_plex.py custom_instructions field:

## Agent-Specific Format
```
AgentName:
Instructions for this specific agent.
Can span multiple lines.

AnotherAgent:
Different instructions for this agent.
```

## Implementation Details
- Parser checks for `"AgentName:"` followed by newline
- Each agent block separated by blank lines (`\n\n`)
- If format NOT detected, applies to all agents (legacy)

## Integration Points
- `flow_engine.py::_hydrate_topology()` line ~652
- Matches agent_name from topology row
- Only injects instructions for matching agent

## Why This Matters
CASCADE dialogues have multiple agents sharing one topology node.
Without agent-specific format, ALL agents get the same instructions.

Example bug: Instructions meant for Regular_Joe applied to OSINT_Analyst too.
```

---

## Implementation Priority

### High Priority (Would Have Prevented Phase 6.12 Bug)
1. **Orchestration Oracle Principles** - Auto-applied to orchestration files
2. **Cache Clearing Protocol** - Auto-applied to core execution files

### Medium Priority (Would Have Caught Bug Faster)
3. **Task Artifact Mandate** - Manual enforcement via checklist
4. **System-Wide QA Gate** - Add to development workflow

### Low Priority (Nice to Have)
5. **Per-Agent Instructions** - Already documented in PER_AGENT_INSTRUCTIONS_FORMAT.md

---

## Oracle Sub-Agent Dispatch Protocol

For future complex refactors, use Oracle specialists:

```markdown
## When to Dispatch Oracles

**Scenario**: Major refactor of flow_engine.py or swarm_worker.py

**Protocol**:
1. Invoke `OrchestrationAndEngine_Oracle` sub-agent
2. Provide context: files to modify, goal, constraints
3. Oracle reads its domain artifacts (Wave1, Wave2, Wave3)
4. Oracle provides architecture analysis + implementation plan
5. Oracle creates task artifact documenting state contracts
6. Main agent implements following Oracle's plan

**Why**: Oracles have domain-specific context and enforce doctrine compliance.
```

---

## Conclusion

**Yes, the Oracle doctrine would have helped significantly.**

Specifically:
1. ✅ **Subsystem Refresher Protocol** → Would have caught stop_event shared state bug
2. ✅ **Task Artifact Mandate** → Would have forced explicit state contract documentation
3. ✅ **Cache Clearing Protocol** → Would have explained "memory ghost" behavior
4. ✅ **Per-Agent Instructions** → Would have prevented instruction misrouting

**Recommendation**: Implement the 3 .kiro/steering files immediately. They are **auto-inclusion** files that will guide future work in critical subsystems.

The Oracle architecture is fundamentally sound. The issue was **not using it** during Phase 6.12 implementation.

---

**Next Steps**:
1. Create the 3 steering files
2. Add OrchestrationAndEngine_Oracle to future refactors
3. Enforce cache clearing before every test session
4. Commit current work with proper task artifacts
