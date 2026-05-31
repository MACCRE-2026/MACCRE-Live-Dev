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
maccre_core/tools/media_tools.py
==================================
Atomic, GUI-agnostic media-pipeline helpers for the MACCRE Tool Registry.

Harvested from NewsCast/stitcher.py and NewsCast/production_manager.py.
Business logic stripped; pure I/O-free functions + a single disk-write helper.

Gemini Function Calling schema contract:
  - Explicit Python type hints throughout.
  - Google-style docstrings (Args / Returns / Raises).
"""

import json
import pathlib
from typing import Any, Dict, List


def build_concat_manifest(
    logs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build an ordered production manifest from a list of speaker log dicts.

    Each log entry must contain at minimum ``"speaker"`` and ``"audio"`` keys.
    An optional ``"video_prompt"`` key is forwarded if present.

    Args:
        logs: List of production log dicts. Each dict must include:
            - ``"speaker"`` (str): Display name of the speaker.
            - ``"audio"`` (str): Filesystem path to the audio clip.
            - ``"video_prompt"`` (str, optional): Visual prompt for a video model.
            Example: [{"speaker": "Host", "audio": "/out/clip.wav", "video_prompt": "Cityscape"}]

    Returns:
        A list of manifest dicts, each containing:
        ``{"index": int, "speaker": str, "audio": str, "video_prompt": str}``.
        Entries are in the same order as ``logs``.
    """
    manifest: List[Dict[str, Any]] = []
    for i, entry in enumerate(logs):
        manifest.append(
            {
                "index": i,
                "speaker": entry.get("speaker", ""),
                "audio": entry.get("audio", ""),
                "video_prompt": entry.get("video_prompt", ""),
            }
        )
    return manifest


def build_ffmpeg_cmd(
    manifest: List[Dict[str, Any]],
    output_path: str,
    ffmpeg_path: str = "ffmpeg",
    placeholder_video: str = "placeholder.mp4",
) -> List[str]:
    """Construct the FFmpeg command list to concatenate manifest audio/video pairs.

    The returned command uses a ``-filter_complex concat`` to merge all
    audio/video stream pairs into a single output file. The caller is
    responsible for executing it (e.g. via ``subprocess.run``).

    Args:
        manifest: Ordered list of production dicts as returned by
            build_concat_manifest. Each dict must include an ``"audio"`` key (str).
            Example: [{"index": 0, "speaker": "Host", "audio": "/out/clip.wav", "video_prompt": ""}]
        output_path: Absolute or relative path to the desired output file
            (e.g. ``"/out/show.mp4"``).
        ffmpeg_path: Path to the FFmpeg executable. Defaults to ``"ffmpeg"``
            (assumes it is on ``$PATH``).
        placeholder_video: Fallback video file path used when no ``"video"``
            key is present in a manifest entry.

    Returns:
        A list of strings forming the complete FFmpeg command, suitable for
        passing directly to subprocess.run.
    """
    input_args: List[str] = []
    filter_complex = ""

    for i, item in enumerate(manifest):
        video_path = item.get("video", placeholder_video)
        audio_path = item["audio"]
        input_args.extend(["-i", video_path, "-i", audio_path])
        filter_complex += f"[{i * 2}:v][{i * 2 + 1}:a]"

    n = len(manifest)
    filter_complex += f"concat=n={n}:v=1:a=1 [v][a]"

    return [
        ffmpeg_path,
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-y",
        output_path,
    ]


def save_manifest(
    manifest_json: str,
    dest: str,
) -> str:
    """Serialise a production manifest to JSON on the local filesystem.

    Creates any missing parent directories automatically.

    Args:
        manifest_json: The manifest as a JSON-encoded string (output of json.dumps).
            Example: '[{"index": 0, "speaker": "Host", "audio": "/out/clip.wav", "video_prompt": ""}]'
        dest: Target filesystem path for the JSON file as a string
            (e.g. ``"B:/MACCREv2/__DATACENTER/04_Code_Artifacts/manifest.json"``).

    Returns:
        The absolute string path of the written JSON file.

    Raises:
        OSError: If the file cannot be written (e.g. permissions error).
    """
    manifest = json.loads(manifest_json)
    path = pathlib.Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
    return str(path.absolute())
