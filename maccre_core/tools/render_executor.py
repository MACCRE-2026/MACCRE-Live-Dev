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
maccre_core/tools/render_executor.py
====================================
Dual-Pipeline Media Render Executor.
Consumes Director JSON, routes generation to Cloud/Local, and executes Edge FFmpeg stitch.
"""

import abc
import asyncio
import base64
import json
import os
import shutil
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from maccre_core._net.model_registry import ModelSurface, get_registry
from maccre_core.logger import logger
from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.tools.audio_tools import (
    VoiceProfile,
    build_tts_config,
    build_tts_config_from_profile,
    load_voice_roster,
    pack_wav_bytes,
)
from maccre_core.utils.path_resolver import get_datacenter_path

# Default silo — used when no session_dir is provided
DATACENTER = get_datacenter_path("05_Rendered_Media")

# ── FFmpeg Binary Resolution ───────────────────────────────────────────────────
_FFMPEG_WINGET_GLOB = (
    Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local"))
    / "Microsoft/WinGet/Packages"
)
_ffmpeg_fallback = next(
    (
        p for p in _FFMPEG_WINGET_GLOB.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe")
        if p.is_file()
    ),
    None,
)
FFMPEG_BIN: str = shutil.which("ffmpeg") or (
    str(_ffmpeg_fallback) if _ffmpeg_fallback else "ffmpeg"
)


class BaseMediaPipeline(abc.ABC):
    """Strangler Fig Interface for Media Generation"""

    @abc.abstractmethod
    async def generate_audio(self, text: str, speaker: str, out_path: Path) -> Path:
        pass

    @abc.abstractmethod
    async def generate_image(self, prompt: str, out_path: Path) -> Path:
        pass


class CloudMediaPipeline(BaseMediaPipeline):
    """Sovereign Cloud Media Pipeline — zero SDK dependency."""

    _IMAGEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateImages"
    _TTS_URL    = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self) -> None:
        raw_key = get_provider_credential("MACCRE_Sovereign")
        if not raw_key:
            raise ValueError("CRITICAL: Vault returned empty for CloudMediaPipeline.")
        self._key: str = str(raw_key).strip()
        self._ssl = ssl.create_default_context()
        self._registry = get_registry(lambda: get_provider_credential("MACCRE_Sovereign"))
        # active_image_model is set lazily from registry on first generate_image call
        self.active_image_model: str = ""

    def _emit_gui_hook(
        self,
        failed_model: str,
        available_models: list[str],
        auto_selected: str,
    ) -> None:
        """Fires a UDP packet to the Flet GUI for the Artisan to hook into."""
        _sock: socket.socket | None = None
        try:
            _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload = json.dumps({
                "event": "MODEL_DRIFT_DETECTED",
                "failed_model": failed_model,
                "available_models": available_models,
                "auto_selected": auto_selected,
                "action_required": "GUI_MODAL_PROMPT",
            }).encode("utf-8")
            _sock.sendto(payload, ("127.0.0.1", 5555))
        except Exception:
            pass  # Never fail the render loop if the GUI is offline
        finally:
            if _sock is not None:
                _sock.close()

    async def generate_audio(
        self,
        text: str,
        speaker: str,
        out_path: Path,
        voice_roster: dict[str, VoiceProfile] | None = None,
    ) -> Path:
        # ── VoiceProfile Resolution ────────────────────────────────────────────
        # Priority: voice_roster.json profile > legacy voice_map fallback.
        # The voice_roster is loaded once per render session and passed in.
        _profile: VoiceProfile | None = None
        if voice_roster:
            _profile = (
                voice_roster.get(speaker)
                or voice_roster.get(speaker.upper())
                or next(
                    (v for k, v in voice_roster.items() if k.lower() == speaker.lower()),
                    None,
                )
            )

        if _profile:
            tts_config = build_tts_config_from_profile(_profile)
        else:
            # ── Generic role voice map — no content-specific names ─────────────
            # Maps broad speaker roles to prebuilt Gemini TTS voices.
            # All content-specific voices (characters, show personas) must live
            # in voice_roster.json where they are fully operator-tunable.
            _ROLE_VOICE_MAP: dict[str, str] = {
                "HOST":      "Fenrir",  "HOST_A":    "Fenrir",
                "HOST_B":    "Kore",    "NARRATOR":  "Aoede",
                "GUEST":     "Charon",  "MODERATOR": "Aoede",
            }
            _voice_name = (
                _ROLE_VOICE_MAP.get(speaker.upper()) or "Puck"
            )
            tts_config = build_tts_config(_voice_name)

        # ── Hierarchical Micro-Direction Audio Prompt ──────────────────────────
        # Structure: Preamble → AUDIO PROFILE → SCENE → DIRECTOR'S NOTES
        #            → #### TRANSCRIPT delimiter → spoken text with inline tags
        #
        # The #### TRANSCRIPT delimiter signals the TTS model that everything
        # above is director context — only what follows should be voiced.
        # This is the canonical technique for preventing bracket read-aloud errors.
        if _profile and (_profile.audio_profile or _profile.directors_notes):
            # ── VoiceProfile-driven hierarchical prompt (fully tunable) ────
            _tag_prefix = ", ".join(_profile.tag_defaults) + ", " if _profile.tag_defaults else ""
            audio_prompt = (
                "Synthesize speech for the following performance. "
                "Scene notes and director's directions are for guidance only — do not read them aloud.\n\n"
                f"AUDIO PROFILE: {_profile.audio_profile}\n"
                f"SCENE: {_profile.scene_context}\n"
                f"DIRECTOR'S NOTES: {_profile.directors_notes}\n"
                f"Do not read [bracketed] stage directions aloud — perform them.\n"
                f"#### TRANSCRIPT\n{_tag_prefix}{text}"
            )
        else:
            # ── Generic fallback — no content-specific persona injected ────
            # The DIRECTOR's micro-direction tags in the text are the sole
            # performance guidance when no VoiceProfile is loaded.
            audio_prompt = (
                "Synthesize natural-sounding speech for the following transcript. "
                f"You are voicing the speaker '{speaker}'. "
                "Perform [bracketed] stage directions — do not read them aloud.\n\n"
                f"#### TRANSCRIPT\n{text}"
            )

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": audio_prompt}]}],
            "generationConfig": tts_config,
        }

        # TTS model ladder — pulled from live registry, falls back to hardcoded
        _TTS_MODELS = self._registry.get_models_for_surface(ModelSurface.TTS) or [
            "gemini-2.5-flash-preview-tts",
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-pro-preview-tts",
        ]

        async def _try_tts(model: str) -> bytes:
            url = self._TTS_URL.format(model=model) + f"?key={self._key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            def _do_request() -> bytes:
                with urllib.request.urlopen(req, context=self._ssl, timeout=90) as r:
                    return r.read()
            return await asyncio.to_thread(_do_request)

        raw: bytes | None = None
        for _tts_model in _TTS_MODELS:
            try:
                raw = await _try_tts(_tts_model)
                break
            except urllib.error.HTTPError as _tts_exc:
                if _tts_exc.code in (400, 404):
                    logger.warning("[TTS] %s returned %d — trying next model.", _tts_model, _tts_exc.code)
                    continue
                raise
        if raw is None:
            raise RuntimeError(f"All TTS models exhausted for speaker '{speaker}'")

        resp_dict: dict[str, Any] = json.loads(raw.decode("utf-8"))

        for cand in resp_dict.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData", {})
                if inline.get("mimeType", "").startswith("audio/"):
                    pcm = base64.b64decode(inline["data"])
                    out_path.write_bytes(pack_wav_bytes(pcm))
                    return out_path

        raise RuntimeError(f"Failed to generate audio for {speaker}")

    async def generate_image(self, prompt: str, out_path: Path) -> Path:
        # Image models discovered via registry surface map.
        # Probe confirmed: imagen-4.x use 'predict' (Vertex AI) — not accessible here.
        # The IMAGE_GENERATION surface returns gemini-*-image models via generateContent.
        _IMAGE_LADDER = self._registry.get_models_for_surface(ModelSurface.IMAGE_GENERATION) or [
            "gemini-2.5-flash-image",
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
        ]
        if not self.active_image_model or self.active_image_model not in _IMAGE_LADDER:
            self.active_image_model = _IMAGE_LADDER[0]

        logger.info(f"[CLOUD] Generating visual asset using {self.active_image_model}...")

        # Prompt is used verbatim — style guidance is the SCRIPTWRITER's responsibility
        # via the video_prompt field. No content-driven defaults are applied here.
        styled_prompt = prompt

        async def _do_gen_image(model: str) -> bytes:
            body: dict[str, Any] = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": styled_prompt}],
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            }
            url = self._TTS_URL.format(model=model) + f"?key={self._key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            def _call() -> bytes:
                with urllib.request.urlopen(req, context=self._ssl, timeout=90) as r:
                    return r.read()
            return await asyncio.to_thread(_call)

        raw: bytes | None = None
        for _model in _IMAGE_LADDER:
            try:
                raw = await _do_gen_image(_model)
                self.active_image_model = _model
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 400):
                    logger.warning("[!] Image model %s returned %d — trying next.", _model, exc.code)
                    continue
                raise

        if raw is None:
            raise RuntimeError("CRITICAL: All Gemini image models exhausted in sovereign ladder.")

        resp: dict[str, Any] = json.loads(raw.decode("utf-8"))
        for cand in resp.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData", {})
                mime = inline.get("mimeType", "")
                if mime.startswith("image/"):
                    out_path.write_bytes(base64.b64decode(inline["data"]))
                    return out_path

        raise RuntimeError("Failed to generate image: API returned no image data.")


class LocalMediaPipeline(BaseMediaPipeline):
    """Air-Gapped Local Successor (Kokoro TTS & Flux.1 Local API)"""

    async def generate_audio(self, text: str, speaker: str, out_path: Path) -> Path:
        logger.info(f"[EDGE] Routing to local Kokoro TTS API -> {out_path.name}")
        # Placeholder for local Kokoro API call
        out_path.write_bytes(b"MOCK_WAV")
        return out_path

    async def generate_image(self, prompt: str, out_path: Path) -> Path:
        logger.info(f"[EDGE] Routing to local ComfyUI/Flux API -> {out_path.name}")
        # Placeholder for local ComfyUI API call
        out_path.write_bytes(b"MOCK_JPG")
        return out_path


def _emit_render_telemetry(
    session_stem: str, scene_count: int, tts_chars: int,
    image_count: int, render_mode: str, output_path: str,
    image_model: str = "gemini-2.5-flash-image",
) -> None:
    """Emit MEDIA_RENDER_COMPLETE to system_logs.db. Non-fatal."""
    try:
        import os as _os  # noqa: PLC0415
        from maccre_core.orchestration.telemetry_db import log_system_event  # noqa: PLC0415
        from maccre_core.tools.finops_tools import calculate_media_cost  # noqa: PLC0415
        _cost = calculate_media_cost(image_count, tts_chars, image_model)
        _payload = json.dumps({
            "scene_count": scene_count, "tts_chars": tts_chars,
            "image_count": image_count, "render_mode": render_mode,
            "output_path": output_path, "image_model": image_model,
        })
        log_system_event(
            action_type="MEDIA_RENDER_COMPLETE", payload=_payload, cost=_cost,
            session_id=session_stem,
            project_id=_os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL"),
            agent_id="render_executor",
        )
        logger.info("[*] Render telemetry emitted: cost=$%.6f mode=%s", _cost, render_mode)
    except Exception as _e:  # noqa: BLE001
        logger.warning("[*] Render telemetry emission failed (non-fatal): %s", _e)


def _heuristic_json_heal(raw_json: str) -> list[dict[str, Any]]:
    import json
    try:
        parsed = json.loads(raw_json)
        
        # 1. Handle object-wrapped arrays (LLM hallucination)
        if isinstance(parsed, dict):
            _found_arr = False
            for key in ["chapters", "scenes", "manifest", "segments"]:
                if key in parsed and isinstance(parsed[key], list):
                    parsed = parsed[key]
                    _found_arr = True
                    break
            if not _found_arr:
                if "text" in parsed or "speaker" in parsed or "script" in parsed:
                    parsed = [parsed]
                else:
                    raise ValueError(f"JSON must be an array of scenes, got dict: {list(parsed.keys())}")
        
        # 2. Normalize hallucinated text keys
        valid_scenes: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            for scene in parsed:
                if isinstance(scene, dict):
                    scene_dict: dict[str, Any] = dict(scene)
                    if "text" not in scene_dict and "script" in scene_dict:
                        scene_dict["text"] = scene_dict["script"]
                    elif "text" not in scene_dict and "content" in scene_dict:
                        scene_dict["text"] = scene_dict["content"]
                    valid_scenes.append(scene_dict)
                        
        return valid_scenes
    except json.JSONDecodeError:
        logger.warning("[!] Director JSON truncated (likely hit API Token Limit). Engaging Auto-Healer...")
        # Find the last properly closed dictionary in the array
        last_brace_idx = raw_json.rfind('}')
        if last_brace_idx != -1:
            # Slice off the broken trailing array data
            healed = raw_json[:last_brace_idx + 1].strip()
            # If there's a trailing comma from the LLM, we shouldn't necessarily see it before the brace,
            # but we must ensure the array is closed.
            healed += "]"
            try:
                result = json.loads(healed)
                
                # Normalize keys on healed data too
                if isinstance(result, list):
                    for scene in result:
                        if isinstance(scene, dict):
                            if "text" not in scene and "script" in scene:
                                scene["text"] = scene["script"]
                
                logger.info(f"[+] Successfully healed truncated JSON. Recovered {len(result)} scenes!")
                return result
            except json.JSONDecodeError as exc:
                logger.error("[CRASH] Healer failed to re-seal structural array.")
                raise exc
        raise ValueError("JSON fundamentally unparseable, no trailing brace found.")

async def _async_execute_render_pipeline(
    manifest_json: str,
    session_dir: str = "",
    audio_only: bool = True,
) -> str:
    manifest: list[dict[str, Any]] = _heuristic_json_heal(manifest_json)
    pipeline = CloudMediaPipeline()

    # ── Resolve output directories (session-scoped or global silo) ────────────
    base_dir: Path = Path(session_dir) if session_dir else DATACENTER
    audio_dir = base_dir / "audio"
    visuals_dir = base_dir / "visuals"
    audio_dir.mkdir(parents=True, exist_ok=True)
    visuals_dir.mkdir(parents=True, exist_ok=True)

    # ── Deterministic session-scoped output naming ────────────────────────────
    # Use the session directory stem (the job_id portion) in all user-facing
    # output filenames so every render is uniquely identified and nothing
    # overwrites a previous session's artifacts.
    _session_stem: str = base_dir.name if session_dir else "standalone"

    logger.info(f"[*] Starting Render Pipeline — {len(manifest)} segments | session: {_session_stem} | dir: {base_dir}")
    if audio_only:
        logger.info("[*] audio_only=True — visual generation suppressed regardless of video_prompt fields.")

    # Pre-compute render metrics for telemetry (scanned once, used at both return points)
    _total_tts_chars: int = sum(len(s.get("text", "")) for s in manifest)
    _total_image_count: int = (
        0 if audio_only else sum(1 for s in manifest if str(s.get("video_prompt", "")).strip())
    )

    # ── Load VoiceRoster once for this render session ────────────────────────
    _voice_roster: dict[str, VoiceProfile] = load_voice_roster()
    if _voice_roster:
        logger.info(f"[*] VoiceRoster loaded: {len(_voice_roster)} speaker profile(s).")
    else:
        logger.info("[*] No voice_roster.json found — using legacy voice_map fallback.")

    # ── Phase A: TTS — Batched Concurrency with exponential backoff ─────────
    # Semaphore at 4: sends 4 concurrent TTS requests max.
    # Firing all 8 simultaneously caused intermittent 500/TimeoutErrors.
    tts_semaphore = asyncio.Semaphore(4)

    async def _safe_generate_audio(txt: str, spk: str, path: Path) -> Path:
        import urllib.error as _uerr  # noqa: PLC0415
        async with tts_semaphore:
            _max_attempts = 3
            _wait = 2.0
            for _attempt in range(_max_attempts):
                try:
                    await asyncio.sleep(0.1 * (_attempt + 1))  # stagger on each attempt
                    return await pipeline.generate_audio(txt, spk, path, voice_roster=_voice_roster)
                except (_uerr.HTTPError, TimeoutError, OSError) as _exc:
                    _code = getattr(_exc, "code", 0)
                    _transient = isinstance(_exc, (TimeoutError, OSError)) or _code in (429, 500, 503)
                    if _transient and _attempt < _max_attempts - 1:
                        logger.warning(
                            "[TTS] Attempt %d/%d failed (%s) — retrying in %.0fs",
                            _attempt + 1, _max_attempts, _exc, _wait,
                        )
                        await asyncio.sleep(_wait)
                        _wait *= 2.0  # exponential: 2s → 4s
                    else:
                        logger.error("[TTS] Segment '%s' failed after %d attempts — writing silence.", spk, _max_attempts)
                        # Write a minimal silent WAV so FFmpeg stitch doesn't crash
                        from maccre_core.tools.render_executor import pack_wav_bytes  # noqa: PLC0415
                        path.write_bytes(pack_wav_bytes(b"\x00" * 4800))  # 0.1s of silence @ 24kHz
                        return path
        return path  # unreachable, satisfies type checker

    audio_tasks: list[asyncio.Task[Path]] = []
    image_scene_queue: list[tuple[str, Path]] = []  # (prompt, out_path)

    for idx, scene in enumerate(manifest):
        audio_path = audio_dir / f"scene_{idx:03d}.wav"
        image_path = visuals_dir / f"scene_{idx:03d}.jpg"

        audio_tasks.append(
            asyncio.ensure_future(
                _safe_generate_audio(scene["text"], scene.get("speaker", "Host"), audio_path)
            )
        )
        # Visuals only if explicitly enabled AND the scene has a prompt.
        # audio_only=True (default) silently ignores video_prompt — the LLM cannot
        # accidentally trigger image generation by including the field.
        if not audio_only and scene.get("video_prompt"):
            image_scene_queue.append((scene["video_prompt"], image_path))
        elif not audio_only:
            # Video mode, but this scene has no prompt — write 0-byte placeholder
            # so FFmpeg frame timing stays consistent across the scene list.
            image_path.write_bytes(b"")

    logger.info(f"[*] Dispatching {len(audio_tasks)} TTS tasks (max 4 concurrent, 3-attempt backoff)...")
    await asyncio.gather(*audio_tasks)


    # ── Phase B: Images — fully sequential with retry-after backoff ───────────
    import re as _re  # noqa: PLC0415

    logger.info(f"[*] Processing {len(image_scene_queue)} image tasks sequentially (15 RPM gate)...")
    for i, (prompt, out_path) in enumerate(image_scene_queue):
        _max_retries = 5
        for _attempt in range(_max_retries):
            try:
                await pipeline.generate_image(prompt, out_path)
                if i < len(image_scene_queue) - 1:
                    await asyncio.sleep(5.0)  # 5s between calls → 12 req/min ≤ 15 RPM limit
                break
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    # Parse retry-after from error message (e.g. "retry in 38.4s")
                    _match = _re.search(r"retry\s+in\s+([\d.]+)s", err_str, _re.IGNORECASE)
                    _wait = float(_match.group(1)) + 2.0 if _match else 60.0
                    logger.info(f"[!] 429 on image {i+1}/{len(image_scene_queue)}. Backing off {_wait:.0f}s...")
                    await asyncio.sleep(_wait)
                else:
                    raise  # Non-quota errors propagate immediately


    # ── FINOPS INJECTION ──────────────────────────────────────────────────────
    from maccre_core.orchestration.telemetry_db import log_system_event  # noqa: PLC0415
    from maccre_core.tools.finops_tools import calculate_media_cost  # noqa: PLC0415

    num_images = sum(1 for scene in manifest if scene.get("video_prompt"))
    total_chars = sum(len(scene.get("text", "")) for scene in manifest)

    actual_cost = 0.0
    active_model_name = getattr(pipeline, "active_image_model", "local")
    if isinstance(pipeline, CloudMediaPipeline):
        actual_cost = calculate_media_cost(num_images, total_chars, active_model_name)

    log_system_event(
        action_type="MEDIA_RENDER_COMPLETE",
        payload=(
            f"Rendered {len(manifest)} scenes. "
            f"Images: {num_images}, TTS Chars: {total_chars}, Model: {active_model_name}"
        ),
        cost=actual_cost,
        agent_id="THE_DIRECTOR",
        source_node="RENDER_NODE",
        model_id=active_model_name,
    )
    # ─────────────────────────────────────────────────────────────────────────

    # ── Phase 1: Overlapped Conversational Audio Physics & Frame Computation ──
    logger.info("[*] Executing SSML Conversational Audio Matrix (Overlaps Active)")
    import wave
    def get_duration_ms(path: Path) -> int:
        with wave.open(str(path), 'rb') as w:
            return int((w.getnframes() / w.getframerate()) * 1000)

    audio_timeline = []  # List of dicts tracking [image_path, start_ms, end_ms]
    current_time_ms = 0
    filter_lines = []
    amix_inputs = ""

    last_valid_image = visuals_dir / "scene_000.jpg" # Base anchor

    for idx, scene in enumerate(manifest):
        audio_path = audio_dir / f"scene_{idx:03d}.wav"
        image_path = visuals_dir / f"scene_{idx:03d}.jpg"
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            continue

        active_img = image_path if (image_path.exists() and image_path.stat().st_size > 0) else last_valid_image
        last_valid_image = active_img

        duration = get_duration_ms(audio_path)
        overlap = 1500 if scene.get("is_interruption", False) else 0
        if overlap > current_time_ms:
            overlap = 0  # Prevent negative delays

        start_time = current_time_ms - overlap

        # Build Filter Graph for this track
        filter_lines.append(f"[{idx}:a]adelay={start_time}|{start_time}[a{idx}];")
        amix_inputs += f"[a{idx}]"

        audio_timeline.append({
            "img": active_img, "start_ms": start_time, "end_ms": start_time + duration
        })
        current_time_ms = start_time + duration

    # Compile the final Amix node
    filter_lines.append(f"{amix_inputs}amix=inputs={len(audio_timeline)}:duration=longest:normalize=0[aout]")

    filter_script = base_dir / "filter_complex.txt"
    with open(filter_script, "w", encoding="utf-8") as f:
        f.write("\n".join(filter_lines))

    # Compile Master Overlapped Audio
    # Only include WAV files that actually exist — a missing file causes FFmpeg to abort.
    # (Silence fallback in _safe_generate_audio should prevent this, but be defensive.)
    master_audio = base_dir / f"{_session_stem}_master.wav"
    audio_cmd = [FFMPEG_BIN, "-y"]
    for i in range(len(manifest)):
        wav = audio_dir / f"scene_{i:03d}.wav"
        if wav.exists() and wav.stat().st_size > 0:
            audio_cmd.extend(["-i", str(wav)])
        else:
            logger.warning("[STITCH] scene_%03d.wav missing or empty — skipping from FFmpeg input.", i)
    audio_cmd.extend(["-filter_complex_script", str(filter_script), "-map", "[aout]", str(master_audio)])

    subprocess.run(audio_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ── Phase 2: Frame-Accurate Video Stitching ──
    segments_dir = base_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    clip_concat_file = segments_dir / "clips_concat.txt"

    # Check whether any real images were generated — if not, emit audio-only output.
    has_images = any(
        entry["img"].exists() and entry["img"].stat().st_size > 0
        for entry in audio_timeline
    )

    if not has_images:
        # ── Audio-only broadcast path ──────────────────────────────────────────
        import shutil as _shutil
        output_wav = base_dir / f"{_session_stem}_broadcast.wav"
        _shutil.copy2(str(master_audio), str(output_wav))
        logger.info("[*] No visuals generated — pure audio broadcast: %s", output_wav)
        _emit_render_telemetry(
            _session_stem, len(manifest), _total_tts_chars, 0, "audio_only",
            str(output_wav.absolute()),
        )
        return f"SUCCESS: Audio-Only Render Complete at {output_wav.absolute()}"

    # Compute true duration of each image on screen based on the audio overlap offsets
    with open(clip_concat_file, "w", encoding="utf-8") as f:
        for i in range(len(audio_timeline)):
            curr = audio_timeline[i]
            # Image holds until the NEXT image starts (or until its own audio ends if last)
            next_start = audio_timeline[i+1]["start_ms"] if i + 1 < len(audio_timeline) else curr["end_ms"]
            hold_dur = (next_start - curr["start_ms"]) / 1000.0
            if hold_dur <= 0:
                hold_dur = 0.1 # Failsafe

            # Format explicitly for concat demuxer
            f.write(f"file '{curr['img'].absolute().as_posix()}'\n")
            f.write(f"duration {hold_dur:.3f}\n")
        # Concat demuxer requires the last file to be repeated without a duration to seal
        f.write(f"file '{audio_timeline[-1]['img'].absolute().as_posix()}'\n")

    output_mp4 = base_dir / f"{_session_stem}_podcast.mp4"
    concat_cmd = [
        FFMPEG_BIN, "-y",
        "-f", "concat", "-safe", "0", "-i", str(clip_concat_file),
        "-i", str(master_audio),
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(output_mp4),
    ]
    subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _emit_render_telemetry(
        _session_stem, len(manifest), _total_tts_chars, _total_image_count, "video",
        str(output_mp4.absolute()), pipeline.active_image_model or "gemini-2.5-flash-image",
    )
    return f"SUCCESS: Render Complete at {output_mp4.absolute()}"


def execute_render_pipeline(
    manifest_json: str,
    session_dir: str = "",
    audio_only: bool = True,
) -> str:
    """
    Parses a Director manifest, generates audio assets (and optionally visuals)
    via Cloud APIs, then stitches via local FFmpeg.

    Args:
        manifest_json: A JSON-encoded string containing a list of scene dicts.
            Each dict MUST have 'speaker' and 'text'. 'video_prompt' is optional
            and only used when audio_only=False.
            Markdown fences (```json ... ```) are stripped automatically.
        session_dir: Absolute path to the target session output directory.
            Leave empty to use the default 05_Rendered_Media silo.
        audio_only: When True (the default), all video_prompt fields in the manifest
            are silently ignored and no images are generated. The final output is a
            WAV broadcast file. Set to False only when a video slideshow is explicitly
            required. AGENT INSTRUCTION: Never pass audio_only=False unless the user
            has specifically requested a video output.

    Returns:
        A string confirming the path of the rendered output file,
        or a TOOL_CRASH string describing the failure.
    """
    import re
    import threading

    # Strip markdown fences in case the LLM passes them into the tool argument
    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", manifest_json.strip(), flags=re.MULTILINE)

    result_container: list[str] = []

    def _thread_worker() -> None:
        try:
            # Run the async pipeline in a completely isolated thread event loop
            # to prevent SDK event loop collisions during automatic function calling.
            res = asyncio.run(_async_execute_render_pipeline(clean_json, session_dir, audio_only))
            result_container.append(res)
        except Exception as e:
            import traceback
            err_trace = traceback.format_exc()
            logger.info(f"\n[RENDER EXECUTOR CRASH]\n{err_trace}\n")
            result_container.append(f"TOOL_CRASH: {str(e)}. Tell the Architect the render tool crashed.")

    t = threading.Thread(target=_thread_worker)
    t.start()
    t.join()

    return result_container[0] if result_container else "TOOL_CRASH: Thread produced no result."


def render_podcast_audio(manifest_json: str, session_dir: str = "") -> str:
    """
    Render a podcast audio broadcast from a Director manifest JSON array.

    Accepts a manifest and produces a single WAV audio file. Image generation
    is always suppressed — this tool is strictly audio-only. The session_dir
    argument is reserved for internal runtime injection; do not pass it from
    an agent tool call.

    Args:
        manifest_json: JSON array string. Each item must contain 'speaker'
            and 'text'. Any 'video_prompt' fields are silently ignored.
            Markdown code fences (```json ... ```) are stripped automatically.
        session_dir: Reserved — injected automatically by the runtime.
            Do NOT pass this argument in an agent tool call.

    Returns:
        SUCCESS string with the absolute path of the rendered WAV file,
        or a TOOL_CRASH description on failure.
    """
    import re
    import threading

    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", manifest_json.strip(), flags=re.MULTILINE)
    result_container: list[str] = []

    def _thread_worker() -> None:
        try:
            res = asyncio.run(_async_execute_render_pipeline(clean_json, session_dir, audio_only=True))
            result_container.append(res)
        except Exception as e:
            import traceback
            err_trace = traceback.format_exc()
            logger.info(f"\n[RENDER EXECUTOR CRASH]\n{err_trace}\n")
            result_container.append(f"TOOL_CRASH: {str(e)}. Tell the Architect the render tool crashed.")

    t = threading.Thread(target=_thread_worker)
    t.start()
    t.join()


    return result_container[0] if result_container else "TOOL_CRASH: Thread produced no result."


def render_video(manifest_json: str, session_dir: str = "") -> str:
    """
    Render a video slideshow from a Director manifest JSON array.

    Generates TTS audio for each scene and an image frame from each
    'video_prompt' field, then stitches them into an MP4. Include all
    style, composition, and aesthetic guidance in the 'video_prompt' field
    itself — no defaults are applied.  The session_dir argument is reserved
    for internal runtime injection; do not pass it from an agent tool call.

    Args:
        manifest_json: JSON array string. Each scene must have 'speaker'
            and 'text'. 'video_prompt' drives the visual frame for that scene.
            Markdown code fences (```json ... ```) are stripped automatically.
        session_dir: Reserved — injected automatically by the runtime.
            Do NOT pass this argument in an agent tool call.

    Returns:
        SUCCESS string with the absolute path of the rendered MP4,
        or a TOOL_CRASH description on failure.
    """
    import re
    import threading

    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", manifest_json.strip(), flags=re.MULTILINE)
    result_container: list[str] = []

    def _thread_worker() -> None:
        try:
            res = asyncio.run(_async_execute_render_pipeline(clean_json, session_dir, audio_only=False))
            result_container.append(res)
        except Exception as e:
            import traceback
            logger.info(f"\n[RENDER EXECUTOR CRASH]\n{traceback.format_exc()}\n")
            result_container.append(f"TOOL_CRASH: {str(e)}. Tell the Architect the render tool crashed.")

    t = threading.Thread(target=_thread_worker)
    t.start()
    t.join()
    return result_container[0] if result_container else "TOOL_CRASH: Thread produced no result."


async def _async_render_single_image(prompt: str, out_path: Path) -> Path:
    """Internal: generate one image via the cloud pipeline, verbatim prompt."""
    pipeline = CloudMediaPipeline()
    return await pipeline.generate_image(prompt, out_path)


def render_image(prompt: str, output_name: str = "", session_dir: str = "") -> str:
    """
    Generate a single image from a text prompt.

    The full visual description — composition, style, aspect ratio,
    lighting, mood — belongs entirely in the prompt. No defaults are applied.

    Args:
        prompt: Complete visual description. The SCRIPTWRITER or DIRECTOR
            is responsible for all style guidance in this string.
        output_name: Filename stem for the output (no extension needed).
            Defaults to 'image_001'. Spaces are converted to underscores.
        session_dir: Reserved — injected automatically by the runtime.
            Do NOT pass this argument in an agent tool call.

    Returns:
        SUCCESS string with the absolute path of the rendered image,
        or a TOOL_CRASH description on failure.
    """
    import threading

    _name = (output_name.strip() or "image_001").replace(" ", "_")
    _base_dir = Path(session_dir) if session_dir else DATACENTER
    _base_dir.mkdir(parents=True, exist_ok=True)
    out_path = _base_dir / f"{_name}.jpg"
    result_container: list[str] = []

    def _thread_worker() -> None:
        try:
            asyncio.run(_async_render_single_image(prompt, out_path))
            result_container.append(f"SUCCESS: Image rendered at {out_path.absolute()}")
        except Exception as e:
            import traceback
            logger.info(f"\n[IMAGE RENDER CRASH]\n{traceback.format_exc()}\n")
            result_container.append(f"TOOL_CRASH: {str(e)}.")

    t = threading.Thread(target=_thread_worker)
    t.start()
    t.join()
    return result_container[0] if result_container else "TOOL_CRASH: Thread produced no result."


async def _async_render_image_batch(
    prompts: list[dict[str, Any]], out_dir: Path, concurrency: int = 3,
) -> list[str]:
    """Internal: generate multiple images concurrently, verbatim prompts."""
    pipeline = CloudMediaPipeline()
    sem = asyncio.Semaphore(concurrency)

    async def _gen_one(idx: int, item: dict[str, Any]) -> str:
        name = str(item.get("name", f"image_{idx:03d}")).replace(" ", "_")
        out_path = out_dir / f"{name}.jpg"
        async with sem:
            try:
                await pipeline.generate_image(str(item.get("prompt", "")), out_path)
                return str(out_path.absolute())
            except Exception as exc:
                logger.warning("[BATCH] Image %d ('%s') failed: %s", idx, name, exc)
                return f"FAILED:{name}"

    return list(await asyncio.gather(*[_gen_one(i, item) for i, item in enumerate(prompts)]))


def render_image_batch(prompts_json: str, session_dir: str = "") -> str:
    """
    Generate multiple images concurrently from a JSON array of prompts.

    Up to 3 images are generated in parallel; remaining entries are queued.
    Each entry controls its visual output entirely via its 'prompt' field.

    Args:
        prompts_json: JSON array of objects with 'prompt' (required) and
            'name' (optional filename stem) keys.
            Example: [{"name": "hero_shot", "prompt": "A lone figure..."}, ...]
            Markdown code fences are stripped automatically.
        session_dir: Reserved — injected automatically by the runtime.
            Do NOT pass this argument in an agent tool call.

    Returns:
        SUCCESS string with the output directory and rendered count,
        or a TOOL_CRASH description on failure.
    """
    import re
    import threading

    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", prompts_json.strip(), flags=re.MULTILINE)
    _base_dir = Path(session_dir) if session_dir else DATACENTER
    visuals_dir = _base_dir / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    result_container: list[str] = []

    def _thread_worker() -> None:
        try:
            prompts: list[dict[str, Any]] = json.loads(clean_json)
            paths = asyncio.run(_async_render_image_batch(prompts, visuals_dir))
            ok = [p for p in paths if not p.startswith("FAILED:")]
            failed = [p for p in paths if p.startswith("FAILED:")]
            msg = f"SUCCESS: {len(ok)}/{len(prompts)} images rendered to {visuals_dir.absolute()}"
            if failed:
                msg += f" | Failed: {', '.join(failed)}"
            result_container.append(msg)
        except Exception as e:
            import traceback
            logger.info(f"\n[BATCH IMAGE CRASH]\n{traceback.format_exc()}\n")
            result_container.append(f"TOOL_CRASH: {str(e)}.")

    t = threading.Thread(target=_thread_worker)
    t.start()
    t.join()
    return result_container[0] if result_container else "TOOL_CRASH: Thread produced no result."
