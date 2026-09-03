# ROLLBACK DOCUMENTATION: Phase 6.12 Regression Recovery

**Date**: August 29, 2026  
**Rollback Target**: Aug 22, 2026 - Commit `a9f96dbadf5da59600576a70caea40be3e94894c`  
**Executed By**: Kiro AI Agent (under user supervision)  
**Backup Location**: `B:\EXO_GANS6.13-PRE-ROLLBACK.zip`

---

## Executive Summary

MACCREv2 codebase rolled back to Aug 19, 2026 state due to critical Phase 6.12 regression that broke CTRL_REVIEW node functionality. The regression was introduced between Aug 22-28 when wrong `.kiro` steering files (RadonVec context instead of MACCRE context) guided development, resulting in hardcoded short-circuits that prevented review checkpoints from functioning.

---

## Failure Timeline

### June 20-26, 2026: CTRL_REVIEW Golden Period ✅
- **20+ flows** with DET_PAUSE_MANUAL/CTRL_REVIEW nodes functioning correctly
- Manual HITL (Human-in-the-Loop) review checkpoints working as designed
- Flow pattern: `Agent → CTRL_REVIEW → (pause) → HITL_injection → Agent → END`
- Evidence: `__DATACENTER/GLOBAL/03_Agent_Ledgers/job_202606*` directories contain DET_PAUSE files + HITL_injection.md

### July 1-3, 2026: Quiet Period
- Simple test flows, no CTRL_REVIEW usage
- System stable, no development activity

### Aug 22, 2026: RadonVec Context Pollution
- **Root Cause**: User worked on RadonVec project in Kiro, requested `.kiro` steering files from Antigravity
- **Critical Mistake**: Forgot `.kiro/` files are GLOBAL, not project-specific
- RadonVec-focused steering applied to MACCRE development
- Oracle doctrine (5 Specialist Oracles) not engaged for MACCRE work

### Aug 23-28, 2026: Phase 6.12 Development Under Wrong Guidance ❌
- Phase 6.12 changes implemented WITHOUT proper MACCRE-specific Oracle steering
- **Regression Introduced**: `maccre_core/orchestration/flow_engine.py:1097-1106`
- CTRL_REVIEW nodes hardcoded to immediate END routing:
  ```python
  if step.macronode_name.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
      macro_def = {
          "topology_rows": [{
              "Node_ID": "CTRL_PAUSE_MANUAL",
              "Model_Override": "none",
              "Wait_For": "none",
              "Next_Node": "END"  # ← IMMEDIATE TERMINATION
          }]
      }
  ```
- **Impact**: Flows terminate after first node, register as "successful" despite incomplete execution
- No DET_PAUSE files created, no HITL injection possible, subsequent nodes never execute

### Aug 28-29, 2026: Discovery & Analysis
- User reports: "Flows run one node then exit successfully"
- Kiro analysis confirms: CTRL_REVIEW nodes never fire
- 60-day telemetry reconstruction identifies June baseline vs Aug broken state
- Git diff analysis reveals Phase 6.12 hardcoded short-circuit
- Decision: Rollback to last known good state

---

## Root Cause Analysis

### Primary Cause: Wrong .kiro Steering Context
**What happened**: RadonVec engineering context applied to MACCRE development  
**Why it matters**: MACCRE is a multi-agent orchestration system with sovereign datacenter architecture, RadonVec is a vector database slicing library. Completely different domains.  
**Consequence**: Agent made decisions appropriate for RadonVec but destructive to MACCRE

### Contributing Factor: .kiro Global Scope
**Design Issue**: `.kiro/steering` files apply globally across all projects in workspace  
**User Error**: Forgot steering was global when switching between RadonVec and MACCRE work  
**Impact**: No isolation between project contexts

### Technical Failure: Hardcoded Short-Circuit
**Location**: `flow_engine.py:1097-1106`  
**Pattern**: Explicit string matching bypassed MacroNode loading  
**Reason**: Likely attempted "quick fix" that became permanent  
**Oracle Doctrine Violation**: Law III (PATHS) - hardcoded logic instead of registry-driven

---

## Rollback Scope

### What IS Being Rolled Back:
- ✅ All Python codebase (`maccre_core/`, `maccre_tui/`, `maccre_mcp.py`, `maccre.py`)
- ✅ Any Phase 6.12 changes (including broken CTRL_REVIEW logic)
- ✅ Any Phase 6.13 planning code (if any existed)

### What IS NOT Being Rolled Back (Preserved):
- ✅ `.kiro/steering/` - NEW Oracle doctrine files created Aug 28-29
  - `cache_clearing_protocol.md`
  - `oracle_doctrine_analysis.md`
  - `orchestration_oracle_principles.md`
- ✅ `.kiro_artifacts/` - Analysis documents created during diagnostic phase
  - `2026-08-24_60day_telemetry_reconstruction.md`
  - `2026-08-28_phase_6.12_full_conversation.md`
  - `2026-08-28_phase_6.12_user_requirements.md`
  - `git_checkpoint_analysis.md`
- ✅ `__DATACENTER/` - Telemetry and ledger data
  - June baseline (CTRL_REVIEW working) PRESERVED
  - July simple tests PRESERVED
  - Aug 28 broken flows REMAIN (can be used for comparison)

### Rollback Target Selection:
**Chosen**: `a9f96dbadf5da59600576a70caea40be3e94894c` (Aug 19, 2026)  
**Commit Message**: "fix(tui): add high-contrast styling for BootSplashModal and universal OptionList text"  
**Rationale**: Last stable commit BEFORE RadonVec work began (Aug 22)  
**Includes**: Phase 4.99 Oracle fixes, Phase 4.75.7 CTRL_SCATTER work, July TUI hardening

---

## Expected Outcomes

### Immediate (Post-Rollback):
1. CTRL_REVIEW nodes should fire correctly (load MacroNode, execute CTRL_PAUSE, wait for HITL)
2. Multi-node flows should execute completely (not terminate after first node)
3. DET_PAUSE_MANUAL files should be created in job ledger directories
4. HITL_injection.md mechanism should function
5. flow_vector telemetry should show full execution path

### Validation Test:
Create simple 3-step flow:
```
AGENT_TestAgent_S0 → CTRL_REVIEW_S1 → AGENT_TestAgent_S2 → END
```

**Success Criteria**:
- Step 0: Agent runs, creates output
- Step 1: CTRL_REVIEW pauses, creates `DET_PAUSE_MANUAL_S1_*.md`
- User injects HITL guidance → `HITL_injection.md`
- Step 2: Agent resumes with HITL context, completes
- `flow_vector` = "TestAgent_S0>CTRL_REVIEW_S1>TestAgent_S2"

### If Rollback Fails:
**Hypothesis A**: __DATACENTER pollution from Aug 28 broken flows interferes  
**Remedy**: Clear Aug 23+ telemetry entries from system_logs.db

**Hypothesis B**: New `.kiro/steering` files insufficient to guide Aug 19 codebase  
**Remedy**: Refine Oracle steering files, add explicit CTRL_REVIEW preservation rules

**Hypothesis C**: Phase 4.75.7 CTRL_SCATTER work introduced subtle regression  
**Remedy**: Rollback further to Jul 28 pre-CTRL_SCATTER expansion (`6fb914efb1a84db2c3a29cb8cbbeddf3c030fe8c`)

---

## Lessons Learned

### 1. Global .kiro Steering Needs Project Scoping
**Current**: `.kiro/steering/*.md` applies globally to entire workspace  
**Needed**: Per-project steering or explicit project tagging  
**Workaround**: Manually switch steering files when changing projects

### 2. Oracle Doctrine Must Be Invoked Explicitly
**Failure**: Assumed Oracle guidance was present when it wasn't  
**Solution**: `.kiro/steering/` now contains explicit MACCRE Oracle principles  
**Prevention**: Invoke Oracles at session start for complex work

### 3. Hardcoded Short-Circuits Are Technical Debt Time Bombs
**Anti-Pattern**: `if node_name == "CTRL_REVIEW": hardcoded_behavior`  
**Doctrine Violation**: Law III (PATHS) - use registries, not string matching  
**Prevention**: All control nodes must load from registry, no special cases

### 4. Telemetry Is Institutional Memory
**Discovery Method**: 60-day reconstruction from `__DATACENTER` logs  
**Key Insight**: June job directories proved CTRL_REVIEW DID work  
**Value**: Without telemetry, regression would be "ghost bug" with no proof of prior function

### 5. Conversation Preservation Enables Replay
**Method**: Kiro session export + manual conversation archive  
**Use Case**: Extract user requirements, replay in clean environment  
**Next**: Test if proper Oracle steering prevents Phase 6.12 mistakes

---

## Forward Recovery Plan

### Phase 1: Validate Rollback (Aug 29)
- Run simple CTRL_REVIEW test flow
- Confirm DET_PAUSE fires correctly
- Verify HITL injection works
- Check telemetry shows full execution

### Phase 2: Selective Forward-Port (Aug 30+)
IF rollback validates baseline:
- Cherry-pick non-CTRL_REVIEW Phase 6.12 improvements
- Apply Phase 6.13 multi-lane planning with Oracle oversight
- Rebuild scatter/merge coordination correctly

IF rollback fails:
- Rollback further (Jul 28 or Jul 12)
- Engage all 5 Specialist Oracles for recovery guidance
- Rebuild from clean foundation

### Phase 3: Phase 6.13 Clean Room Reconstruction
- Use `.kiro_artifacts/2026-08-28_phase_6.12_user_requirements.md` as spec
- Apply proper MACCRE Oracle steering from start
- Implement multi-lane topology authoring with doctrine compliance
- Test at each milestone against June baseline metrics

---

## Metadata

**Rollback Executed**: 2026-08-29  
**Git Target**: `a9f96dbadf5da59600576a70caea40be3e94894c` (Aug 19, 2026)  
**Pre-Rollback Backup**: `B:\EXO_GANS6.13-PRE-ROLLBACK.zip`  
**Analysis Artifacts**: `.kiro_artifacts/` (preserved)  
**Oracle Steering**: `.kiro/steering/` (preserved, NEW)  
**Telemetry Baseline**: June 20-26, 2026 (preserved in __DATACENTER)

**Commit Message for This Document**:
```
docs: document Phase 6.12 regression and Aug 19 rollback rationale

Phase 6.12 introduced critical CTRL_REVIEW regression due to wrong
.kiro steering (RadonVec context applied to MACCRE). Hardcoded
short-circuit in flow_engine.py:1097-1106 prevented review nodes
from functioning. Rolling back to Aug 19 pre-RadonVec state to
restore working baseline. See ROLLBACK_2026-08-29_PHASE_6.12_FAILURE.md
for complete analysis and recovery plan.
```

---

## Sign-Off

**Approved By**: User (operator)  
**Executed By**: Kiro AI Agent  
**Status**: Ready for execution  
**Next Action**: `git checkout a9f96dbadf5da59600576a70caea40be3e94894c -- .` (preserving .kiro/ and .kiro_artifacts/)
