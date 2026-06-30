# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/tools/web_tools.py
================================
Sovereign web access tools for swarm agents.

Two tools exposed to the TOOL_DISPATCHER:
  - search_web(query, num_results)  — Brave Search API via Windows Vault key
  - read_url_content(url)           — Fetch and strip a URL to plain text

Zero external dependencies: urllib.request only. The `requests` library is
explicitly NOT used (omni qa sovereignty compliance).

Brave API key is read exclusively from the Windows Credential Vault under
the target name 'BRAVE_SEARCH_API_KEY', injested via:
  python maccre.py config set-key <YOUR_BRAVE_KEY>
"""
from __future__ import annotations

import html
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from maccre_core.logger import logger


# ── SSL context (reused across all calls) ────────────────────────────────────
_SSL = ssl.create_default_context()

# ── Brave Search endpoint ────────────────────────────────────────────────────
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _get_brave_key() -> str:
    """Retrieve the Brave Search API key from the Windows Credential Vault."""
    try:
        from maccre_core.orchestration.universal_vault import get_provider_credential  # noqa: PLC0415
        key = get_provider_credential("BRAVE_SEARCH_API_KEY")
        return str(key).strip() if key else ""
    except Exception:  # noqa: BLE001
        return ""


def _strip_html(raw: str) -> str:
    """Strip HTML tags and decode entities. Returns plain text."""
    # Remove script/style blocks entirely
    raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode HTML entities
    raw = html.unescape(raw)
    # Collapse whitespace
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


# ── Public Tools ─────────────────────────────────────────────────────────────


def search_web(query: str, num_results: int = 8, freshness: str = "") -> str:
    """Search the live web using the Brave Search API.

    Requires 'BRAVE_SEARCH_API_KEY' in the Windows Credential Vault.
    Returns formatted search results with titles, URLs, and snippets.
    Falls back to a clear error message if the key is absent.

    Args:
        query: The search query string.
        num_results: Number of results to return (max 20). Default 8.
        freshness: Optional time filter ('pd' for past day, 'pw' for past week, 'pm', 'py').

    Returns:
        Formatted string of search results.
    """
    api_key = _get_brave_key()
    if not api_key:
        return (
            "[WEB_SEARCH_UNAVAILABLE] BRAVE_SEARCH_API_KEY not found in vault. "
            "Use read_url_content(url) to fetch a specific known URL instead, "
            "or ask the operator to run: python maccre.py config set-key <BRAVE_KEY>"
        )

    # Coerce to int
    num_results = int(num_results)
    params = f"q={urllib.parse.quote(query)}&count={min(num_results, 20)}"
    if freshness in ("pd", "pw", "pm", "py"):
        params += f"&freshness={freshness}"
    url = f"{_BRAVE_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            # NOTE: Do NOT set Accept-Encoding: gzip — urllib.request does NOT
            # auto-decompress gzip responses, causing JSONDecodeError on raw bytes.
            "X-Subscription-Token": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=15) as resp:
            raw_bytes = resp.read()
            # Decompress gzip if the server sends it anyway (defensive fallback)
            if raw_bytes[:2] == b"\x1f\x8b":
                import gzip as _gzip  # noqa: PLC0415
                raw_bytes = _gzip.decompress(raw_bytes)
            data: dict[str, Any] = json.loads(raw_bytes.decode("utf-8", errors="replace"))

        results: list[dict[str, Any]] = data.get("web", {}).get("results", [])
        if not results:
            return f"[WEB_SEARCH] No results found for query: '{query}'"

        lines: list[str] = [f"=== WEB SEARCH: {query} ===\n"]
        for i, r in enumerate(results[:num_results], 1):
            title   = r.get("title", "N/A")
            src_url = r.get("url", "")
            snippet = r.get("description", "No snippet available.")
            lines.append(f"[{i}] {title}\n    URL: {src_url}\n    {snippet}\n")

        logger.info("[web_tools] search_web: %d results for '%s'", len(results), query)
        return "\n".join(lines)

    except urllib.error.HTTPError as exc:
        logger.warning("[web_tools] Brave HTTP %d for query '%s'", exc.code, query)
        return f"[WEB_SEARCH_ERROR] HTTP {exc.code}: {exc.reason} — query: '{query}'"
    except Exception as exc:  # noqa: BLE001
        logger.warning("[web_tools] search_web fault: %s", exc)
        return f"[WEB_SEARCH_ERROR] {exc!s}"


def read_url_content(url: str) -> str:
    """Fetch a URL and return its content as plain text (HTML stripped).

    Sovereign implementation — no external deps. Strips all HTML tags,
    script/style blocks, and decodes entities. Truncates at 12,000 chars
    to respect context window budgets.

    Args:
        url: The fully-qualified URL to fetch (must start with http/https).

    Returns:
        Plain-text content of the page (max 12,000 chars), or an error
        string if the fetch fails.
    """
    if not url.startswith(("http://", "https://")):
        return f"[URL_FAULT] Invalid URL (must start with http/https): {url}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=20) as resp:
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].strip().split(";")[0].strip()
            raw = resp.read().decode(charset, errors="replace")

        text = _strip_html(raw)
        if len(text) > 12_000:
            text = text[:12_000] + "\n\n[...TRUNCATED at 12,000 chars — use a more specific URL...]"

        logger.info("[web_tools] read_url_content: %d chars from %s", len(text), url)
        return text

    except urllib.error.HTTPError as exc:
        return f"[URL_ERROR] HTTP {exc.code} {exc.reason} — {url}"
    except urllib.error.URLError as exc:
        return f"[URL_ERROR] Connection failed: {exc.reason} — {url}"
    except Exception as exc:  # noqa: BLE001
        return f"[URL_ERROR] {exc!s} — {url}"


def cascade_search(query: str, num_results: int = 10, num_passes: int = 2) -> str:
    """Multi-index Brave search with automatic source exclusion.

    Pass 1 searches the query normally, then subsequent passes re-search with
    ``-site:<domain>`` exclusions for every domain surfaced in all previous passes.
    This surfaces diverse sources that would otherwise be buried under
    dominant domains.

    Args:
        query: The search query string.
        num_results: Number of results per pass (max 20). Default 10.
        num_passes: Number of exclusionary passes to run (max 5). Default 2.

    Returns:
        Combined results from all passes, clearly labeled.
    """
    num_results = int(num_results)
    num_passes = max(1, min(5, int(num_passes)))

    all_results = [f"=== CASCADE SEARCH: [{query}] ===\n"]
    domains: list[str] = []
    seen: set[str] = set()

    for pass_num in range(1, num_passes + 1):
        if domains:
            exclusion_suffix = " ".join(f"-site:{d}" for d in domains)
            current_query = f"{query} {exclusion_suffix}"
        else:
            current_query = query

        pass_result = search_web(current_query, num_results)
        
        # Label the pass appropriately
        pass_name = "PRIMARY INDEX" if pass_num == 1 else f"EXCLUSIONARY INDEX (PASS {pass_num})"
        all_results.append(f"=== {pass_name} ===\n{pass_result}\n")

        # Extract unique domains from this pass's URLs
        for line in pass_result.splitlines():
            stripped = line.strip()
            if stripped.startswith("URL: "):
                raw_url = stripped[5:].strip()
                try:
                    host = urllib.parse.urlparse(raw_url).netloc
                    if host and host not in seen:
                        seen.add(host)
                        domains.append(host)
                except Exception:  # noqa: BLE001
                    pass
                    
        logger.info(f"[web_tools] cascade_search pass {pass_num}: accumulated {len(domains)} total excluded domains")

    return "\n".join(all_results)
