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
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        
    async def run_session(self, system_instruction: str, run_loop_cb: Callable[[Any], Any]) -> None:
        """Mount the WebSocket connection and run the provided async callback with the session."""
        config = types.LiveConnectConfig(
            system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
            response_modalities=[types.Modality.TEXT]
        )
        
        async with self.client.aio.live.connect(model=self.model, config=config) as session:
            _log.info(f"[LiveClient] WebSocket bound to {self.model}")
            await run_loop_cb(session)
