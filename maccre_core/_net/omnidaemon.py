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
maccre_core/_net/omnidaemon.py
==============================
Sovereign Network Orchestrator for MACCREv2.

Replaces the google-genai SDK and Pydantic entirely.
Dynamically routes inference to localhost (Gemma via Ollama) or 
Cloud (Gemini API) based on active environment probing.
"""
import dataclasses
import json
import urllib.request
import urllib.error
from typing import Any, Type, Optional

from maccre_core._net.environment_probe import get_environment_matrix
from maccre_core.schemas.sovereign_schema import dict_to_dataclass, SchemaValidationError
from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.logger import logger

def _dataclass_to_json_schema(cls: Type[Any]) -> dict[str, Any]:
    """Dynamically converts a Sovereign Schema dataclass to OpenAI/Google JSON schema format."""
    if not dataclasses.is_dataclass(cls):
        raise TypeError("Target must be a Sovereign dataclass.")
        
    properties = {}
    required = []
    
    for field in dataclasses.fields(cls):
        # Determine strict type
        t_name = getattr(field.type, "__name__", str(field.type)).lower()
        if "str" in t_name:
            json_type = "string"
        elif "int" in t_name:
            json_type = "integer"
        elif "float" in t_name:
            json_type = "number"
        elif "bool" in t_name:
            json_type = "boolean"
        elif "list" in t_name:
            json_type = "array"  # Very simplified for now
        elif "dict" in t_name:
            json_type = "object"
        else:
            json_type = "string"  # Fallback
        
        desc = field.metadata.get("description", "")
        properties[field.name] = {"type": json_type, "description": desc}
        
        # If it doesn't have a default, it's required
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            required.append(field.name)
            
    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


class OmniDaemon:
    """The central inference driver. Uses pure urllib to execute the Strangler Fig routing."""
    
    def __init__(self):
        self.matrix = get_environment_matrix()
        self.api_key = get_provider_credential("MACCRE_Sovereign")
        
    def _route_local(self, prompt: str, schema: Optional[Type[Any]], system_instruction: str, temperature: float) -> str:
        """Route entirely locally to Ollama."""
        # Hardcoded to use gemma3:latest or similar assuming Ollama structure
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "gemma", # Fallback local
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "options": {"temperature": temperature}
        }
        
        if schema:
            payload["format"] = _dataclass_to_json_schema(schema)
            
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read().decode('utf-8'))
                return res.get("response", "")
        except Exception as e:
            logger.error(f"[OmniDaemon] Local Reroute Failed: {e}")
            raise

    def _route_edge(self, prompt: str, model_id: str, schema: Optional[Type[Any]], system_instruction: str, temperature: float) -> str:
        """Route to Edge Device (Personal Cloud) using OpenAI compatible REST."""
        import os
        url = os.environ.get("MACCRE_EDGE_URL", "http://127.0.0.1:8080/v1/chat/completions")
        
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "stream": False
        }
        
        if schema:
            # Tell the Edge LLM to return JSON
            payload["response_format"] = {"type": "json_object"}
            
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer edge-token")
        
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read().decode('utf-8'))
                return res.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"[OmniDaemon] Edge Routing Failed to {url}: {e}")
            raise

    def _route_cloud(self, prompt: str, model_id: str, schema: Optional[Type[Any]], system_instruction: str, temperature: float) -> str:
        """Route to Google Generative Language Engine using the sovereign GeminiClient."""
        if not self.api_key:
            raise ValueError("No API key available for cloud routing.")

        from maccre_core._net.gemini_client import GeminiClient, user_turn  # noqa: PLC0415
        client = GeminiClient(key_provider=lambda: get_provider_credential("MACCRE_Sovereign"))

        resolved_schema = _dataclass_to_json_schema(schema) if schema else None

        res = client.generate_content(
            model=model_id,
            contents=[user_turn(prompt)],
            system_instruction=system_instruction or None,
            temperature=temperature,
            response_schema=resolved_schema,
        )
        return res.text

    def generate(self, 
                 prompt: str, 
                 model_id: str = "gemini-3.1-pro-preview", 
                 schema: Optional[Type[Any]] = None, 
                 system_instruction: str = "", 
                 temperature: float = 0.7,
                 compute_tier: str = "cloud") -> Any:
        """"""
        # 1. Evaluate Routing
        is_local = (compute_tier == "local") or (compute_tier == "hybrid" and self.matrix["ollama_active"])
        raw_output = ""
        
        try:
            if compute_tier == "edge":
                logger.info(f"[OmniDaemon] Active Routing -> EDGE ({model_id})")
                raw_output = self._route_edge(prompt, model_id, schema, system_instruction, temperature)
            elif is_local:
                logger.info("[OmniDaemon] Active Routing -> LOCAL GPU (Gemma)")
                raw_output = self._route_local(prompt, schema, system_instruction, temperature)
            else:
                logger.info(f"[OmniDaemon] Active Routing -> CLOUD ({model_id})")
                raw_output = self._route_cloud(prompt, model_id, schema, system_instruction, temperature)
        except urllib.error.URLError as e:
            if compute_tier == "hybrid" and is_local:
                logger.warning(f"[OmniDaemon] Local GPU Failed ({e}), routing to CLOUD.")
                raw_output = self._route_cloud(prompt, model_id, schema, system_instruction, temperature)
            else:
                raise
                
        # 2. Strict Cast Schema if requested
        if schema:
            try:
                # Often responses contain markdown wrapping (```json ... ```)
                clean_raw = raw_output.strip()
                if clean_raw.startswith("```json"):
                    clean_raw = clean_raw[7:]
                if clean_raw.startswith("```"):
                    clean_raw = clean_raw[3:]
                if clean_raw.endswith("```"):
                    clean_raw = clean_raw[:-3]
                
                raw_dict = json.loads(clean_raw.strip())
                return dict_to_dataclass(schema, raw_dict)
            except Exception as e:
                logger.error(f"[OmniDaemon] Schema Strict Cast Failure: {e}")
                raise SchemaValidationError(f"Could not map output to {schema.__name__}: {e}")
                
        return raw_output
