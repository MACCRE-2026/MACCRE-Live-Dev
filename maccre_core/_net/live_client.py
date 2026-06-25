from __future__ import annotations

import logging
from typing import Callable, Any

# SOVEREIGNTY EXCEPTION: Live API WebSocket protocol has no REST equivalent
from google import genai
# SOVEREIGNTY EXCEPTION: Live API WebSocket protocol has no REST equivalent
from google.genai import types

_log = logging.getLogger(__name__)

class GeminiLiveClient:
    """
    Stream 4a: Live API WebSocket Wrapper.
    Uses the official google-genai SDK to establish a stateful, bi-directional
    WebSocket connection to the Gemini Live API.
    
    Currently locked to TEXT modalities to ensure full compatibility with 
    Termux/Android environments (bypassing pyaudio/sounddevice constraints).
    """
    def __init__(self, key_provider: Callable[[], str | None], model: str = "gemini-2.0-flash") -> None:
        self._key_provider = key_provider
        self.model = model
        
    async def run_session(self, system_instruction: str, run_loop_cb: Callable[[Any], Any]) -> None:
        """Mount the WebSocket connection and run the provided async callback with the session."""
        config = types.LiveConnectConfig(
            system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
            response_modalities=[types.Modality.TEXT]
        )
        
        raw_key = self._key_provider()
        if not raw_key:
            raise ValueError("No API key provided for LiveClient.")
            
        client = genai.Client(api_key=raw_key)
        try:
            async with client.aio.live.connect(model=self.model, config=config) as session:
                _log.info(f"[LiveClient] WebSocket bound to {self.model}")
                await run_loop_cb(session)
        finally:
            from maccre_core.orchestration.universal_vault import wipe_string  # noqa: PLC0415
            wipe_string(raw_key)
