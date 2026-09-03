# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Shared Fixtures                             │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/conftest.py
=================
Phase 2A — Pytest fixtures and shared test configuration.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.mocks.mock_broker import MockMessageBroker
from tests.mocks.mock_inference import MockInferenceClient


@pytest.fixture()
def mock_broker() -> MockMessageBroker:
    """Fresh in-memory MockMessageBroker."""
    return MockMessageBroker()


@pytest.fixture()
def mock_client() -> MockInferenceClient:
    """Fresh MockInferenceClient with default responses."""
    return MockInferenceClient()


@pytest.fixture()
def mock_client_with_responses() -> type[MockInferenceClient]:
    """Factory fixture: create MockInferenceClient with custom responses.

    Usage::

        def test_something(mock_client_with_responses):
            client = mock_client_with_responses(["response_1", "response_2"])
    """
    return MockInferenceClient


@pytest.fixture()
def tmp_datacenter(tmp_path: Path) -> Path:
    """Create a temporary datacenter with 5-tier structure."""
    dc = tmp_path / "__DATACENTER" / "TEST_PROJECT"
    for tier in [
        "01_Raw_Source",
        "02_Dynamic_Context",
        "02_Dynamic_Context/memory_pins",
        "03_Agent_Ledgers",
        "04_Code_Artifacts",
        "05_Rendered_Media",
    ]:
        (dc / tier).mkdir(parents=True, exist_ok=True)
    return dc


@pytest.fixture()
def tmp_payload(tmp_path: Path) -> Path:
    """Create a temporary payload file for testing."""
    payload = tmp_path / "test_payload.txt"
    payload.write_text("This is a test payload for the MACCREv2 swarm.", encoding="utf-8")
    return payload


@pytest.fixture(autouse=True)
def _set_test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-applied fixture: sets env vars for test isolation."""
    monkeypatch.setenv("MACCRE_ROOT", str(tmp_path))
    monkeypatch.setenv("MACCRE_ACTIVE_PROJECT", "TEST_PROJECT")
