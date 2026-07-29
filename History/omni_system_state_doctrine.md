# OMNI SYSTEM-PATH TOOL: STATE & DOCTRINE
**Effective Phase:** Phase 12 Bifurcation / Phase 1 Omni Development
**Artifact Type:** Sovereign System Specification & Usage Doctrine

---

## 1. Statement of Current State
As of the current Phase 1 implementation detailed in the Omni Design Specifications, Omni exists as a **Globally Pathed, Zero-Dependency CI/CD Engine**. It operates as the ultimate gatekeeper for Python execution environments, specifically tuned to govern complex multi-agent architectures like MACCREv2 without polluting their internal dependencies.

**Current Capabilities (Phase 1 — The Gatekeeper):**
The core toolchain is live and governs all script execution. The emergent "Omni Daemon" (ambient monitoring and AST-hashing security ledgers) is greenlit but resides in future roadmap phases (Phases 2-5).

Presently, the following operations are fully active:
- **`omni qa [path] [--smart]`**: The absolute quality gate. Enforces strict Ruff linting and Pyright typing natively, resolving venv binaries directly to bypass Node.js/npm wrapper hangs.
- **`omni build [path]`**: The full compilation pipeline (Zombie Hunt → QA → Cache Purge → PyInstaller seal).
- **`omni clean [path]`**: Development hygiene. Unilaterally eradicates `.ruff_cache`, SQLite WAL/SHM artifacts, `__pycache__`, and hunts down orphaned zombie processes.
- **`omni run [path]`**: The canonical launcher. Resolves the active Python engine, hunting pre-existing zombies before executing the primary entry point (`main.py`, `app.py`, `run.py`).
- **`omni smoke [path]`**: E2E validation delegator for testing swarms.

---

## 2. System Level Doctrine: Usage of Current Omni

This doctrine dictates how engineers and autonomous agents (like Antigravity) must interact with the host system.

### I. The Sovereign Prefix Mandate
Omni is the absolute boundary between code and execution. You must **never** invoke bare Python scripts (e.g., `python main.py` or `python -m pytest`) when initiating a swarm or testing a module. 
- All executions must flow through **`omni run`**. 
- All testing/compilation must flow through **`omni qa`** and **`omni build`**. 

### II. External Isolation (Zero-Dependency Rule)
Omni is installed globally (`C:\OmniBuilder\omni.py`) and is intentionally kept entirely decoupled from project-level `requirements.txt` or `Pipfile` environments. Security and governance tooling that depends on the environment it secures is a circular failure. Omni must never be imported as a Python package inside MACCREv2 or any other project. It is invoked strictly as a CLI terminal tool.

### III. Proactive Hygiene (The Zombie Hunt)
Because AI Swarms and headless LLM clients often crash or are manually interrupted without gracefully closing WebSocket or DB connections, background Python processes inevitably hang. Omni's doctrine mandates that `omni run` and `omni clean` automatically trigger `hunt_zombies()`. This ensures that every new run begins in a mathematically pristine, zero-collision state, preventing silent SQLite deadlocks or port collisions.

### IV. Dual-Tier Security Backstop
Omni sits *in front of* Windows, not as a replacement for it. Omni acts as a JIT CI/CD Gatekeeper, preventing malformed or conceptually flawed scripts from executing. However, Windows UAC and PowerShell Execution Policies remain fully active as the definitive backstop. Omni does not circumvent OS-level elevation prompts; it relies on them.

---

## 3. The Path Forward (The Daemon Bifurcation)
While the Omni *Tool* is currently functioning as a CLI gatekeeper, the architecture is greenlit to evolve into the Omni *Daemon*. In future phases, Omni will intercept OS-level execution requests, fingerprint Abstract Syntax Trees (AST), log them against a SQLite Ledger (`omni_index.db`), and use local edge-LLMs (like `gemma3:9b`) to conduct semantic security reviews of gray-area scripts *before* allowing them to hit the Python interpreter.
