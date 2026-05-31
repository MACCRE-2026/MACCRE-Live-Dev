# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/tools/hybrid_search.py
=====================================
True Hybrid Search — simultaneous Live Web + Local Vector DB.

Executes an external Brave Search query while concurrently querying the active
project's SovereignPinStore vector DB. Returns a unified context block.

Sovereign implementation: uses urllib (web_tools.py) — zero requests dependency.
Brave API key lives in Windows Credential Vault as 'BRAVE_SEARCH_API_KEY'.
"""
from __future__ import annotations

import concurrent.futures
from typing import Any


def _query_local_sovereign(query: str, collection_name: str = "swarm_memory", n_results: int = 5) -> str:
    """Query the active project's SovereignPinStore for semantic matches.

    Args:
        query: Natural language search query.
        collection_name: ChromaDB/SQLite collection to search. Default 'swarm_memory'.
        n_results: Number of results to return. Default 5.

    Returns:
        Formatted string of matching document snippets, or a fault message.
    """
    import os as _os  # noqa: PLC0415
    try:
        from maccre_core.memory import get_knowledge_store  # noqa: PLC0415
        from maccre_core.tools.rag_tools import get_gemini_embedding  # noqa: PLC0415

        env_project = _os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        store = get_knowledge_store(env_project)

        if collection_name not in store.list_collections():
            return f"[LOCAL_SEARCH] Collection '{collection_name}' not found in project '{env_project}'."

        vector = get_gemini_embedding(query, task_type="RETRIEVAL_QUERY")
        pins = store.query(collection_name, vector, n=n_results)

        if not pins:
            return "[LOCAL_SEARCH] No relevant chunks found."
        return "\n---\n".join(pin.text for pin in pins)
    except Exception as exc:  # noqa: BLE001
        return f"[LOCAL_STORE_FAULT] {exc!s}"


def execute_hybrid_synthesis(
    query: str,
    collection_name: str = "swarm_memory",
    extra_queries: str = "",
) -> str:
    """Run simultaneous live web search + local vector DB query and merge results.

    Fires a Brave Search API call and a local SovereignPinStore semantic query
    concurrently, then returns a unified context block with both result sets.
    If BRAVE_SEARCH_API_KEY is absent from the vault, the web search degrades
    gracefully and only local memory results are returned.

    This is the primary research tool for OSINT-style agents — use it as the
    first call for any factual investigation before calling read_url_content
    to deep-read specific source URLs.

    When extra_queries is provided (pipe-separated search phrases), additional
    Brave searches are fired concurrently alongside the primary query.  Use
    this from OSINT_BRAVE to drill into specific domains surfaced by OSINT_GOOGLE:
    e.g. extra_queries="site:aljazeera.com iran ceasefire|site:bbc.com hezbollah"

    Args:
        query: The primary research question or search phrase.
        collection_name: Local vector collection to query. Default 'swarm_memory'.
        extra_queries: Optional pipe-separated additional Brave search terms.

    Returns:
        Unified string block containing LOCAL MEMORY results and LIVE WEB results
        (primary + any extra queries), or graceful error messages if unavailable.
    """
    from maccre_core.tools.web_tools import search_web  # noqa: PLC0415

    # Build the list of web queries: primary + any extras
    all_queries: list[str] = [query]
    if extra_queries.strip():
        all_queries.extend(q.strip() for q in extra_queries.split("|") if q.strip())

    web_results: list[str] = []
    local_result: str = "[LOCAL_SEARCH] Pending..."

    max_workers = 1 + len(all_queries)  # local + one per web query
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_local = executor.submit(_query_local_sovereign, query, collection_name)
        future_webs  = [executor.submit(search_web, q, 15) for q in all_queries]
        local_result = future_local.result(timeout=30)
        for q, fw in zip(all_queries, future_webs):
            try:
                web_results.append(f"--- Query: [{q}] ---\n{fw.result(timeout=30)}")
            except Exception as exc:  # noqa: BLE001
                web_results.append(f"--- Query: [{q}] ---\n[WEB_FAULT] {exc!s}")

    merged_web = "\n\n".join(web_results)
    return (
        f"=== HYBRID SEARCH: [{query}] ===\n\n"
        f"=== LOCAL MEMORY ===\n{local_result}\n\n"
        f"=== LIVE WEB GROUNDING ===\n{merged_web}\n"
    )


def get_hybrid_tools() -> list[Any]:
    """Return the hybrid search tool list (legacy hook — kept for compatibility).

    Returns:
        List containing the execute_hybrid_synthesis callable.
    """
    return [execute_hybrid_synthesis]
