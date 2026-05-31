# Handover Report: Resolving Dual Router Ambiguity

**Target Agent:** The Primary Engineering Agent for EXO-GANS
**Context:** System Audit flagged a critical ambiguity between `UniversalRouter` and `OmniDaemon`/`AgentRouter`.

## The Architectural Nuance
In the MACCREv2 architecture, the inference pipeline is meant to be completely "Sovereign"—meaning zero third-party SDK dependencies (like `google-genai` or `httpx`). 

Currently, there are two parallel sovereign pipelines:
1. **`UniversalRouter` + `GeminiClient`:** This is the hardened, feature-complete pipeline. `GeminiClient` is a bespoke, raw `urllib` REST client that perfectly maps Google's `v1beta` JSON schemas. `UniversalRouter` wraps this client with advanced telemetry, dynamic failover tracking via `ModelSentinel`, and FinOps cost logging to the Triune SQLite databases.
2. **`AgentRouter` + `OmniDaemon`:** This is the pipeline currently handling Nexus UI chats. However, `OmniDaemon` was written as a *separate* raw REST client. It uses a barebones `urllib` implementation that **bypasses** the Sentinel health checks, skips failover routing, and drops FinOps DB tracking.

**The Directive:** The user loves the zero-dependency, bespoke REST approach. We are NOT reverting to the official Google SDK. Instead, we are consolidating the architecture so that all routes pass through the hardened `UniversalRouter` and `GeminiClient`.

## Execution Blueprint for the Next Agent

When you assume control, execute the following two file modifications exactly as outlined below:

### 1. Wire AgentRouter Directly to UniversalRouter
**Target:** `maccre_core/maccre_router.py`

You must remove `AgentRouter`'s reliance on `OmniDaemon` so that Nexus chats get full FinOps telemetry and failover support.

**Action:**
1. In `AgentRouter.__init__`, replace `self._daemon = OmniDaemon()` with:
   ```python
   from maccre_core.maccre_router import UniversalRouter
   self._router = UniversalRouter()
   ```
2. In `AgentRouter.chat()`, replace the `self._daemon.generate(...)` block with:
   ```python
   try:
       # Replaces OmniDaemon logic natively with the Sovereign UniversalRouter
       raw_output, _cost = self._router.generate(
           model_name=effective_model,
           payload=full_message,
           system_prompt=_SCHEMA_INSTRUCTION,
           tools_str="",
           temperature=0.7,
           response_schema=AgentResponse
       )
       
       return self._extract_and_log(raw_output, agent_name, session_id)
   except Exception as exc:
       return f"FATAL ERROR: UniversalRouter Generation Failed - {exc}"
   ```

### 2. Update OmniDaemon to use GeminiClient for Parity
**Target:** `maccre_core/_net/omnidaemon.py`

There may be legacy scripts (like `tests/ouroboros_monitor.py`) that still instantiate `OmniDaemon` directly. To ensure these scripts achieve network parity (retry logic, proper error bubbling), `OmniDaemon`'s cloud routing must be refactored to use `GeminiClient` instead of its duplicate `urllib` code.

**Action:**
Replace the entire `_route_cloud` method with the following:
```python
    def _route_cloud(self, prompt: str, model_id: str, schema: Optional[Type[Any]], system_instruction: str, temperature: float) -> str:
        """Route to Google Generative Language Engine using the sovereign GeminiClient."""
        if not self.api_key:
            raise ValueError("No API key available for cloud routing.")
            
        from maccre_core._net.gemini_client import GeminiClient, user_turn
        client = GeminiClient(api_key=self.api_key)
        
        resolved_schema = _dataclass_to_json_schema(schema) if schema else None
        
        res = client.generate_content(
            model=model_id,
            contents=[user_turn(prompt)],
            system_instruction=system_instruction or None,
            temperature=temperature,
            response_schema=resolved_schema
        )
        return res.text
```

### Conclusion
By executing these two edits, you will successfully collapse the Dual Router Ambiguity into a single, unified, sovereign REST pipeline. Nexus will regain failover and telemetry, and the MACCRE architecture will remain 100% dependency-free.
