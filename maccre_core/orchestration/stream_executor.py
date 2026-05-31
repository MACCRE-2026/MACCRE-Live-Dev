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
import asyncio
import threading
import subprocess
from maccre_core.logger import logger
from maccre_core.tools.render_executor import CloudMediaPipeline
from maccre_core.utils.path_resolver import get_datacenter_path

def live_stream_audio(text: str, speaker_name: str, job_id: str, node_id: str) -> None:
    """
    Submits a background TTS synthesis job mimicking real-time stream-to-speaker architecture.
    Bypasses monolithic FFmpeg stitchers for native conversational velocity.
    """
    def _worker():
        try:
            pipeline = CloudMediaPipeline()
            
            # Temporary staging bin for live clips
            tmp_dir = get_datacenter_path("05_Rendered_Media", f"live_stream_{job_id}")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            wav_path = tmp_dir / f"{node_id}_live.wav"
            
            # Execute async Google TTS natively
            asyncio.run(pipeline.generate_audio(text, speaker_name, wav_path))
            
            # Invoke physical hardware playback
            if wav_path.exists():
                logger.info(f"🎤 [LIVE STREAM] Playing audio for {speaker_name} on {node_id}...")
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav_path)],
                    check=False
                )
        except Exception as e:
            logger.warning(f"Live Audio Stream Failed (Non-Fatal): {str(e)}")

    # Daemonize to prevent blocking the swarm engine
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
