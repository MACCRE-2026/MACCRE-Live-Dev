# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — ABC Contract Tests                                   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_abc_contracts.py
===========================
Phase 2D — Verifies that all ABC interfaces are correctly implemented
by their concrete drivers AND mock test doubles.
"""
from __future__ import annotations

from maccre_core._net.client_interface import EmbeddingResult, InferenceClient, InferenceResponse
from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.topology_interface import TopologyProvider
from maccre_core.orchestration.tool_executor_interface import ToolDispatcher
from tests.mocks.mock_broker import MockMessageBroker
from tests.mocks.mock_inference import MockInferenceClient


# ── ABC Inheritance Tests ─────────────────────────────────────────────────────


class TestABCInheritance:
    """Verify all concrete classes properly inherit from ABCs."""

    def test_local_broker_is_message_broker(self) -> None:
        from maccre_core.orchestration.local_broker import LocalMessageBroker
        assert issubclass(LocalMessageBroker, MessageBroker)

    def test_gemini_client_is_inference_client(self) -> None:
        from maccre_core._net.gemini_client import GeminiClient
        assert issubclass(GeminiClient, InferenceClient)

    def test_gemini_response_is_inference_response(self) -> None:
        from maccre_core._net.gemini_client import GeminiResponse
        assert issubclass(GeminiResponse, InferenceResponse)

    def test_embedding_response_is_embedding_result(self) -> None:
        from maccre_core._net.gemini_client import EmbeddingResponse
        assert issubclass(EmbeddingResponse, EmbeddingResult)

    def test_topology_engine_is_topology_provider(self) -> None:
        from maccre_core.orchestration.topology_engine import TopologyEngine
        assert issubclass(TopologyEngine, TopologyProvider)

    def test_tool_executor_is_tool_dispatcher(self) -> None:
        from maccre_core.orchestration.tool_executor import ToolExecutor
        assert issubclass(ToolExecutor, ToolDispatcher)

    def test_mock_broker_is_message_broker(self) -> None:
        assert issubclass(MockMessageBroker, MessageBroker)

    def test_mock_client_is_inference_client(self) -> None:
        assert issubclass(MockInferenceClient, InferenceClient)


# ── Mock Broker Tests ─────────────────────────────────────────────────────────


class TestMockBroker:
    """Verify MockMessageBroker behavior."""

    def test_inject_and_fetch(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_task("job_1", "/payload.txt", "NODE_A")
        task = mock_broker.fetch_and_lock_task("agent_1", None)
        assert task is not None
        assert task["current_node"] == "NODE_A"
        assert task["job_id"] == "job_1"
        assert task["lock_status"] == "locked"

    def test_empty_queue_returns_none(self, mock_broker: MockMessageBroker) -> None:
        task = mock_broker.fetch_and_lock_task("agent_1", None)
        assert task is None

    def test_route_creates_successor(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_task("job_1", "/payload.txt", "NODE_A")
        task = mock_broker.fetch_and_lock_task("agent_1", None)
        assert task is not None

        mock_broker.route_task(
            row_id=task["id"],
            job_id="job_1",
            next_node_str="NODE_B|NODE_C",
            new_payload_path="/output.txt",
        )

        # Should have 2 new open tasks
        t1 = mock_broker.fetch_and_lock_task("agent_1", None)
        t2 = mock_broker.fetch_and_lock_task("agent_1", None)
        assert t1 is not None
        assert t2 is not None
        nodes = {t1["current_node"], t2["current_node"]}
        assert nodes == {"NODE_B", "NODE_C"}

    def test_route_end_creates_no_successor(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_task("job_1", "/payload.txt", "NODE_A")
        task = mock_broker.fetch_and_lock_task("agent_1", None)
        assert task is not None

        mock_broker.route_task(
            row_id=task["id"],
            job_id="job_1",
            next_node_str="END",
            new_payload_path="/output.txt",
        )

        # No successor should be created
        t = mock_broker.fetch_and_lock_task("agent_1", None)
        assert t is None

    def test_release_returns_to_open(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_task("job_1", "/payload.txt", "NODE_A")
        task = mock_broker.fetch_and_lock_task("agent_1", None)
        assert task is not None

        mock_broker.release_task(task["id"])

        # Should be fetchable again
        task2 = mock_broker.fetch_and_lock_task("agent_2", None)
        assert task2 is not None
        assert task2["current_node"] == "NODE_A"

    def test_interrupt_inject_and_consume(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_interrupt("job_1", "URGENT: Stop immediately!")
        mock_broker.inject_interrupt("job_1", "ALSO: Change course!")

        texts = mock_broker.consume_pending_interrupts("job_1")
        assert len(texts) == 2
        assert "URGENT: Stop immediately!" in texts

        # Second consume should be empty
        texts2 = mock_broker.consume_pending_interrupts("job_1")
        assert len(texts2) == 0

    def test_broadcast_records_events(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.broadcast_topology_event("NODE_STARTED", {"node": "A"})
        assert len(mock_broker._events) == 1
        assert mock_broker._events[0][0] == "NODE_STARTED"

    def test_multi_node_inject(self, mock_broker: MockMessageBroker) -> None:
        mock_broker.inject_task("job_1", "/payload.txt", "NODE_A, NODE_B, NODE_C")
        tasks = []
        while True:
            t = mock_broker.fetch_and_lock_task("agent_1", None)
            if t is None:
                break
            tasks.append(t)
        assert len(tasks) == 3
        nodes = {t["current_node"] for t in tasks}
        assert nodes == {"NODE_A", "NODE_B", "NODE_C"}


# ── Mock Inference Client Tests ───────────────────────────────────────────────


class TestMockInferenceClient:
    """Verify MockInferenceClient behavior."""

    def test_default_response(self, mock_client: MockInferenceClient) -> None:
        resp = mock_client.generate_content("gemini-2.5-flash", [])
        assert resp.text == "Mock LLM response."
        assert resp.function_call is None
        assert resp.prompt_tokens == 10
        assert resp.candidate_tokens == 20

    def test_custom_responses_cycle(self) -> None:
        client = MockInferenceClient(responses=["A", "B", "C"])
        assert client.generate_content("m", []).text == "A"
        assert client.generate_content("m", []).text == "B"
        assert client.generate_content("m", []).text == "C"
        # Wraps around
        assert client.generate_content("m", []).text == "A"

    def test_tracks_calls(self, mock_client: MockInferenceClient) -> None:
        mock_client.generate_content("model-1", [], temperature=0.5)
        mock_client.generate_content("model-2", [], temperature=1.0)
        assert mock_client.call_count == 2
        assert mock_client.calls[0]["model"] == "model-1"
        assert mock_client.calls[1]["temperature"] == 1.0

    def test_streaming(self, mock_client: MockInferenceClient) -> None:
        tokens = list(mock_client.stream_generate_content("m", []))
        assert len(tokens) > 0
        full = "".join(tokens).strip()
        assert full == "Mock LLM response."

    def test_embedding(self, mock_client: MockInferenceClient) -> None:
        result = mock_client.embed_content("text-embedding-004", "hello")
        assert len(result.values) == 768
        assert isinstance(result.values[0], float)

    def test_batch_embedding(self, mock_client: MockInferenceClient) -> None:
        results = mock_client.batch_embed_contents("m", ["a", "b", "c"])
        assert len(results) == 3

    def test_function_call_response(self) -> None:
        client = MockInferenceClient(
            responses=["I'll call a tool"],
            function_responses=[("write_file", {"path": "/test.txt", "content": "hello"})],
        )
        resp = client.generate_content("m", [])
        assert resp.function_call is not None
        assert resp.function_call[0] == "write_file"
        assert resp.function_call[1]["path"] == "/test.txt"
