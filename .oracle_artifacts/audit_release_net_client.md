# Net & Client Subsystem Audit Report: B:\MACCRE_Release

**Auditor:** NetAndClient_Oracle
**Date:** 2026-07-25
**Scope:** `setup_mcp.py`, `maccre_core/_net/`, `gemini_client.py`, `model_sentinel.py`, `model_registry.py`, `omnidaemon.py`, `ooxml.py`, `requirements-*.txt`.

## Summary Matrix
- **Zero-SDK REST urllib Compliance**: 95% (PASSED — 1 documented Sovereignty Exception for Live API WebSocket)
- **RAM Key Zeroing Protocol**: 100% (PASSED — `wipe_string()` via `ctypes.memset` in `finally:` blocks)
- **ModelSentinel Health Monitoring**: 100% (PASSED — background probe, sliding window error rate, EMA latency, 13 surface tiers)
- **MCP Activation**: 90% (PASSED — stdio JSON-RPC pipe isolation verified; 1 cross-platform venv path fix recommended)
- **Dependencies**: 85% (WARNING — `requests` in `requirements-sovereign.txt` is unused and should be removed)

## Detailed Findings

1. **gemini_client.py**: Fully zero-dependency HTTP client implementing full Generative Language API surface using `urllib.request`. All 9 API request methods wrap key access in `try...finally:` with `wipe_string()`.
2. **live_client.py**: Imports `google.genai` for Live API WebSocket streaming (`bidiGenerateContent`). Explicit Sovereignty Exception documented.
3. **model_sentinel.py & model_registry.py**: Thread-safe active background probe daemon, diff change detection, 13 capability surface classifications, and failover chains.
4. **setup_mcp.py**: Correctly materializes `mcp_config.json` with `MACCRE_ROOT`. Requires cross-platform fix for `.venv/bin/python` vs `.venv/Scripts/python.exe`.
5. **maccre_mcp.py**: Stdio logging redirected to stderr to protect JSON-RPC protocol framing pipe.

## Recommendations
1. Update `setup_mcp.py` to resolve `VENV_PYTHON` based on `platform.system()`.
2. Remove `requests>=2.31.0` from `requirements-sovereign.txt`.
