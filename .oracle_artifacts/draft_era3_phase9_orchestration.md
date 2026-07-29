# Era 3 Swarm Engine & Orchestration Roadmap: Phase 9 Addition
**Subsystem:** Core Swarm Engine & Orchestration (`maccre_core/orchestration/`)  
**Author:** Orchestration & Engine Specialist Oracle  
**Theme:** Phase 9 — In-State Live Development & Antigravity Desktop Transition Bridge  
**Date:** 2026-07-25  

---

## 1. Executive Summary & Vision

Phase 9 represents the ultimate convergence of deterministic orchestration, isolated state deployment, and living trajectory compiler mechanics. It transitions MACCREv2 / EXO_GANS from a static execution framework into an **autonomous, self-improving edge runtime**.

Under Phase 9, the Swarm Engine builds, tests, and evaluates candidate state changes and workflow topologies entirely from within. It isolates candidate deployment states using `shutil.copy2` database forks, ingests external developer/Antigravity tool call trajectories into optimized `CTRL_` ControlNode DAG topologies, and binds every evolutionary mutation to an embedded, immutable Git execution lineage.

---

## 2. Core Pillars of Phase 9 in Swarm Engine & Orchestration

### 2.1 In-State Live Development & Frozen State Sandboxing
- **Zero-Side-Effect Candidate Deployment**: When the system proposes a candidate self-improvement (code refactor, prompt optimization, or node topology update), `flow_engine.py` initializes a `CandidateSandboxManager`.
- **`shutil.copy2` Database Forking**: The active SQLite queue state (`swarm_queue.db`) and telemetry databases are cloned into `02_Dynamic_Context/sandboxes/candidate_<id>/candidate_queue.db`.
- **Built-in Test Topology Verification**: The candidate is executed in `ExecutionMode.IN_STATE_TEST` against automated benchmark topologies (`CTRL_TEST_HARNESS`).
- **Atomic Promotion / Rollback**: A Quadrivector Critic evaluates candidate telemetry. If 100% of assertion gates pass, state mutations are atomically committed (`BEGIN EXCLUSIVE`) to production databases and codebase. If any assertion fails, the candidate sandbox directory is unlinked with zero residual state pollution.

### 2.2 Replaying Antigravity Tool Calls & Trajectories as `CTRL_` ControlNode DAGs
- **Trajectory Ingestion Engine (`TrajectoryCompiler`)**: Converts raw tool call streams (e.g. Antigravity IDE action logs, CLI transcripts, MCP tool calls) into optimized, deterministic DAG topologies.
- **Token-Free Control Primitive Substitution**:
  - File Reads / Workspace Context Gathering $\rightarrow$ `CTRL_PAYLOAD_INJECT` / `CTRL_TRANSFORM`.
  - Quality Checks / QA Assertions $\rightarrow$ `CTRL_GATE` / `CTRL_CONDITIONAL_ROUTE`.
  - Concurrent Workspace Operations $\rightarrow$ `CTRL_SCATTER` / `CTRL_MERGE`.
  - Iterative Debug Loops $\rightarrow$ `CTRL_RECURSION` (with refractory limits).
- **Session Bridge Trajectory Playback**: Extends `AgentStudioChatScreen`'s Session Bridge Compiler to load, edit, visualize, and replay compiled trajectory DAGs directly in the NexusPlex TUI.

### 2.3 Living Local Git Model for Immutable System Evolution
- **Commit-on-Flow State Serialization**: Integrates an embedded Git wrapper (`maccre_core/utils/git_engine.py`) into `flow_engine.py`. Every successful in-state candidate deployment or session milestone generates a lightweight local Git commit.
- **Topological Lineage Cryptography**: Unifies `flow_vector` lineage strings (`SCATTER_A:AGENT_B:MERGE_A`) with Git commit SHA-256 hashes (`flow_vector_sha256`), providing tamper-proof cryptographic auditability of how system code and topologies evolved over time.
- **Topological Branching & Rollbacks**: Local Git branches map cleanly to candidate flow branches (`branch: candidate/flow_refactor_v2`), enabling instant time-travel rollbacks and side-by-side branch execution.

---

## 3. Concrete Implementation Specifications

### 3.1 New & Extended Primitives (`deterministic_nodes.py`)
- **`CTRL_GIT_COMMIT`**: Token-free node that stages and creates atomic Git commits of modified candidate artifacts.
  - Config: `{"commit_message": str, "target_paths": list[str], "branch_name": str}`
- **`CTRL_TEST_HARNESS`**: Primitive that executes a target candidate DAG inside an isolated sandbox and scores output against assertion criteria.
  - Config: `{"candidate_topology": str, "test_suite_id": str, "max_duration_sec": int}`

### 3.2 Engine Code Contracts (`flow_engine.py` & `local_broker.py`)
```python
class ExecutionMode(Enum):
    PRODUCTION = "production"
    PAUSED_STASIS = "paused_stasis"
    IN_STATE_TEST = "in_state_test"

class CandidateSandboxManager:
    def __init__(self, candidate_id: str, base_db_path: str = "") -> None:
        self.candidate_id = candidate_id
        self.root = get_maccre_root()
        self.sandbox_dir = self.root / "02_Dynamic_Context" / "sandboxes" / candidate_id
        self.forked_db_path = self.sandbox_dir / "candidate_swarm_queue.db"

    def fork_environment(self) -> Path:
        """Forks active state via shutil.copy2 into candidate sandbox."""
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.root / "03_Agent_Ledgers" / "swarm_queue.db", self.forked_db_path)
        return self.forked_db_path

    def teardown_sandbox(self, promote: bool = False) -> None:
        """Purges sandbox or promotes changes to production master."""
        if promote:
            # Atomic commit to production
            pass
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir)
```

---

## 4. Phase 9 Timeline & Master Matrix Integration

In the Era 3 Master Roadmap, Phase 9 completes the progression:
- **Phase 6**: High-Performance Engine & TUI Refinement (Parallel Scatter, WAL Sharding, 60FPS Async UI).
- **Phase 7**: Neural Circuit Motifs & Time-Travel Replay (`flow_vector` Scrubber, `SET_GATE` Modulation).
- **Phase 8**: Zero-Trust Edge Mesh & Temporal Extrapolation (S25 NPU Mesh, TPM 2.0 Enclave, I2V Live Photo).
- **Phase 9**: In-State Live Development & Antigravity Desktop Transition Bridge (`copy2` Sandbox Forks, Antigravity Trajectory Replay as `CTRL_` DAGs, Living Git System Evolution).
