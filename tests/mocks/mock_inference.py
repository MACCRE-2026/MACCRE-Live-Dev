# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Mock Inference Client                       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/mocks/mock_inference.py
=============================
Phase 2B — Mock InferenceClient for deterministic testing.

Implements the ``InferenceClient`` ABC with canned responses,
eliminating the need for live API keys or network during tests.
"""
from __future__ import annotations

from typing import Any, Generator

from maccre_core._net.client_interface import (
    EmbeddingResult,
    InferenceClient,
    InferenceResponse,
)


class MockInferenceResponse(InferenceResponse):
    """Canned response for testing — fully deterministic."""

    def __init__(
        self,
        text: str = "Mock response.",
        function_call: tuple[str, dict[str, Any]] | None = None,
        prompt_tokens: int = 10,
        candidate_tokens: int = 20,
    ) -> None:
        self._text = text
        self._function_call = function_call
        self._prompt_tokens = prompt_tokens
        self._candidate_tokens = candidate_tokens

    @property
    def text(self) -> str:
        return self._text

    @property
    def function_call(self) -> tuple[str, dict[str, Any]] | None:
        return self._function_call

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def candidate_tokens(self) -> int:
        return self._candidate_tokens

    @property
    def raw(self) -> dict[str, Any]:
        return {"mock": True, "text": self._text}


class MockEmbeddingResult(EmbeddingResult):
    """Returns a fixed embedding vector for testing."""

    def __init__(self, dimensions: int = 768) -> None:
        self._values = [0.01 * i for i in range(dimensions)]

    @property
    def values(self) -> list[float]:
        return self._values


class MockInferenceClient(InferenceClient):
    """Deterministic InferenceClient for unit tests.

    Usage::

        client = MockInferenceClient(responses=["Hello!", "World!"])
        resp = client.generate_content("model", [])
        assert resp.text == "Hello!"
        resp = client.generate_content("model", [])
        assert resp.text == "World!"

    Tracks all calls for assertion:
        assert client.call_count == 2
        assert client.calls[0]["model"] == "model"
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        function_responses: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._responses = responses or ["Mock LLM response."]
        self._function_responses = function_responses or []
        self._call_idx = 0
        self.calls: list[dict[str, Any]] = []
        self.call_count = 0

    def generate_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        tool_declarations: list[dict[str, Any]] | None = None,
        search_grounding: bool = False,
        disable_auto_function_calling: bool = True,
        response_schema: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        max_output_tokens: int | None = None,
        cached_content_uri: str | None = None,
    ) -> InferenceResponse:
        self.calls.append({
            "model": model,
            "contents": contents,
            "system_instruction": system_instruction,
            "temperature": temperature,
        })
        self.call_count += 1

        # Check for function call responses first
        func_call = None
        if self._call_idx < len(self._function_responses):
            func_call = self._function_responses[self._call_idx]

        text = self._responses[self._call_idx % len(self._responses)]
        self._call_idx += 1

        return MockInferenceResponse(text=text, function_call=func_call)

    def stream_generate_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        tool_declarations: list[dict[str, Any]] | None = None,
        search_grounding: bool = False,
        response_schema: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        max_output_tokens: int | None = None,
        cached_content_uri: str | None = None,
    ) -> Generator[str, None, None]:
        self.call_count += 1
        text = self._responses[self._call_idx % len(self._responses)]
        self._call_idx += 1
        # Simulate token-by-token streaming
        for word in text.split():
            yield word + " "

    def embed_content(
        self,
        model: str,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> EmbeddingResult:
        self.call_count += 1
        return MockEmbeddingResult()

    def batch_embed_contents(
        self,
        model: str,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[EmbeddingResult]:
        self.call_count += 1
        return [MockEmbeddingResult() for _ in texts]
