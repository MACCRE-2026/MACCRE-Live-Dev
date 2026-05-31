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
maccre_core/tools/audio_tools.py
==================================
Atomic, GUI-agnostic audio-processing helpers for the MACCRE Tool Registry.

Zero SDK dependency. All TTS config is returned as plain dicts ready for
the sovereign GeminiClient.generate_content() body.

Includes the VoiceProfile system for deterministic, tunable voice identities
loaded from ``02_Dynamic_Context/voice_roster.json`` at render time.
"""

import hashlib
import io
import wave
from dataclasses import dataclass, field
from typing import Any


def pack_wav_bytes(
    pcm: bytes,
    channels: int = 1,
    sample_rate: int = 24_000,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM bytes in a valid WAV container and return the full WAV blob.

    Args:
        pcm: Raw PCM audio bytes from the TTS API response.
        channels: Number of audio channels (1 = mono, 2 = stereo).
        sample_rate: Sample rate in Hz (Native TTS default: 24000).
        sample_width: Bytes per sample (2 = 16-bit).

    Returns:
        A bytes object containing a fully-formed WAV file including the RIFF
        header and audio data.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setframerate(sample_rate)
        wf.setsampwidth(sample_width)
        wf.writeframes(pcm)
    return buf.getvalue()


def make_tts_filename(speaker: str, text: str, extension: str = "mp3") -> str:
    """Generate a deterministic, filesystem-safe filename for a TTS audio clip.

    Args:
        speaker: Display name of the agent or speaker.
        text: The spoken text content (used to derive a content hash).
        extension: File extension without the leading dot. Defaults to ``"mp3"``.

    Returns:
        A string of the form ``"Speaker_Name_<hex_hash>.<extension>"``.
    """
    safe_speaker = speaker.replace(" ", "_")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{safe_speaker}_{content_hash}.{extension}"


# ── VoiceProfile System ────────────────────────────────────────────────────────

@dataclass
class VoiceProfile:
    """Deterministic voice blueprint for a named speaker in the render pipeline.

    Stores both the Gemini prebuilt voice selection and the full hierarchical
    audio prompt that governs delivery quality. Controls voice texture through
    prompt engineering — not API parameters — which is the correct mechanism for
    Gemini's instruction-following TTS models.

    Fields:
        voice_name: Gemini prebuilt voice name (e.g. "Fenrir", "Kore", "Aoede").
            Full list: Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus, Aoede,
            Callirrhoe, Autonoe, Enceladus, Iapetus, Umbriel, Algieba, Despina,
            Erinome, Algenib, Rasalghul, Laomedeia, Achernar, Alnilam, Schedar,
            Gacrux, Pulcherrima, Achird, Zubenelgenubi, Vindemiatrix, Sadachbia,
            Sadaltager, Sulafat.
        audio_profile: 2–3 sentence description of vocal texture. This is injected
            into the TTS audio prompt as the speaker's physical voice identity.
            Be specific and sensory: "gravelly baritone", "chest-resonant", etc.
        scene_context: Default setting or context for this speaker. Informs the
            emotional register of the delivery (e.g. "late-night broadcast booth").
        directors_notes: Style, pace, accent, and emotional arc defaults. Injected
            as the director's layer in the hierarchical audio prompt.
        tag_defaults: Inline audio tags always prepended to this speaker's lines
            (e.g. ["[breath]"]). Uses the confirmed Gemini TTS inline tag library.
    """
    voice_name: str
    audio_profile: str = ""
    scene_context: str = ""
    directors_notes: str = ""
    tag_defaults: list[str] = field(default_factory=list)


def load_voice_roster() -> dict[str, VoiceProfile]:
    """Load VoiceProfiles from the active project's voice_roster.json.

    Reads ``02_Dynamic_Context/voice_roster.json`` in the currently active project
    silo (resolved via ``MACCRE_ACTIVE_PROJECT`` env var). Returns an empty dict
    if no roster file exists — callers fall back to the legacy voice_map.

    voice_roster.json format::

        {
          "HOST_A": {
            "voice_name": "Fenrir",
            "audio_profile": "Deep baritone, gravelly texture...",
            "scene_context": "Late-night broadcast booth, single microphone.",
            "directors_notes": "Deliberate pace. Builds pressure through sentence.",
            "tag_defaults": ["[breath]"]
          }
        }

    Returns:
        Dict mapping speaker name (str) → VoiceProfile. Empty dict on any error.
    """
    try:
        import json as _json  # noqa: PLC0415
        from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
        roster_path = get_datacenter_path("02_Dynamic_Context") / "voice_roster.json"
        if not roster_path.exists():
            return {}
        raw: dict[str, Any] = _json.loads(roster_path.read_text(encoding="utf-8"))
        result: dict[str, VoiceProfile] = {}
        for name, data in raw.items():
            result[str(name)] = VoiceProfile(
                voice_name=str(data.get("voice_name", "Puck")),
                audio_profile=str(data.get("audio_profile", "")),
                scene_context=str(data.get("scene_context", "")),
                directors_notes=str(data.get("directors_notes", "")),
                tag_defaults=list(data.get("tag_defaults", [])),
            )
        return result
    except Exception:  # noqa: BLE001
        return {}


def build_tts_config(voice: str = "Kore") -> dict[str, Any]:
    """Build a generationConfig dict configured for Google Native TTS output.

    Returns a plain dict (no SDK dependency) suitable for the sovereign
    GeminiClient's generationConfig field. The dict matches the REST API
    shape for the AUDIO response modality.

    Use with TTS models:
        - ``gemini-2.5-flash-preview-tts``
        - ``gemini-2.5-pro-preview-tts``

    Args:
        voice: Prebuilt voice name. Verified options: Kore, Puck, Charon,
            Fenrir, Aoede.

    Returns:
        A dict with ``response_modalities`` and ``speechConfig`` keys.
    """
    return {
        "response_modalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": voice}
            }
        },
    }


def build_tts_config_from_profile(profile: VoiceProfile) -> dict[str, Any]:
    """Build a generationConfig dict from a VoiceProfile.

    Functionally identical to ``build_tts_config`` but reads the voice name
    from the VoiceProfile rather than a raw string. The audio prompt itself
    is constructed separately in ``render_executor.py`` using the profile's
    ``audio_profile``, ``scene_context``, and ``directors_notes`` fields.

    Args:
        profile: A VoiceProfile instance (from ``load_voice_roster`` or
            constructed directly).

    Returns:
        A dict with ``response_modalities`` and ``speechConfig`` keys.
    """
    return {
        "response_modalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": profile.voice_name}
            }
        },
    }


# ── Inline Tag Library Reference ──────────────────────────────────────────────
# Confirmed working Gemini TTS inline audio direction tags.
# Embed these in the 'text' field of a manifest scene dict.
# Best practice: use commas between tagged clauses for smooth delivery.
#
# Expression: [whispers], [laughs], [sighs], [gasp], [amazed], [sarcastic]
# Pacing:     [short pause], [breath], [slow down]
# Emphasis:   [emphasize] <word> [/emphasize]
#
# Example:
#   "[sighs], I warned you this would happen, [short pause] and here we are."
