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
maccre_core/tools/search_tools.py
====================================
Strangler Fig abstraction for web search in the MACCRE Tool Registry.

Architecture:
  SearchProvider (ABC)
      └── BraveSearchAdapter   ← wraps maccre_keys.brave_search()
      └── (future: GoogleSearchAdapter, LocalIndexAdapter …)

The ``run_search()`` dispatcher takes any ``SearchProvider`` so the router
can swap backends (e.g. Gemma 3 on NUC fleet using a local embeddings index)
without changing calling code.

Gemini Function Calling schema contract:
  - Explicit Python type hints throughout.
  - Google-style docstrings (Args / Returns / Raises).
"""

import abc
from typing import Any, Dict, List, Optional
import os
import requests


def brave_search(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Native Brave Search API call utilizing OS-level secrets."""
    api_key = os.environ.get("SEARCH_API_KEY")
    if not api_key: 
        raise RuntimeError("SEARCH_API_KEY missing from environment.")
        
    headers = {
        "Accept": "application/json", 
        "X-Subscription-Token": api_key
    }
    
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers=headers,
        timeout=10
    )
    response.raise_for_status()
    
    return response.json().get("web", {}).get("results", [])


# ── Abstract Base Class ──────────────────────────────────────────────────────

class SearchProvider(abc.ABC):
    """Abstract interface for all web / document search backends.

    Any new search integration (Google Custom Search, local FAISS index, etc.)
    must subclass ``SearchProvider`` and implement :meth:`search`.  This
    enforces the Strangler Fig contract: business logic calls ``run_search()``
    through this interface and is immune to backend swaps.
    """

    @abc.abstractmethod
    def search(self, query: str, count: int = 5) -> dict[str, Any]:
        """Execute a search query and return the raw provider response.

        Args:
            query: The search query string.
            count: Maximum number of results to return (1–20 for Brave).

        Returns:
            A dict whose structure matches the provider's native JSON schema.
            Callers should not rely on specific keys; use a normaliser instead.

        Raises:
            EnvironmentError: If the required API key is not configured.
            RuntimeError: If the provider returns an unexpected error.
        """


# ── Concrete Adapters ────────────────────────────────────────────────────────

class BraveSearchAdapter(SearchProvider):
    """Brave Search implementation of ``SearchProvider``.

    Routes through ``maccre_keys.brave_search()`` which reads the
    ``BRAVE_SEARCH_API_KEY`` from the MACCRE global ``.env`` vault.

    Usage:
        adapter = BraveSearchAdapter()
        results = adapter.search("solar desalination", count=5)
    """

    def search(self, query: str, count: int = 5) -> dict[str, Any]:
        """Run a Brave web search and return the raw JSON response.

        Args:
            query: The search query string.
            count: Number of results to request (1–20).

        Returns:
            The Brave Search API JSON payload as a Python dict.

        Raises:
            EnvironmentError: If ``BRAVE_SEARCH_API_KEY`` is not set in the
                MACCRE ``.env`` file.
        """
        api_key = os.environ.get("SEARCH_API_KEY")
        if not api_key:
            raise RuntimeError("SEARCH_API_KEY missing from environment.")
        return {"results": brave_search(query, count=count)}


# ── Dispatcher ───────────────────────────────────────────────────────────────

def run_search(
    query: str,
    provider: Optional[SearchProvider] = None,
    count: int = 5,
) -> dict[str, Any]:
    """Dispatch a search query through the given provider.

    If no provider is given, a :class:`BraveSearchAdapter` is instantiated
    automatically, making this a convenient one-call interface for the most
    common case.

    Args:
        query: The search query string.
        provider: A ``SearchProvider`` instance to use.  Defaults to
            ``BraveSearchAdapter()`` when ``None``.
        count: Number of results to return.

    Returns:
        The raw search response dict from the chosen provider.

    Raises:
        EnvironmentError: Propagated from the provider if auth fails.
    """
    if provider is None:
        provider = BraveSearchAdapter()
    return provider.search(query, count=count)
