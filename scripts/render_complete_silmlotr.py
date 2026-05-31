"""render_complete_silmlotr.py — completes the SilmLOTR render"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

# Force UTF-8 stdio on Windows so print() doesn't hit CP1252 walls
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

MANIFEST_PATH = REPO_ROOT / "__DATACENTER/SilmLOTR/04_Code_Artifacts/podcast_manifest.json"
OUTPUT_DIR = REPO_ROOT / "__DATACENTER/SilmLOTR/05_Rendered_Media/job_resume_1777002728"
AUDIO_DIR = OUTPUT_DIR / "audio"
VISUALS_DIR = OUTPUT_DIR / "visuals"
SEGMENTS_DIR = OUTPUT_DIR / "segments"


def log(msg: str) -> None:
    print(f"[RENDER] {msg}", flush=True)


def get_ffmpeg() -> str:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # WinGet install path
    winget_root = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local")) / "Microsoft/WinGet/Packages"
    for p in winget_root.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
        if p.is_file():
            return str(p)
    return "ffmpeg"


def get_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        return int((w.getnframes() / w.getframerate()) * 1000)


async def main() -> None:
    # ── Load manifest ──────────────────────────────────────────────────────────
    manifest: list[dict] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    log(f"Manifest loaded: {len(manifest)} scenes")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Boot the pipeline ──────────────────────────────────────────────────────
    from maccre_core.tools.render_executor import CloudMediaPipeline  # noqa: PLC0415
    pipeline = CloudMediaPipeline()

    # ── Phase A: TTS — only missing scenes ────────────────────────────────────
    missing_audio: list[tuple[int, dict]] = []
    for idx, scene in enumerate(manifest):
        audio_path = AUDIO_DIR / f"scene_{idx:03d}.wav"
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            missing_audio.append((idx, scene))

    if missing_audio:
        log(f"Generating TTS for {len(missing_audio)} missing scenes: {[i for i,_ in missing_audio]}")
        sem = asyncio.Semaphore(5)

        async def _safe_tts(idx: int, scene: dict) -> None:
            async with sem:
                await asyncio.sleep(0.1)
                out = AUDIO_DIR / f"scene_{idx:03d}.wav"
                await pipeline.generate_audio(scene["text"], scene.get("speaker", "Host"), out)
                log(f"  [OK] Audio scene_{idx:03d}.wav ({out.stat().st_size:,} bytes)")

        await asyncio.gather(*[_safe_tts(i, s) for i, s in missing_audio])
    else:
        log("All audio scenes already present — skipping TTS phase.")

    # ── Phase B: Images — only missing scenes (sequential, 5s gate) ───────────
    missing_images: list[tuple[int, dict]] = []
    for idx, scene in enumerate(manifest):
        if not scene.get("video_prompt"):
            continue
        img_path = VISUALS_DIR / f"scene_{idx:03d}.jpg"
        if not img_path.exists() or img_path.stat().st_size == 0:
            missing_images.append((idx, scene))

    if missing_images:
        log(f"Generating images for {len(missing_images)} missing scenes: {[i for i,_ in missing_images]}")
        for n, (idx, scene) in enumerate(missing_images):
            out_path = VISUALS_DIR / f"scene_{idx:03d}.jpg"
            _max_retries = 5
            for attempt in range(_max_retries):
                try:
                    await pipeline.generate_image(scene["video_prompt"], out_path)
                    log(f"  [OK] Image scene_{idx:03d}.jpg ({out_path.stat().st_size:,} bytes) [{n+1}/{len(missing_images)}]")
                    if n < len(missing_images) - 1:
                        await asyncio.sleep(5.0)  # Stay under 15 RPM
                    break
                except Exception as exc:
                    err = str(exc)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err:
                        match = re.search(r"retry\s+in\s+([\d.]+)s", err, re.IGNORECASE)
                        wait = float(match.group(1)) + 2.0 if match else 60.0
                        log(f"  ! 429 on scene_{idx:03d} — backoff {wait:.0f}s (attempt {attempt+1}/{_max_retries})")
                        await asyncio.sleep(wait)
                    else:
                        log(f"  [FAIL] Image scene_{idx:03d} failed: {exc}")
                        raise
    else:
        log("All image scenes already present — skipping image phase.")

    # ── Phase C: Audio timeline computation ───────────────────────────────────
    log("Computing audio timeline for all 20 scenes...")
    audio_timeline: list[dict] = []
    filter_lines: list[str] = []
    amix_inputs = ""
    current_time_ms = 0
    last_valid_image = VISUALS_DIR / "scene_000.jpg"

    for idx, scene in enumerate(manifest):
        audio_path = AUDIO_DIR / f"scene_{idx:03d}.wav"
        image_path = VISUALS_DIR / f"scene_{idx:03d}.jpg"

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            log(f"  WARN: scene_{idx:03d} audio missing — skipping")
            continue

        active_img = image_path if (image_path.exists() and image_path.stat().st_size > 0) else last_valid_image
        last_valid_image = active_img

        duration = get_duration_ms(audio_path)
        overlap = 1500 if scene.get("is_interruption", False) else 0
        if overlap > current_time_ms:
            overlap = 0

        start_time = current_time_ms - overlap
        filter_lines.append(f"[{idx}:a]adelay={start_time}|{start_time}[a{idx}];")
        amix_inputs += f"[a{idx}]"

        audio_timeline.append({"img": active_img, "start_ms": start_time, "end_ms": start_time + duration})
        current_time_ms = start_time + duration

    total_duration_s = current_time_ms / 1000.0
    log(f"Total duration: {total_duration_s:.1f}s ({total_duration_s/60:.1f} minutes), {len(audio_timeline)} scenes active")

    filter_lines.append(
        f"{amix_inputs}amix=inputs={len(audio_timeline)}:duration=longest:normalize=0[aout]"
    )

    filter_script = OUTPUT_DIR / "filter_complex.txt"
    filter_script.write_text("\n".join(filter_lines), encoding="utf-8")

    # ── Phase D: Master audio mix ──────────────────────────────────────────────
    log("Mixing master audio track...")
    ffmpeg = get_ffmpeg()
    master_audio = OUTPUT_DIR / "master_audio.wav"

    # Build full input list (all 20 scene files — ffmpeg needs them all for filter indexing)
    audio_cmd = [ffmpeg, "-y"]
    for i in range(len(manifest)):
        ap = AUDIO_DIR / f"scene_{i:03d}.wav"
        if ap.exists() and ap.stat().st_size > 0:
            audio_cmd.extend(["-i", str(ap)])
        else:
            # Insert a silent placeholder so filter indices match
            audio_cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono"])
    audio_cmd.extend(["-filter_complex_script", str(filter_script), "-map", "[aout]", str(master_audio)])

    result = subprocess.run(audio_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"FFmpeg audio mix FAILED:\n{result.stderr[-2000:]}")
        sys.exit(1)
    log(f"  [OK] master_audio.wav ({master_audio.stat().st_size:,} bytes)")

    # ── Phase E: Video concat ──────────────────────────────────────────────────
    log("Building video concat list...")
    clip_concat_file = SEGMENTS_DIR / "clips_concat.txt"
    with open(clip_concat_file, "w", encoding="utf-8") as f:
        for i in range(len(audio_timeline)):
            curr = audio_timeline[i]
            next_start = audio_timeline[i + 1]["start_ms"] if i + 1 < len(audio_timeline) else curr["end_ms"]
            hold_dur = max((next_start - curr["start_ms"]) / 1000.0, 0.1)
            f.write(f"file '{curr['img'].absolute().as_posix()}'\n")
            f.write(f"duration {hold_dur:.3f}\n")
        # Seal the concat demuxer
        f.write(f"file '{audio_timeline[-1]['img'].absolute().as_posix()}'\n")

    output_mp4 = OUTPUT_DIR / "podcast_output.mp4"
    log(f"Assembling final video → {output_mp4}")

    concat_cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0", "-i", str(clip_concat_file),
        "-i", str(master_audio),
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "slow",   # slow for quality
        "-crf", "20",                                                    # quality gate
        "-vf", "scale=1280:720,setsar=1",                               # 720p output
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_mp4),
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"FFmpeg concat FAILED:\n{result.stderr[-3000:]}")
        sys.exit(1)

    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    log(f"\n{'='*60}")
    log("RENDER COMPLETE")
    log(f"  Output: {output_mp4}")
    log(f"  Duration: {total_duration_s:.1f}s ({total_duration_s/60:.1f} min)")
    log(f"  File size: {size_mb:.1f} MB")
    log(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
