# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/patterns/brief_packet.py
=====================================
BriefPacket — the structured context packet delivered at HUMAN_GATE nodes.

This is the "instantiation context packet" designed from Antigravity's
perspective.  It contains exactly what's needed to make an informed decision
at the start of a new session or after a swarm pattern completes — without
having to read raw logs or ledger files.

Key principle: compression fidelity > completeness.  A good brief is not
a log dump.  It is: what changed, what it means, the decision point,
the recommended path, and its cost.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class PathOption:
    """One implementation path option produced by a simulation swarm fork."""

    label: str
    agent: str                          # Fork node_id that produced this option
    summary: str
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.5             # 0.0–1.0 rated by the fork agent
    artifacts: list[str] = field(default_factory=list)  # ledger file paths


@dataclass
class DecisionSurface:
    """The synthesized decision surface — the core of every BriefPacket."""

    question: str
    options: list[PathOption] = field(default_factory=list)
    synthesizer_recommendation: str = ""
    next_action_options: list[str] = field(default_factory=list)


@dataclass
class SessionContext:
    """Current project state — always included in session_brief patterns."""

    project: str = ""
    git_head: str = ""
    git_recent_commits: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    cost_7d_usd: float = 0.0
    cost_session_usd: float = 0.0
    sentinel_health: dict[str, int] = field(default_factory=dict)
    active_jobs: list[str] = field(default_factory=list)


@dataclass
class BriefPacket:
    """Structured context packet delivered at HUMAN_GATE nodes.

    Designed from Antigravity's perspective as the stateless process being
    served.  Compact, structured, and directly actionable.
    """

    pattern: str
    job_id: str
    fired_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cost_usd: float = 0.0
    decision_surface: DecisionSurface | None = None
    session_context: SessionContext | None = None
    raw_synthesis: str = ""             # Full synthesizer ledger (fallback)
    pattern_artifacts: list[str] = field(default_factory=list)
    error: str = ""                     # Set if pattern faulted before gate

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "BriefPacket":
        """Deserialize from JSON string. Returns an error packet on parse failure."""
        try:
            data: dict = json.loads(text)
            # Reconstruct nested dataclasses from raw dicts
            if data.get("decision_surface"):
                ds = data["decision_surface"]
                options = [PathOption(**opt) for opt in ds.get("options", [])]
                data["decision_surface"] = DecisionSurface(
                    question=ds.get("question", ""),
                    options=options,
                    synthesizer_recommendation=ds.get("synthesizer_recommendation", ""),
                    next_action_options=ds.get("next_action_options", []),
                )
            if data.get("session_context"):
                sc = data["session_context"]
                data["session_context"] = SessionContext(**sc)
            return cls(**data)
        except Exception as exc:
            return cls(
                pattern="unknown",
                job_id="unknown",
                error=f"BriefPacket parse failure: {exc}",
                raw_synthesis=text[:2000],
            )

    # ── Factory Helpers ────────────────────────────────────────────────────────

    @classmethod
    def build_session_brief(
        cls,
        job_id: str,
        project: str,
        git_summary: str,
        cost_summary: str,
        telemetry_summary: str,
        cost_usd: float = 0.0,
        sentinel_health: dict[str, int] | None = None,
    ) -> "BriefPacket":
        """Convenience factory for synchronous session_brief output."""
        import re  # noqa: PLC0415

        head_match = re.search(r"([0-9a-f]{7,40})", git_summary)
        git_head = head_match.group(1) if head_match else "unknown"

        commits = [ln.strip() for ln in git_summary.strip().splitlines() if ln.strip()]

        cost_match = re.search(r"\$([\d.]+)", cost_summary)
        cost_7d = float(cost_match.group(1)) if cost_match else 0.0

        ctx = SessionContext(
            project=project,
            git_head=git_head,
            git_recent_commits=commits[:5],
            cost_7d_usd=cost_7d,
            sentinel_health=sentinel_health or {},
        )

        surface = DecisionSurface(
            question="What is the current state and recommended next action?",
            synthesizer_recommendation=(
                f"GIT: {git_summary[:200]}\n\n"
                f"COST: {cost_summary}\n\n"
                f"TELEMETRY: {telemetry_summary[:200]}"
            ),
            next_action_options=[
                "continue_current_task",
                "run_simulation_swarm",
                "run_checkpoint_sweep",
                "start_new_task",
            ],
        )

        return cls(
            pattern="session_brief",
            job_id=job_id,
            cost_usd=cost_usd,
            decision_surface=surface,
            session_context=ctx,
        )

    # ── Display Formatting ─────────────────────────────────────────────────────

    def format_for_display(self) -> str:
        """Format BriefPacket as human + AI readable markdown."""
        lines: list[str] = [
            f"# 📋 MACCRE Brief — `{self.pattern}`",
            f"**Job:** `{self.job_id}` | **Cost:** `${self.cost_usd:.4f}`",
            f"**Completed:** {self.completed_at}",
            "",
        ]

        if self.error:
            lines += [f"⚠️ **Pattern Error:** {self.error}", ""]

        if self.session_context:
            ctx = self.session_context
            lines += [
                "## 🧭 Session Context",
                f"- **Project:** `{ctx.project}`",
                f"- **Git HEAD:** `{ctx.git_head}`",
                f"- **Cost (7d):** `${ctx.cost_7d_usd:.4f}`",
                f"- **Sentinel:** {ctx.sentinel_health}",
            ]
            if ctx.git_recent_commits:
                lines.append("- **Recent commits:**")
                for c in ctx.git_recent_commits[:3]:
                    lines.append(f"  - `{c}`")
            lines.append("")

        if self.decision_surface:
            ds = self.decision_surface
            lines += [
                "## 🎯 Decision Surface",
                f"**Question:** {ds.question}",
                "",
            ]
            for i, opt in enumerate(ds.options):
                lines += [
                    f"### Option {i + 1}: {opt.label}",
                    f"**Agent:** `{opt.agent}` | **Confidence:** {opt.confidence:.0%}",
                    opt.summary,
                    f"**Risks:** {', '.join(opt.risks) or 'None identified'}",
                    "",
                ]
            if ds.synthesizer_recommendation:
                lines += [
                    "### 🤖 Synthesizer Recommendation",
                    ds.synthesizer_recommendation,
                    "",
                ]
            if ds.next_action_options:
                options_str = " | ".join(f"`{a}`" for a in ds.next_action_options)
                lines += [f"**Available decisions:** {options_str}", ""]

        if self.raw_synthesis and not self.decision_surface:
            lines += ["## 📄 Synthesis", self.raw_synthesis[:1500], ""]

        return "\n".join(lines)


__all__ = ["BriefPacket", "DecisionSurface", "PathOption", "SessionContext"]
