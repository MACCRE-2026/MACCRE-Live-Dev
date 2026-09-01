---
inclusion: fileMatch
fileMatchPattern:
  - 'maccre_core/orchestration/**'
---

# Orchestration & Engine Oracle Principles

**Auto-Applied**: This file is automatically included when editing files in `maccre_core/orchestration/`

---

## Mandatory Pre-Work Protocol

Before modifying ANY orchestration code, you MUST read these artifacts:

1. `B:\EXO_GANS\Analysis\Wave1\02_engine_swarms_ledger.md` - Swarm worker architecture
2. `B:\EXO_GANS\Analysis\Wave1\03_orchestration_factory_ledger.md` - MacroNode expansion
3. `B:\EXO_GANS\Analysis\Wave2\flowchart_02_orchestration_engine.md` - Flow engine flowchart
4. `B:\EXO_GANS\Analysis\Wave3\MASTER_FLOWCHART.md` - System-wide architecture

**Why**: Understanding existing architecture prevents breaking shared state contracts.

---

## Shared State Contract Rules

Any `threading.Event`, `queue.Queue`, or shared mutable state MUST be documented:

### Ownership Model
- **Owner**: Creates the object, manages its lifecycle, has exclusive mutation rights
- **Observer**: Receives reference as parameter, can only READ state
- **Mutator**: Explicitly granted write permission by owner

### Critical Rule
**If a function receives a `threading.Event` as a parameter, it is an OBSERVER.**

❌ **NEVER** call `.set()` or `.clear()` unless you are the owner.

### Example
```python
# flow_engine.py (OWNER)
cancel_event = threading.Event()  # I own this

# swarm_pool.py (OBSERVER)
def run_until_drained(self, stop_event: threading.Event | None):
    # I received this event - I can only READ it
    if stop_event is not None and stop_event.is_set():  # ✅ OK - reading
        break
    
    # ❌ WRONG - This cancels the entire flow, not just my step!
    # stop_event.set()  # NEVER do this!
```

---

## Task Artifact Mandate

After ANY orchestration change, create:

1. **Task Artifact**: `B:\EXO_GANS\.oracle_artifacts\YYYY-MM-DD_<task_name>.md`
2. **Ledger Entry**: Append to `B:\EXO_GANS\.agent\skills\Specialists\OrchestrationAndEngine_Oracle\task_ledger.md`

### Task Artifact Template
```markdown
# YYYY-MM-DD: <Task Name>

## Summary
Brief description of the change

## Files Modified
- `path/to/file.py` - What changed

## Function Signatures Added/Changed
```python
def new_function(param: Type) -> ReturnType:
    """What it does"""
```

## State Contracts
| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| cancel_event | flow_engine.execute_flow() | swarm_pool, workers | Owner only |

## Architecture Decisions
- Why this approach was chosen
- Tradeoffs considered
- Alternative approaches rejected

## Testing
- What tests were added/modified
- How to verify the change works
```

---

## System-Wide QA Gate

After EVERY orchestration change, from the project root:

```powershell
cd B:\EXO_GANS
omni qa
```

See `omni_pipeline_mandate.md` (always applied) for the full doctrine. In short:

- **Never** scope the gate — not `omni qa flow_engine.py`, and not by substituting
  `python -m ruff check maccre_core/orchestration` or
  `python -m pyright <file>`. Scoped checks create "success-siloing" that masks:
  - Cross-module type breaks
  - Broken return tuples
  - Dangling imports in adjacent scopes
- **`omni qa` does not run tests.** Follow it with
  `.venv\Scripts\python.exe -m pytest tests -q` and check the *collected* count, then
  `omni smoke` for changes to execution paths.
- Omni is system-pathed at `C:\OmniBuilder\` — outside this repo. Searching the
  workspace for it finds nothing; that is expected, not a missing tool.

The **entire project** must be mathematically valid after every change, not just the
orchestration layer.

---

## Integration Testing Requirements

Unit tests are NOT sufficient for orchestration changes.

### Minimum Test Suite
After ANY flow_engine.py or swarm_*.py modification:

1. **Multi-step flow** (minimum 3 steps)
   - Verifies step loop doesn't break early
   - Verifies payload passing between steps

2. **CTRL_REVIEW flow** (pause/resume)
   - Verifies pause_event handling
   - Verifies Human-in-the-Loop integration

3. **CTRL_SCATTER flow** (concurrency)
   - Verifies scatter lane execution
   - Verifies gather synchronization
   - Verifies concurrent worker management

### How to Run
```bash
# Start TUI
omni run run.py

# Build test flows in UI:
# 1. Agent -> Agent -> Agent (3 steps)
# 2. Agent -> CTRL_REVIEW -> Agent
# 3. CTRL_SCATTER -> [lanes] -> (implicit CTRL_MERGE)

# Execute and verify all complete successfully
```

---

## Common Bug Patterns to Avoid

### Bug: Setting Shared Events
```python
# ❌ WRONG - Cancels entire flow
def my_function(stop_event: threading.Event):
    stop_event.set()  # I don't own this!

# ✅ CORRECT - Only observe
def my_function(stop_event: threading.Event):
    if stop_event.is_set():
        return  # Respect the owner's decision
```

### Bug: Modifying Shared Lists
```python
# ❌ WRONG - Side effects on caller's data
def process_steps(steps: list[FlowStep]):
    steps.clear()  # Mutating shared state!

# ✅ CORRECT - Create new list
def process_steps(steps: list[FlowStep]) -> list[FlowStep]:
    return [step for step in steps if step.is_valid()]
```

### Bug: Thread-Unsafe SQLite
```python
# ❌ WRONG - No transaction
conn.execute("UPDATE tasks SET status='done'")

# ✅ CORRECT - Explicit transaction
conn.execute("BEGIN EXCLUSIVE")
try:
    conn.execute("UPDATE tasks SET status='done'")
    conn.commit()
except:
    conn.rollback()
    raise
```

---

## When to Invoke OrchestrationAndEngine_Oracle Sub-Agent

For **major refactors** (e.g., replacing execution loop, adding new control primitives):

1. Invoke `OrchestrationAndEngine_Oracle` sub-agent
2. Provide: files to modify, goal, constraints
3. Oracle reads domain artifacts (Wave1/2/3)
4. Oracle provides architecture analysis + implementation plan
5. Oracle creates task artifact documenting state contracts
6. Main agent implements following Oracle's plan

**Why**: Oracles have domain-specific context and enforce doctrine compliance.

---

## Doctrine Alignment

These principles derive from:
- **GEMINI.md** Sections I, II, III (Omni compliance, architecture patterns)
- **OrchestrationAndEngine_Oracle SKILL.md** (Subsystem refresher, task artifacts)
- **Phase 6.12 Post-Mortem** (stop_event bug analysis)

**Last Updated**: August 28, 2026
