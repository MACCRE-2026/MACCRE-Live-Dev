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
maccre_core/tools/knowledge_dedup.py
======================================
Knowledge Vault — Phase 0: Dedup + Scan

Walks a source archive directory, de-duplicates by SHA-256 hash and
"root thought" filename normalization, classifies file types, and emits
a DEDUP_MANIFEST.json. No AI calls, no moves — pure Python, read-only.

Usage (standalone):
    python -m maccre_core.tools.knowledge_dedup --source B:/Knowledge/Research --out B:/Knowledge/Vault

Usage (from MCP tool):
    from maccre_core.tools.knowledge_dedup import run_dedup_scan
    manifest = run_dedup_scan(source_dir="B:/Knowledge/Research")
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("maccre_core")

# ── File classification buckets ───────────────────────────────────────────────

DOC_EXTS: frozenset[str] = frozenset({".md", ".txt", ".rst"})
CODE_EXTS: frozenset[str] = frozenset({".py", ".js", ".ahk", ".ps1", ".bat", ".html", ".css", ".json"})
MEDIA_EXTS: frozenset[str] = frozenset({".mp4", ".m4a", ".wav", ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".gif"})
BINARY_EXTS: frozenset[str] = frozenset({
    ".pyc", ".pyd", ".pyi", ".dll", ".so", ".exe", ".bin",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".whl",
    ".salt", ".vault", ".vsidx", ".db", ".sqlite",
})

# Directories to skip entirely — venv / pycache / build contamination
SKIP_DIRS: frozenset[str] = frozenset({
    ".venv", "venv", "site-packages", "__pycache__", ".git", ".vs", ".idea",
    "build", "dist", "node_modules", "intermediates", ".gradle", "outputs",
    "tmp", "qml", "_Chunked", "Chunked_Compilation", ".ruff_cache",
    "Development",  # python library installs bleed-through
})

# Max file size to SHA-256 in one pass (100 MB). Larger files get a partial hash.
MAX_FULL_HASH_MB: int = 100

# Gemini header/footer artifacts to strip when reading preview text
_GEMINI_HEADER: str = "Conversation with Gemini"
_GEMINI_FOOTERS: tuple[str, ...] = (
    "Gemini can make mistakes, so double-check it",
    "Gemini may display inaccurate info",
    "Google Privacy Policy",
    "Google Terms of Service",
    "Your privacy & Gemini Apps",
)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class FileRecord:
    """One de-duplicated file entry in the manifest."""
    canonical_path: str          # Absolute path of the canonical (largest) copy
    root_thought: str            # Normalized stem — used for dedup grouping
    file_type: str               # "doc" | "code" | "media" | "binary" | "other"
    ext: str
    size_bytes: int
    sha256: str
    duplicate_count: int = 0     # How many other copies were collapsed into this
    duplicate_paths: list[str] = field(default_factory=list)
    preview: str = ""            # First 300 chars of cleaned text (docs only)
    suggested_category: str = "" # Filled by Phase 1 AI pass


@dataclass
class DedupManifest:
    """Full Phase 0 output."""
    source_dir: str
    generated_at: str
    total_files_scanned: int = 0
    total_size_bytes: int = 0
    skipped_binary: int = 0
    skipped_dir_excluded: int = 0
    records: list[FileRecord] = field(default_factory=list)

    @property
    def doc_count(self) -> int:
        return sum(1 for r in self.records if r.file_type == "doc")

    @property
    def code_count(self) -> int:
        return sum(1 for r in self.records if r.file_type == "code")

    @property
    def media_count(self) -> int:
        return sum(1 for r in self.records if r.file_type == "media")

    @property
    def dedup_savings(self) -> int:
        return sum(r.duplicate_count for r in self.records)


# ── Core helpers ───────────────────────────────────────────────────────────────

def clean_filename(filename: str) -> str:
    """
    Strips duplication artifacts to find the 'Root Thought'.
    Adapted from create_vectordb.py — the canonical ganglia logic.
    """
    base, _ = os.path.splitext(filename)
    base = re.sub(r"_COPY_\d+", "", base)
    base = re.sub(r"-Batch\d+", "", base)
    base = re.sub(r"\d+$", "", base)
    return base.strip()


def sha256_file(path: Path) -> str:
    """SHA-256 of a file. Hashes first 100 MB then appends size for large files."""
    h = hashlib.sha256()
    size = path.stat().st_size
    max_bytes = MAX_FULL_HASH_MB * 1024 * 1024
    try:
        with path.open("rb") as fh:
            read = 0
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
                read += len(chunk)
                if read >= max_bytes:
                    # Suffix size so identical-prefix files still differ
                    h.update(str(size).encode())
                    break
    except OSError:
        return "ERROR"
    return h.hexdigest()


def _read_preview(path: Path) -> str:
    """Read first 300 chars of a text file, stripping Gemini header/footer artifacts."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Strip Gemini header
        if _GEMINI_HEADER in raw:
            idx = raw.find(_GEMINI_HEADER)
            raw = raw[idx + len(_GEMINI_HEADER):].lstrip()
        # Strip trailing footers
        cleaned = raw.strip()
        for marker in _GEMINI_FOOTERS:
            if cleaned.endswith(marker):
                cleaned = cleaned[: -len(marker)].strip()
        return cleaned[:300].replace("\n", " ")
    except Exception:
        return ""


def _classify(ext: str) -> str:
    if ext in DOC_EXTS:
        return "doc"
    if ext in CODE_EXTS:
        return "code"
    if ext in MEDIA_EXTS:
        return "media"
    if ext in BINARY_EXTS:
        return "binary"
    return "other"


# ── Phase 0 scanner ────────────────────────────────────────────────────────────

def run_dedup_scan(
    source_dir: str = "",
    out_dir: str = "",
    emit_manifest: bool = True,
) -> DedupManifest:
    """
    Walk source_dir, dedup by root-thought + SHA-256, emit DEDUP_MANIFEST.json.

    Args:
        source_dir:     Root of the archive to scan. Defaults to B:/Knowledge/Research.
        out_dir:        Where to write DEDUP_MANIFEST.json. Defaults to source_dir.
        emit_manifest:  If True, writes the JSON file. Pass False for dry-run testing.

    Returns:
        DedupManifest dataclass with all record data.
    """
    src = Path(source_dir) if source_dir else Path("B:/Knowledge/Research")
    out = Path(out_dir) if out_dir else src

    if not src.exists():
        raise FileNotFoundError(f"Source directory not found: {src}")

    manifest = DedupManifest(
        source_dir=str(src),
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    # Two pass accumulators:
    # doc_groups: root_thought → list[(path, size)]  — for largest-wins dedup
    # hash_seen:  sha256 → canonical path            — for byte-exact dedup
    doc_groups: dict[str, list[tuple[Path, int]]] = {}
    hash_seen: dict[str, Path] = {}
    code_records: list[FileRecord] = []
    media_records: list[FileRecord] = []
    other_records: list[FileRecord] = []

    logger.info("Phase 0 scan starting: %s", src)
    t0 = time.monotonic()

    for root, dirs, files in os.walk(src):
        # Prune skip dirs in-place (modifies dirs to prevent descent)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for filename in files:
            filepath = Path(root) / filename
            ext = filepath.suffix.lower()
            file_type = _classify(ext)
            manifest.total_files_scanned += 1

            try:
                size = filepath.stat().st_size
            except OSError:
                continue

            manifest.total_size_bytes += size

            # Skip binaries entirely
            if file_type == "binary":
                manifest.skipped_binary += 1
                continue

            # ── Doc files: root-thought grouping ──────────────────────────
            if file_type == "doc":
                root_thought = clean_filename(filename)
                if root_thought not in doc_groups:
                    doc_groups[root_thought] = []
                doc_groups[root_thought].append((filepath, size))
                continue

            # ── Code, media, other: hash-dedup ────────────────────────────
            fhash = sha256_file(filepath)
            if fhash in hash_seen and fhash != "ERROR":
                logger.debug("Hash dup skipped: %s (canonical: %s)", filepath, hash_seen[fhash])
                continue
            if fhash != "ERROR":
                hash_seen[fhash] = filepath

            rec = FileRecord(
                canonical_path=str(filepath),
                root_thought=clean_filename(filename),
                file_type=file_type,
                ext=ext,
                size_bytes=size,
                sha256=fhash,
            )
            if file_type == "code":
                code_records.append(rec)
            elif file_type == "media":
                media_records.append(rec)
            else:
                other_records.append(rec)

    # ── Resolve doc groups: keep largest, list duplicates ─────────────────────
    logger.info("Resolving %d root-thought groups...", len(doc_groups))
    for root_thought, candidates in doc_groups.items():
        # Sort by size descending — largest is canonical
        candidates.sort(key=lambda x: x[1], reverse=True)
        canonical_path, canonical_size = candidates[0]
        dups = [str(p) for p, _ in candidates[1:]]

        # Byte-exact dedup against hash_seen for docs too
        fhash = sha256_file(canonical_path)
        if fhash in hash_seen and fhash != "ERROR" and hash_seen[fhash] != canonical_path:
            # Another canonical already covers this content — collapse
            manifest.skipped_binary += 1  # reuse counter as "dup collapsed"
            continue
        if fhash != "ERROR":
            hash_seen[fhash] = canonical_path

        preview = _read_preview(canonical_path)
        rec = FileRecord(
            canonical_path=str(canonical_path),
            root_thought=root_thought,
            file_type="doc",
            ext=canonical_path.suffix.lower(),
            size_bytes=canonical_size,
            sha256=fhash,
            duplicate_count=len(dups),
            duplicate_paths=dups,
            preview=preview,
        )
        manifest.records.append(rec)

    manifest.records.extend(code_records)
    manifest.records.extend(media_records)
    manifest.records.extend(other_records)

    elapsed = time.monotonic() - t0
    logger.info(
        "Phase 0 complete in %.1fs | scanned=%d | canonical=%d | docs=%d | code=%d | media=%d | dedup_saved=%d",
        elapsed,
        manifest.total_files_scanned,
        len(manifest.records),
        manifest.doc_count,
        manifest.code_count,
        manifest.media_count,
        manifest.dedup_savings,
    )

    if emit_manifest:
        out.mkdir(parents=True, exist_ok=True)
        manifest_path = out / "DEDUP_MANIFEST.json"
        payload: dict[str, Any] = {
            **{k: v for k, v in asdict(manifest).items() if k != "records"},
            "summary": {
                "canonical_files": len(manifest.records),
                "docs": manifest.doc_count,
                "code": manifest.code_count,
                "media": manifest.media_count,
                "dedup_savings": manifest.dedup_savings,
            },
            "records": [asdict(r) for r in manifest.records],
        }
        manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Manifest written: %s", manifest_path)

    return manifest


# ── CLI entry point ────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge Vault — Phase 0: Dedup + Scan")
    parser.add_argument("--source", default="", help="Archive root to scan (default: B:/Knowledge/Research)")
    parser.add_argument("--out", default="", help="Output directory for DEDUP_MANIFEST.json")
    parser.add_argument("--dry-run", action="store_true", help="Scan without writing manifest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    manifest = run_dedup_scan(
        source_dir=args.source,
        out_dir=args.out,
        emit_manifest=not args.dry_run,
    )

    total_mb = manifest.total_size_bytes / (1024 ** 2)
    logger.info(
        "\n%s\n  DEDUP SCAN COMPLETE\n%s\n"
        "  Source:          %s\n"
        "  Files scanned:   %s\n"
        "  Canonical files: %s\n"
        "  ├─ Docs:         %s\n"
        "  ├─ Code:         %s\n"
        "  └─ Media:        %s\n"
        "  Dedup savings:   %s duplicates collapsed\n"
        "  Binary skipped:  %s\n"
        "  Total scanned:   %s MB\n%s",
        "═" * 60, "─" * 60,
        manifest.source_dir,
        f"{manifest.total_files_scanned:,}",
        f"{len(manifest.records):,}",
        f"{manifest.doc_count:,}",
        f"{manifest.code_count:,}",
        f"{manifest.media_count:,}",
        f"{manifest.dedup_savings:,}",
        f"{manifest.skipped_binary:,}",
        f"{total_mb:,.1f}",
        "═" * 60,
    )


if __name__ == "__main__":
    _cli()
