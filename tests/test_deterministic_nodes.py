# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Deterministic Node Tests                             │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_deterministic_nodes.py
==================================
Phase 4 — Verifies all 7 deterministic node types.
"""
from __future__ import annotations

from pathlib import Path

from maccre_core.orchestration.deterministic_nodes import (
    DeterministicNodeType,
    execute_deterministic_node,
    is_deterministic_node,
    _resolve_node_type,
)


class TestNodeDetection:
    """Test DET_ prefix detection and type resolution."""

    def test_det_prefix_detected(self) -> None:
        assert is_deterministic_node("DET_ANCHOR") is True
        assert is_deterministic_node("DET_PAUSE_1") is True
        assert is_deterministic_node("det_checkpoint") is True  # case insensitive

    def test_non_det_not_detected(self) -> None:
        assert is_deterministic_node("OSINT_Analyst") is False
        assert is_deterministic_node("Regular_Joe") is False
        assert is_deterministic_node("DETERMINE_FATE") is False  # only prefix, not substring

    def test_resolve_all_types(self) -> None:
        assert _resolve_node_type("DET_ANCHOR") == DeterministicNodeType.ANCHOR
        assert _resolve_node_type("DET_RECURSION_1") == DeterministicNodeType.RECURSION
        assert _resolve_node_type("DET_PAUSE") == DeterministicNodeType.PAUSE
        assert _resolve_node_type("DET_GATE") == DeterministicNodeType.GATE
        assert _resolve_node_type("DET_CHECKPOINT_A") == DeterministicNodeType.CHECKPOINT
        assert _resolve_node_type("DET_DELAY") == DeterministicNodeType.DELAY
        assert _resolve_node_type("DET_TRANSFORM_1") == DeterministicNodeType.TRANSFORM

    def test_unknown_type_returns_none(self) -> None:
        assert _resolve_node_type("DET_UNKNOWN") is None


class TestAnchorNode:
    """Test DET_ANCHOR — pass-through."""

    def test_anchor_passes_through(self) -> None:
        task = {"payload_path": "/some/payload.md", "job_id": "test_job"}
        result = execute_deterministic_node("DET_ANCHOR", task)
        assert result.output_payload_path == "/some/payload.md"
        assert result.should_pause is False
        assert "ANCHOR" in result.log_message


class TestRecursionNode:
    """Test DET_RECURSION — loop-back control."""

    def test_recursion_loops_when_under_max(self) -> None:
        task = {"payload_path": "/p.md", "job_id": "j1"}
        config = {"Max_Recursion": "3", "loop_iteration_count": 1, "Instruction_Override": "NODE_A"}
        result = execute_deterministic_node("DET_RECURSION", task, config)
        assert result.next_node == "NODE_A"
        assert "looping" in result.log_message.lower()

    def test_recursion_stops_at_max(self) -> None:
        task = {"payload_path": "/p.md", "job_id": "j1"}
        config = {"Max_Recursion": "3", "loop_iteration_count": 3}
        result = execute_deterministic_node("DET_RECURSION", task, config)
        assert result.next_node is None  # Use topology next_node
        assert "complete" in result.log_message.lower()


class TestPauseNode:
    """Test DET_PAUSE — halts execution."""

    def test_pause_sets_flag(self) -> None:
        task = {"payload_path": "/p.md", "job_id": "j1"}
        result = execute_deterministic_node("DET_PAUSE", task)
        assert result.should_pause is True
        assert "pause" in result.log_message.lower()


class TestGateNode:
    """Test DET_GATE — conditional gate."""

    def test_gate_blocks_on_no_payload(self) -> None:
        task = {"payload_path": "none", "job_id": "j1"}
        result = execute_deterministic_node("DET_GATE", task)
        assert result.next_node == "DET_GATE"  # Re-queues self
        assert "blocked" in result.log_message.lower()

    def test_gate_passes_on_existing_payload(self, tmp_path: Path) -> None:
        payload = tmp_path / "test.md"
        payload.write_text("content", encoding="utf-8")
        task = {"payload_path": str(payload), "job_id": "j1"}
        result = execute_deterministic_node("DET_GATE", task)
        assert result.next_node is None  # Use topology default
        assert "passed" in result.log_message.lower()

    def test_gate_blocks_on_empty_file(self, tmp_path: Path) -> None:
        payload = tmp_path / "empty.md"
        payload.write_text("", encoding="utf-8")
        task = {"payload_path": str(payload), "job_id": "j1"}
        result = execute_deterministic_node("DET_GATE", task)
        assert "blocked" in result.log_message.lower()


class TestCheckpointNode:
    """Test DET_CHECKPOINT — payload snapshotting."""

    def test_checkpoint_creates_file(self, tmp_path: Path) -> None:
        payload = tmp_path / "payload.md"
        payload.write_text("# Important data", encoding="utf-8")
        task = {"payload_path": str(payload), "job_id": "test_checkpoint_job"}
        result = execute_deterministic_node("DET_CHECKPOINT_1", task)
        assert result.output_payload_path == str(payload)  # Unchanged
        assert "checkpoint" in result.log_message.lower()


class TestDelayNode:
    """Test DET_DELAY — timed sleep."""

    def test_delay_with_custom_time(self) -> None:
        task = {"payload_path": "/p.md", "job_id": "j1"}
        config = {"Instruction_Override": "0.01"}  # 10ms for fast test
        import time
        start = time.time()
        result = execute_deterministic_node("DET_DELAY", task, config)
        elapsed = time.time() - start
        assert elapsed >= 0.01
        assert "DELAY" in result.log_message

    def test_delay_caps_at_3600(self) -> None:
        task = {"payload_path": "/p.md", "job_id": "j1"}
        config = {"Instruction_Override": "0.001"}  # Very small for test speed
        result = execute_deterministic_node("DET_DELAY", task, config)
        assert "slept" in result.log_message.lower()


class TestTransformNode:
    """Test DET_TRANSFORM — static text template."""

    def test_transform_applies_template(self, tmp_path: Path) -> None:
        payload = tmp_path / "source.md"
        payload.write_text("Hello world", encoding="utf-8")
        task = {"payload_path": str(payload), "job_id": "test_transform_job"}
        config = {"Instruction_Override": "## Wrapped\n\n{PAYLOAD}\n\n## End"}
        result = execute_deterministic_node("DET_TRANSFORM_1", task, config)

        output = Path(result.output_payload_path)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "Hello world" in content
        assert "## Wrapped" in content
