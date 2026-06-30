# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/tools/swarm_watcher.py
====================================
MACCRE Swarm Watcher — live ANSI terminal dashboard for active swarm sessions.

Layout (full-width, ANSI redrawn each poll cycle):

  ◈ MACCRE SWARM WATCHER  │  job: <id>  │  project: <name>  │  elapsed: HH:MM:SS
  ─────────────────────────────────────────────────────────────────────────────────
  ◈ THOUGHTS & ERRORS              │  ◈ RESPONSES & EVENTS
  ─────────────────────────────────┼─────────────────────────────────────────────
  [HH:MM:SS] [NODE] thought text   │  [HH:MM:SS] [NODE] NODE_ROUTED → NEXT
  ...                              │  ...
  ─────────────────────────────────────────────────────────────────────────────────
  TOPOLOGY:  ✓NODE1 ──► ▶NODE2 ──► ○NODE3
   Node 1/3  │  $0.0023 spent  │  status: pending  │  [Q] detach  [↑↓ ←→] scroll

Data sources (all read-only WAL):
  thoughts.db     → left panel  (session_id = job_id)
  system_logs.db  → right panel (session_id = job_id)
  maccre_queue.db → status bar  (job_id column)
  topology.csv    → topology order for progress display
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# ── VT100/ANSI on Windows ─────────────────────────────────────────────────────
if sys.platform == "win32":
    import ctypes
    _k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    _k32.SetConsoleMode(_k32.GetStdHandle(-11), 7)

# ── ANSI primitives ───────────────────────────────────────────────────────────
_E = "\033["


def _cls() -> str:
    return f"{_E}2J{_E}H"


def _bold(s: str) -> str:
    return f"{_E}1m{s}{_E}0m"


def _cyan(s: str) -> str:
    return f"{_E}96m{s}{_E}0m"


def _green(s: str) -> str:
    return f"{_E}92m{s}{_E}0m"


def _red(s: str) -> str:
    return f"{_E}91m{s}{_E}0m"


def _yellow(s: str) -> str:
    return f"{_E}93m{s}{_E}0m"


def _dim(s: str) -> str:
    return f"{_E}2m{s}{_E}0m"


def _strip_ansi(s: str) -> int:
    """Approximate visible length ignoring ANSI escapes."""
    import re
    return len(re.sub(r"\033\[[^m]*m", "", s))


def _trunc(s: str, width: int, padded: bool = True) -> str:
    vis = _strip_ansi(s)
    if vis > width:
        # Naive truncation — strip the raw string
        raw = s[:width - 1] + "…"
        return raw
    return s + (" " * (width - vis)) if padded else s


# ── Root / path resolution ────────────────────────────────────────────────────

def _find_root() -> Path:
    env = os.environ.get("MACCRE_ROOT", "")
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for _ in range(10):
        if (p / "maccre.py").exists():
            return p
        p = p.parent
    return Path.cwd()


def _telemetry(name: str) -> Path:
    return _find_root() / "__DATACENTER" / "telemetry" / name


def _queue_db() -> Path:
    return _find_root() / "__DATACENTER" / "maccre_queue.db"


# ── DB helpers ────────────────────────────────────────────────────────────────

@contextmanager
def _ro(db: Path) -> Generator[sqlite3.Connection | None, None, None]:
    """Read-only WAL-safe connection; yields None if file absent."""
    if not db.exists():
        yield None
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _fetch_thoughts(job_id: str, project: str, since: int) -> list[tuple[int, str, str, str]]:
    job_dir = _find_root() / "__DATACENTER" / project / "03_Agent_Ledgers" / f"job_{job_id}"
    if not job_dir.exists():
        return []

    import re
    from datetime import datetime, timezone
    _SCRATCHPAD_PAT = re.compile(r"<scratchpad(?:.*?timestamp=\"([^\"]+)\")?[^>]*>(.*?)</scratchpad>", re.DOTALL)
    
    thoughts = []
    for md_file in job_dir.glob("thoughts_and_tools_*.md"):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
            # Extract agent name from filename: thoughts_and_tools_{agent}_{row_id}.md
            parts = md_file.stem.split("_")
            agent = parts[3] if len(parts) > 3 else "?"
            
            for match in _SCRATCHPAD_PAT.finditer(content):
                ts_val = match.group(1)
                thought_content = match.group(2).strip()
                if ts_val:
                    try:
                        dt = datetime.fromisoformat(ts_val)
                        ts_str = dt.strftime("%H:%M:%S")
                        sort_key = dt.timestamp()
                    except Exception:
                        ts_str = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc).strftime("%H:%M:%S")
                        sort_key = md_file.stat().st_mtime
                else:
                    ts_str = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc).strftime("%H:%M:%S")
                    sort_key = md_file.stat().st_mtime
                    
                thoughts.append((thought_content, agent, ts_str, sort_key))
        except Exception:
            continue
            
    # Sort chronologically
    thoughts.sort(key=lambda x: x[3])
    
    results = []
    for idx, (thought, agent, ts_str, _) in enumerate(thoughts, start=1):
        if idx > since:
            results.append((idx, ts_str, agent, thought[:200]))
            
    return results


def _fetch_events(job_id: str, project: str, since: int) -> list[tuple[int, str, str, str]]:
    sys_db = _find_root() / "__DATACENTER" / project / "telemetry" / "system_logs.db"
    with _ro(sys_db) as conn:
        if conn is None:
            return []
        try:
            rows = conn.execute(
                "SELECT id, timestamp, source_node, action_type, payload "
                "FROM system_logs WHERE session_id=? AND id>? ORDER BY id",
                (job_id, since),
            ).fetchall()
            result: list[tuple[int, str, str, str]] = []
            for r in rows:
                payload = r["payload"] or ""
                try:
                    pd = json.loads(payload)
                    short = str(pd.get("tool") or pd.get("next_node") or pd.get("job_id") or payload[:80])
                except Exception:
                    short = payload[:80]
                msg = f"{r['action_type']}: {short}"
                result.append((r["id"], (r["timestamp"] or "")[:8], r["source_node"] or "?", msg))
            return result
        except Exception:
            return []


def _queue_status(job_id: str) -> tuple[str, str, float]:
    with _ro(_queue_db()) as conn:
        if conn is None:
            return ("—", "waiting", 0.0)
        try:
            row = conn.execute(
                "SELECT current_node, lock_status, actual_cost "
                "FROM task_queue WHERE job_id=? ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if row:
                return (str(row["current_node"] or "—"), str(row["lock_status"] or "queued"), float(row["actual_cost"] or 0.0))
        except Exception:
            pass
    return ("—", "waiting", 0.0)


def _load_topology(project: str) -> list[str]:
    root = _find_root()
    for candidate in [
        root / "__DATACENTER" / project / "02_Dynamic_Context" / "topology.csv",
        root / "__DATACENTER" / project / "topology.csv",
    ]:
        if candidate.exists():
            try:
                with open(candidate, newline="", encoding="utf-8") as f:
                    return [r.get("Node_ID", r.get("node_id", ""))
                            for r in csv.DictReader(f)
                            if r.get("Node_ID") or r.get("node_id")]
            except Exception:
                pass
    return []


# ── Renderer ──────────────────────────────────────────────────────────────────

def _render_frame(
    *,
    job_id: str,
    project: str,
    start_ts: float,
    current_node: str,
    lock_status: str,
    actual_cost: float,
    topology: list[str],
    done_nodes: set[str],
    t_buf: deque[str],
    e_buf: deque[str],
    t_scroll: int,
    e_scroll: int,
) -> str:
    ts_obj = shutil.get_terminal_size((120, 40))
    W = ts_obj.columns
    ROWS = ts_obj.lines

    half = (W - 3) // 2
    elapsed = int(time.time() - start_ts)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60

    out: list[str] = [_cls()]

    # Header
    hdr = f" ◈ MACCRE SWARM WATCHER  │  job: {job_id}  │  project: {project}  │  elapsed: {h:02d}:{m:02d}:{s:02d} "
    out.append(_bold(_cyan(_trunc(hdr, W))) + "\n")
    out.append(_dim("─" * W) + "\n")

    # Panel labels
    lhdr = _bold(_yellow(" ◈ THOUGHTS & ERRORS"))
    rhdr = _bold(_cyan(" ◈ RESPONSES & EVENTS"))
    out.append(_trunc(lhdr, half) + " │ " + _trunc(rhdr, half) + "\n")
    out.append(_dim("─" * half + "─┼─" + "─" * half) + "\n")

    # Content rows
    panel_rows = max(ROWS - 8, 4)
    t_lines = list(t_buf)
    e_lines = list(e_buf)

    def _view(buf: list[str], scroll: int) -> list[str]:
        end = len(buf) - scroll if scroll else None
        start = max(0, len(buf) - panel_rows - scroll)
        sliced = buf[start:end]
        # pad
        while len(sliced) < panel_rows:
            sliced.append("")
        return sliced

    t_view = _view(t_lines, t_scroll)
    e_view = _view(e_lines, e_scroll)

    for i in range(panel_rows):
        tl_raw = t_view[i] if i < len(t_view) else ""
        el_raw = e_view[i] if i < len(e_view) else ""

        # Colour thoughts
        if "[ERROR]" in tl_raw or "FAULT" in tl_raw or "error" in tl_raw.lower():
            tl = _trunc(_red(tl_raw), half)
        elif tl_raw.strip():
            tl = _trunc(_dim(tl_raw), half)
        else:
            tl = " " * half

        # Colour events
        if "NODE_ROUTED" in el_raw:
            el = _trunc(_green(el_raw), half)
        elif "TOOL_FIRED" in el_raw:
            el = _trunc(_cyan(el_raw), half)
        elif "INFERENCE_COST" in el_raw:
            el = _trunc(_dim(el_raw), half)
        elif "ERROR" in el_raw or "FAULT" in el_raw:
            el = _trunc(_red(el_raw), half)
        elif el_raw.strip():
            el = _trunc(el_raw, half)
        else:
            el = " " * half

        out.append(f" {tl} │ {el}\n")

    # Divider
    out.append(_dim("─" * W) + "\n")

    # Topology progress
    topo_str = " TOPOLOGY:  "
    if topology:
        segments: list[str] = []
        for nid in topology:
            if nid in done_nodes:
                segments.append(_green(f"✓{nid}"))
            elif nid == current_node:
                segments.append(_yellow(f"▶{nid}"))
            else:
                segments.append(_dim(f"○{nid}"))
        topo_str += " ──► ".join(segments)
    else:
        status_col = _yellow if lock_status == "pending" else (_green if "complete" in lock_status else _cyan)
        topo_str += status_col(f"[{current_node}]  status: {lock_status}")
    out.append(_trunc(topo_str, W, padded=False) + "\n")

    # Status bar
    done_n = len(done_nodes)
    total_n = str(len(topology)) if topology else "?"
    status = (
        f" Node {done_n}/{total_n}  │  ${actual_cost:.4f} spent  │  "
        f"status: {lock_status}  │  [Q] detach  [↑/↓] scroll thoughts  [←/→] scroll events"
    )
    out.append(_dim(_trunc(status, W, padded=False)) + "\n")

    return "".join(out)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_watcher(job_id: str, project: str, poll_ms: int = 500) -> None:
    """Non-blocking polling loop — exits on Q, ESC, or swarm terminal state."""
    poll = poll_ms / 1000.0
    start_ts = time.time()
    topology = _load_topology(project)
    done_nodes: set[str] = set()

    t_buf: deque[str] = deque(maxlen=500)
    e_buf: deque[str] = deque(maxlen=500)
    t_max = e_max = 0
    t_scroll = e_scroll = 0
    current_node = "—"
    lock_status = "queued"
    actual_cost = 0.0

    # Windows non-blocking keyboard
    _msvcrt = None
    if sys.platform == "win32":
        try:
            import msvcrt as _m  # type: ignore[import]
            _msvcrt = _m
        except ImportError:
            pass

    try:
        while True:
            # ── Keyboard ──────────────────────────────────────────────────────
            if _msvcrt and _msvcrt.kbhit():
                ch = _msvcrt.getwch()
                if ch in ("q", "Q", "\x1b"):
                    break
                if ch == "\xe0":
                        ch2 = _msvcrt.getwch()
                        if ch2 == "H":
                            t_scroll = min(t_scroll + 3, max(0, len(t_buf) - 1))   # Up
                        elif ch2 == "P":
                            t_scroll = max(t_scroll - 3, 0)                          # Down
                        elif ch2 == "K":
                            e_scroll = min(e_scroll + 3, max(0, len(e_buf) - 1))    # Left (←)
                        elif ch2 == "M":
                            e_scroll = max(e_scroll - 3, 0)                          # Right (→)

            # ── Poll thoughts ────────────────────────────────────────────────
            for rid, ts, node, content in _fetch_thoughts(job_id, project, t_max):
                t_max = max(t_max, rid)
                t_buf.append(f"[{ts}] [{node}] {content}")
                t_scroll = 0  # snap to bottom on new data

            # ── Poll events ──────────────────────────────────────────────────
            for rid, ts, node, msg in _fetch_events(job_id, project, e_max):
                e_max = max(e_max, rid)
                e_buf.append(f"[{ts}] [{node}] {msg}")
                e_scroll = 0

            # ── Queue status ─────────────────────────────────────────────────
            current_node, lock_status, actual_cost = _queue_status(job_id)

            if topology and current_node in topology:
                idx = topology.index(current_node)
                for n in topology[:idx]:
                    done_nodes.add(n)

            if lock_status in ("completed", "STOP", "DONE", "FAILED"):
                if topology:
                    done_nodes.update(topology)

            # ── Render ───────────────────────────────────────────────────────
            frame = _render_frame(
                job_id=job_id,
                project=project,
                start_ts=start_ts,
                current_node=current_node,
                lock_status=lock_status,
                actual_cost=actual_cost,
                topology=topology,
                done_nodes=done_nodes,
                t_buf=t_buf,
                e_buf=e_buf,
                t_scroll=t_scroll,
                e_scroll=e_scroll,
            )
            sys.stdout.write(frame)
            sys.stdout.flush()

            # ── Terminal state exit ──────────────────────────────────────────
            if lock_status in ("completed", "STOP", "DONE", "FAILED"):
                e_buf.append(f"  ✓ Swarm finished with status: {lock_status}")
                time.sleep(3)
                break

            time.sleep(poll)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(f"\n{_dim('[WATCHER] Detached. Swarm continues in background.')}\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="MACCRE Swarm Watcher — live swarm dashboard")
    parser.add_argument("--job-id",  required=True, help="Swarm job ID to watch")
    parser.add_argument("--project", default="",    help="Project silo name (for topology display)")
    parser.add_argument("--poll",    type=int, default=500, help="Poll interval in ms (default 500)")
    args = parser.parse_args()
    run_watcher(args.job_id, args.project or "GLOBAL", args.poll)


if __name__ == "__main__":
    main()
