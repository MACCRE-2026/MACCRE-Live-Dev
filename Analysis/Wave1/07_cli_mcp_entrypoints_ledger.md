# Granular Functional Ledger: Top-Level Entrypoints & CLI Tools
**Analysis Level**: Line-by-Line / Block-by-Block Functional Decomposition
**Module Scope**: `maccre.py` (63KB), `maccre_mcp.py` (35KB), `setup_mcp.py` (4.2KB), `run.py` (108B)
**Architecture Standard**: MACCREv2 Engineering Doctrine (Law Rev 19.0)

---

## Executive Summary & Architectural Overview

The top-level entrypoints of MACCREv2 form a multi-modal control plane designed to support human interactive terminal operators, automated swarm scripts, programmatic MCP host integration (e.g. Antigravity, Nexus-Gemma), and terminal visualizers. 

The four entrypoints fulfill four orthogonal operational personas:
1. **`run.py`**: Minimal bootstrap launcher for the Textual TUI interface (`NexusPlex`).
2. **`setup_mcp.py`**: Zero-dependency machine auto-configurator that resolves local virtual environments and outputs standard `mcp_config.json` for Antigravity integration.
3. **`maccre_mcp.py`**: The stdio Model Context Protocol (MCP) server delivering 27 exposed agentic tools structured into 8 functional groups with strict stdio JSON-RPC pipe protection.
4. **`maccre.py`**: The master CLI engine providing direct swarm ignition, workbook processing, topology management, session PID hygiene, forensic auditing, and memory canonization.

---

## 1. Analysis of `run.py`
Lightweight wrapper launcher for `maccre_tui.nexus_plex.NexusPlex`.

## 2. Analysis of `setup_mcp.py`
Machine-agnostic auto-setup script that detects project root, virtual environment executable, and system-specific Antigravity application paths to generate `mcp_config.json`.

## 3. Analysis of `maccre_mcp.py`
Primary MCP stdio server powered by `FastMCP`. Exposes 27 agentic tools across 8 functional groups (System, Swarm/Pattern, Knowledge/RAG, Storage, Render, Telemetry, FinOps, Admin).

## 4. Analysis of `maccre.py`
Master CLI engine & headless orchestration launcher. Manages task injection, workbook processing, topology management, session lifecycle, PID registry hygiene, and forensic debugging.
