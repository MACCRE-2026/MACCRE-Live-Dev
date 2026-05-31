"""
scripts/rebuild_manifest.py
Deterministically rebuilds the SilmLOTR podcast_manifest.json from the two
sidecar files without relying on an LLM to do the aggregation correctly.

Logic:
  - Split podcast_screenplay.md on ## Scene N ## boundaries
  - For each scene: concatenate ALL spoken lines (PROFESSOR: ... and VALE: ...)
    into a single 'text' field
  - Determine primary speaker by who speaks MORE words in that scene
  - Match against the corresponding line from image_prompts.md
  - Write clean 20-object JSON array
"""
from __future__ import annotations

import json
import re
import pathlib

PROJECT_DIR = pathlib.Path("B:/MACCREv2/__DATACENTER/SilmLOTR")
SCREENPLAY  = PROJECT_DIR / "04_Code_Artifacts/podcast_screenplay.md"
PROMPTS     = PROJECT_DIR / "04_Code_Artifacts/image_prompts.md"
MANIFEST    = PROJECT_DIR / "04_Code_Artifacts/podcast_manifest.json"

# ── Read screenplay and split on scene markers ──────────────────────────────

screenplay_text = SCREENPLAY.read_text(encoding="utf-8")
# Split on ## Scene N ## (with optional ##/## variations)
scene_pattern = re.compile(r"##\s*Scene\s+\d+\s*##", re.IGNORECASE)
parts = scene_pattern.split(screenplay_text)
# parts[0] is any preamble before Scene 1; parts[1..] are the scene bodies
scene_bodies: list[str] = [p.strip() for p in parts[1:] if p.strip()]
print(f"Found {len(scene_bodies)} scene bodies in screenplay.")

# ── Parse each scene body ────────────────────────────────────────────────────

SPEAKER_RE = re.compile(r"^(PROFESSOR|VALE)\s*:\s*(.+)", re.IGNORECASE | re.MULTILINE)

def extract_scene_dialogue(body: str) -> tuple[str, str]:
    """Returns (primary_speaker, combined_text) for a scene body."""
    matches = SPEAKER_RE.findall(body)
    if not matches:
        # fallback: use full body as text, guess PROFESSOR
        clean = re.sub(r"\*.*?\*", "", body).strip()
        return ("PROFESSOR", clean)

    prof_words = 0
    vale_words = 0
    combined: list[str] = []
    for speaker, line in matches:
        line = line.strip()
        combined.append(line)
        wc = len(line.split())
        if speaker.upper() == "PROFESSOR":
            prof_words += wc
        else:
            vale_words += wc

    primary = "PROFESSOR" if prof_words >= vale_words else "VALE"
    return (primary, " ".join(combined))

scenes: list[tuple[str, str]] = [extract_scene_dialogue(b) for b in scene_bodies]

# ── Read image prompts ───────────────────────────────────────────────────────

prompts_text = PROMPTS.read_text(encoding="utf-8")
# Format: "Scene N: [prompt text]"
prompt_pattern = re.compile(r"Scene\s+(\d+)\s*:\s*(.+?)(?=Scene\s+\d+\s*:|$)", re.DOTALL | re.IGNORECASE)
prompt_map: dict[int, str] = {}
for m in prompt_pattern.finditer(prompts_text):
    idx = int(m.group(1))
    prompt_map[idx] = m.group(2).strip().replace("\n", " ")

print(f"Found {len(prompt_map)} image prompts.")

# ── Assemble manifest ────────────────────────────────────────────────────────

manifest: list[dict[str, str]] = []
for i, (speaker, text) in enumerate(scenes, start=1):
    video_prompt = prompt_map.get(i, "")
    manifest.append({
        "speaker": speaker,
        "text": text,
        "video_prompt": video_prompt,
    })

# ── Stats ──────────────────────────────────────────────────────────────────

total_words = sum(len(s["text"].split()) for s in manifest)
print(f"\nManifest assembled: {len(manifest)} scenes, {total_words} total words")
print(f"Estimated runtime at 130wpm: {total_words/130:.1f} minutes")
for i, s in enumerate(manifest):
    w = len(s["text"].split())
    print(f"  S{i+1:02d} {s['speaker'][:9]:9} {w:4}w  img={bool(s['video_prompt'])}")

# ── Write ───────────────────────────────────────────────────────────────────

MANIFEST.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(f"\n[OK] Manifest written to {MANIFEST}")
