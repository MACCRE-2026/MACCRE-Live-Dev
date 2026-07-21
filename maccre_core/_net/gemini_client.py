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
maccre_core/_net/gemini_client.py
==================================
Phase 4 / 4.1 — Sovereign Gemini HTTP Client (Full Surface).

Zero-dependency replacement for the ``google-genai`` SDK. Uses only
Python standard library: ``urllib.request``, ``urllib.error``, ``json``,
``ssl``, ``base64``, ``pathlib``, ``mimetypes``.

Full API surface implemented:
  - generateContent        — text, multi-turn, tools, search grounding
  - streamGenerateContent  — server-sent NDJSON chunks → token generator
  - embedContent           — single embedding vector
  - batchEmbedContents     — multiple embeddings in one round-trip
  - File API upload        — resumable upload for images/audio/video/docs
  - File API get/delete    — file metadata management
  - Inline multimodal      — image/audio/video as base64 inline parts
  - Model list             — enumerate available models (used by ModelRegistry)

REST base:
  https://generativelanguage.googleapis.com/v1beta/

Doctrine: ZERO third-party imports. No requests, no httpx, no SDK.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Generator, Callable

from maccre_core._net.client_interface import InferenceClient, InferenceResponse, EmbeddingResult
from maccre_core.orchestration.universal_vault import wipe_string

# ── Constants ─────────────────────────────────────────────────────────────────

_BASE_URL    = "https://generativelanguage.googleapis.com/v1beta/models"
_FILES_URL   = "https://generativelanguage.googleapis.com/v1beta/files"
_UPLOAD_URL  = "https://generativelanguage.googleapis.com/upload/v1beta/files"
_TIMEOUT     = 300   # seconds
_STREAM_TIMEOUT = 600  # streaming can legitimately run longer


# ── Response containers ───────────────────────────────────────────────────────

class GeminiResponse(InferenceResponse):
    """Lightweight parsed response from generateContent."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    @property
    def text(self) -> str:
        """Text parts from the first candidate, ignoring thought blocks, with appended search grounding citations."""
        try:
            candidate = self._body["candidates"][0]
            texts = []
            for part in candidate["content"]["parts"]:
                if "text" in part and not part.get("thought"):
                    texts.append(str(part["text"]))
            
            base_text = "\n".join(texts)
                    
            grounding = candidate.get("groundingMetadata", {})
            chunks = grounding.get("groundingChunks", [])
            
            if chunks:
                base_text += "\n\n### Search Grounding Sources:\n"
                for i, chunk in enumerate(chunks, 1):
                    web = chunk.get("web", {})
                    title = web.get("title", "Unknown Title")
                    uri = web.get("uri", "No URI provided")
                    base_text += f"[{i}] {title}\n    {uri}\n"
                    
            return base_text
        except (KeyError, IndexError, TypeError):
            pass
        return ""

    @property
    def scratchpad_thought(self) -> str:
        """Extracts native 'thought' blocks from Gemini Thinking models."""
        try:
            candidate = self._body["candidates"][0]
            thoughts = []
            for part in candidate["content"]["parts"]:
                if "thought" in part:
                    if isinstance(part["thought"], str):
                        thoughts.append(part["thought"])
                    elif part["thought"] is True and "text" in part:
                        thoughts.append(str(part["text"]))
            return "\n\n".join(thoughts)
        except (KeyError, IndexError, TypeError):
            pass
        return ""

    @property
    def function_call(self) -> tuple[str, dict[str, Any]] | None:
        """(name, args) if model returned a function call, else None."""
        try:
            for part in self._body["candidates"][0]["content"]["parts"]:
                if "functionCall" in part:
                    fc = part["functionCall"]
                    name: str = fc.get("name", "")
                    args: dict[str, Any] = fc.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    return name, args
        except (KeyError, IndexError, TypeError):
            pass
        return None

    @property
    def prompt_tokens(self) -> int:
        try:
            return int(self._body["usageMetadata"]["promptTokenCount"])
        except (KeyError, TypeError, ValueError):
            return 0

    @property
    def candidate_tokens(self) -> int:
        try:
            return int(self._body["usageMetadata"]["candidatesTokenCount"])
        except (KeyError, TypeError, ValueError):
            return 0

    @property
    def raw(self) -> dict[str, Any]:
        return self._body


class EmbeddingResponse(EmbeddingResult):
    """Response from embedContent."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    @property
    def values(self) -> list[float]:
        """The embedding vector as a list of floats."""
        try:
            return list(self._body["embedding"]["values"])
        except (KeyError, TypeError):
            return []

    @property
    def raw(self) -> dict[str, Any]:
        return self._body


class FileMetadata:
    """Metadata returned by the File API."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    @property
    def name(self) -> str:
        """Resource name, e.g. 'files/abc123'."""
        return str(self._body.get("name", ""))

    @property
    def uri(self) -> str:
        """Publicly-accessible URI to reference in content parts."""
        return str(self._body.get("uri", ""))

    @property
    def mime_type(self) -> str:
        return str(self._body.get("mimeType", "application/octet-stream"))

    @property
    def state(self) -> str:
        """'ACTIVE', 'PROCESSING', or 'FAILED'."""
        return str(self._body.get("state", "UNKNOWN"))

    @property
    def raw(self) -> dict[str, Any]:
        return self._body


# ── Request builders ──────────────────────────────────────────────────────────

def _build_request_body(
    contents: list[dict[str, Any]],
    system_instruction: str | None,
    temperature: float,
    tool_declarations: list[dict[str, Any]] | None,
    search_grounding: bool,
    disable_auto_function_calling: bool,
    response_schema: dict[str, Any] | None = None,
    safety_settings: list[dict[str, str]] | None = None,
    max_output_tokens: int | None = None,
    thinking_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"contents": contents}

    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    gen_config: dict[str, Any] = {"temperature": temperature}
    if max_output_tokens is not None:
        gen_config["maxOutputTokens"] = max_output_tokens
    if thinking_config is not None:
        tc = dict(thinking_config)
        tc["includeThoughts"] = True
        gen_config["thinkingConfig"] = tc
    body["generationConfig"] = gen_config

    if response_schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = response_schema

    tools: list[dict[str, Any]] = []
    if tool_declarations:
        tools.append({"functionDeclarations": tool_declarations})
        if search_grounding:
            # Gemini API rejects combining google_search with functionDeclarations.
            # Function calling takes priority — it's user-configured and more specific.
            import logging as _logging  # noqa: PLC0415
            _logging.getLogger("maccre_core").warning(
                "[GeminiClient] Search grounding disabled for this call — "
                "Gemini API does not allow google_search + functionDeclarations "
                "in the same request. Function calling takes priority."
            )
    elif search_grounding:
        tools.append({"googleSearch": {}})
    if tools:
        body["tools"] = tools

    tool_config: dict[str, Any] = {}
    if disable_auto_function_calling and tool_declarations:
        tool_config["functionCallingConfig"] = {"mode": "AUTO"}
    if tool_config:
        body["toolConfig"] = tool_config

    if safety_settings:
        body["safetySettings"] = safety_settings

    return body

def _build_cache_request_body(
    model: str,
    contents: list[dict[str, Any]],
    system_instruction: str | None,
    ttl_seconds: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": f"models/{model.removeprefix('models/')}",
        "contents": contents,
        "ttl": f"{ttl_seconds}s"
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    return body

def _make_req(
    url: str,
    data: bytes | None = None,
    method: str = "POST",
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
) -> urllib.request.Request:
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
        "User-Agent": "MACCREv2-SovereignClient/4.1 (Python urllib)",
    }
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(url, data=data, method=method, headers=headers)


def _call(req: urllib.request.Request, ctx: ssl.SSLContext, timeout: int = _TIMEOUT) -> dict[str, Any]:
    """Execute an HTTP request and return the parsed JSON body."""
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise urllib.error.HTTPError(
            url=exc.url, code=exc.code,
            msg=f"Gemini API {exc.code}: {err_body[:400]}",
            hdrs=exc.headers, fp=None,
        ) from exc

    try:
        result: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"[GeminiClient] JSON parse failure: {exc}. Raw: {raw[:200]}"
        ) from exc

    if "error" in result:
        err = result["error"]
        raise RuntimeError(
            f"[GeminiClient] API error {err.get('code','?')}: {err.get('message', str(err))}"
        )
    return result


# ── Multimodal content helpers ────────────────────────────────────────────────

def inline_part(file_path: str | Path, mime_type: str | None = None) -> dict[str, Any]:
    """Build an inline data part from a local file (image, audio, video, PDF).

    The file is base64-encoded and embedded directly in the request body.
    Use for files < ~20 MB; use upload_file() for larger assets.

    Args:
        file_path: Path to the local file.
        mime_type: MIME type override. Auto-detected from extension if None.

    Returns:
        A part dict ready for inclusion in a contents list.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"[GeminiClient] File not found: {path}")
    detected, _ = mimetypes.guess_type(str(path))
    resolved_mime = mime_type or detected or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"inlineData": {"mimeType": resolved_mime, "data": encoded}}


def file_uri_part(uri: str, mime_type: str) -> dict[str, Any]:
    """Build a content part referencing a File API URI.

    Use after upload_file() — pass FileMetadata.uri and FileMetadata.mime_type.
    """
    return {"fileData": {"mimeType": mime_type, "fileUri": uri}}


def text_part(text: str) -> dict[str, Any]:
    """Build a plain text content part."""
    return {"text": text}


def user_turn(*parts: dict[str, Any] | str) -> dict[str, Any]:
    """Build a user-role content turn from one or more parts.

    Parts may be dicts (from inline_part / file_uri_part / text_part)
    or plain strings (automatically wrapped as text parts).
    """
    resolved = [text_part(p) if isinstance(p, str) else p for p in parts]
    return {"role": "user", "parts": resolved}


def model_turn(text: str) -> dict[str, Any]:
    """Build a model-role content turn."""
    return {"role": "model", "parts": [{"text": text}]}


def history_to_contents(
    history: list[dict[str, str]],
    current_user_text: str,
) -> list[dict[str, Any]]:
    """Convert maccre_router conversation_history → Gemini contents list."""
    contents: list[dict[str, Any]] = []
    for turn in history:
        gemini_role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": turn.get("text", "")}]})
    contents.append(user_turn(current_user_text))
    return contents


# ── Error classification ──────────────────────────────────────────────────────

def is_transient_error(exc: Exception) -> bool:
    err = str(exc)
    return any(code in err for code in ("503", "500", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


def is_fatal_error(exc: Exception) -> bool:
    err = str(exc)
    return any(code in err for code in ("404", "NOT_FOUND", "INVALID_ARGUMENT", "400"))


# ── Core client ───────────────────────────────────────────────────────────────

class GeminiClient(InferenceClient):
    """Sovereign Gemini HTTP client — zero SDK dependency.

    Covers the full generation/embedding/file surface of the Google
    Generative Language REST API using only Python stdlib.

    Methods
    -------
    generate_content()         — standard request/response generation
    stream_generate_content()  — streaming generation, yields text chunks
    embed_content()            — single text embedding
    batch_embed_contents()     — batch text embeddings
    upload_file()              — upload a local file to the File API
    get_file()                 — retrieve File API metadata by name
    delete_file()              — delete a File API upload
    list_models()              — enumerate available models (for ModelRegistry)
    """

    def __init__(self, key_provider: Callable[[], str | None]) -> None:
        self._key_provider = key_provider
        self._ssl = ssl.create_default_context()

    def _url(self, model: str, action: str) -> str:
        clean = model.removeprefix("models/")
        return f"{_BASE_URL}/{clean}:{action}"

    # ── Text Generation ───────────────────────────────────────────────────────

    def generate_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        tool_declarations: list[dict[str, Any]] | None = None,
        search_grounding: bool = False,
        disable_auto_function_calling: bool = True,
        response_schema: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        max_output_tokens: int | None = None,
        cached_content_uri: str | None = None,
        thinking_config: dict[str, Any] | None = None,
    ) -> GeminiResponse:
        """Standard (non-streaming) generate call.

        Args:
            model: Model name, e.g. 'gemini-2.5-flash'. 'models/' prefix handled.
            contents: List of content turns (use user_turn/model_turn helpers).
            system_instruction: System prompt string.
            temperature: 0.0–2.0 sampling temperature.
            tool_declarations: OpenAPI function declaration dicts, or None.
            search_grounding: Enable Google Search live grounding.
            disable_auto_function_calling: Force model to return raw functionCall.
            cached_content_uri: Optional URI of pre-cached context.

        Returns:
            GeminiResponse with .text, .function_call, .prompt_tokens, etc.
        """
        body = _build_request_body(
            contents, system_instruction, temperature,
            tool_declarations, search_grounding, disable_auto_function_calling,
            response_schema=response_schema,
            safety_settings=safety_settings,
            max_output_tokens=max_output_tokens,
            thinking_config=thinking_config,
        )
        if cached_content_uri:
            body["cachedContent"] = cached_content_uri
            
        raw_key = self._key_provider()
        try:
            req = _make_req(
                self._url(model, "generateContent"),
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                extra_headers={"x-goog-api-key": raw_key} if raw_key else None
            )
            return GeminiResponse(_call(req, self._ssl))
        finally:
            if raw_key:
                wipe_string(raw_key)

    def stream_generate_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        tool_declarations: list[dict[str, Any]] | None = None,
        search_grounding: bool = False,
        response_schema: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        max_output_tokens: int | None = None,
        cached_content_uri: str | None = None,
    ) -> Generator[str, None, None]:
        """Streaming generation — yields text tokens as they arrive.

        The Gemini streaming endpoint returns newline-delimited JSON objects,
        each matching the standard generateContent response shape. Each chunk
        may contain one or more text parts. This method yields the text from
        each chunk as soon as it arrives.

        Usage:
            for token in client.stream_generate_content(model, contents):
                print(token, end="", flush=True)

        Yields:
            str — text fragments from each NDJSON chunk.
        """
        body = _build_request_body(
            contents, system_instruction, temperature,
            tool_declarations, search_grounding, False,
            response_schema=response_schema,
            safety_settings=safety_settings,
            max_output_tokens=max_output_tokens,
        )
        if cached_content_uri:
            body["cachedContent"] = cached_content_uri
            
        url = self._url(model, "streamGenerateContent") + "?alt=sse"
        raw_key = self._key_provider()
        req = _make_req(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), extra_headers={"x-goog-api-key": raw_key} if raw_key else None)

        try:
            with urllib.request.urlopen(req, context=self._ssl, timeout=_STREAM_TIMEOUT) as resp:
                buffer = b""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    # SSE lines start with "data: "; split on newline
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8", errors="replace").strip()
                        if not line_str.startswith("data:"):
                            continue
                        payload = line_str[5:].strip()
                        if payload in ("", "[DONE]"):
                            continue
                        try:
                            obj: dict[str, Any] = json.loads(payload)
                            for part in obj.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                                if "text" in part:
                                    yield str(part["text"])
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"[GeminiClient] Stream error {exc.code}: {err_body[:300]}") from exc
        finally:
            if raw_key:
                wipe_string(raw_key)

    # ── Embeddings ────────────────────────────────────────────────────────────

    def embed_content(
        self,
        model: str,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> EmbeddingResponse:
        """Embed a single text string.

        Args:
            model: Embedding model, e.g. 'text-embedding-004'.
            text: The text to embed.
            task_type: 'RETRIEVAL_DOCUMENT', 'RETRIEVAL_QUERY',
                       'SEMANTIC_SIMILARITY', 'CLASSIFICATION', 'CLUSTERING'.

        Returns:
            EmbeddingResponse with .values (list[float]).
        """
        body = {
            "model": f"models/{model.removeprefix('models/')}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
        }
        raw_key = self._key_provider()
        try:
            req = _make_req(
                self._url(model, "embedContent"),
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                extra_headers={"x-goog-api-key": raw_key} if raw_key else None
            )
            return EmbeddingResponse(_call(req, self._ssl, timeout=30))
        finally:
            if raw_key:
                wipe_string(raw_key)

    def batch_embed_contents(
        self,
        model: str,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[EmbeddingResponse]:
        """Embed multiple texts in one API round-trip.

        Args:
            model: Embedding model name.
            texts: List of strings to embed.
            task_type: Embedding task type (same options as embed_content).

        Returns:
            List of EmbeddingResponse objects, one per input text.
        """
        model_path = f"models/{model.removeprefix('models/')}"
        body = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                }
                for t in texts
            ]
        }
        raw_key = self._key_provider()
        try:
            req = _make_req(
                self._url(model, "batchEmbedContents"),
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                extra_headers={"x-goog-api-key": raw_key} if raw_key else None
            )
            result = _call(req, self._ssl)
            return [EmbeddingResponse({"embedding": e}) for e in result.get("embeddings", [])]
        finally:
            if raw_key:
                wipe_string(raw_key)

    # ── File API ──────────────────────────────────────────────────────────────

    def upload_file(
        self,
        file_path: str | Path,
        mime_type: str | None = None,
        display_name: str | None = None,
    ) -> FileMetadata:
        """Upload a local file to the Gemini File API.

        Performs a single-request multipart upload (suitable for files up to
        ~20 MB). For larger files, the API supports resumable uploads but that
        is an uncommon edge case for this codebase.

        The returned FileMetadata.uri can be passed to file_uri_part() to
        reference the file in subsequent generateContent calls.

        Args:
            file_path: Local path to the file.
            mime_type: Override MIME type. Auto-detected from extension if None.
            display_name: Human-readable label shown in File API listings.

        Returns:
            FileMetadata with .name, .uri, .mime_type, .state.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"[GeminiClient] File not found: {path}")

        detected, _ = mimetypes.guess_type(str(path))
        resolved_mime = mime_type or detected or "application/octet-stream"
        file_bytes = path.read_bytes()

        # ── Build multipart body ──────────────────────────────────────────────
        boundary = "maccre_sovereign_boundary_v4"
        meta: dict[str, Any] = {"file": {"displayName": display_name or path.name}}
        meta_json = json.dumps(meta, ensure_ascii=False).encode("utf-8")

        parts = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n\r\n"
        ).encode("utf-8")
        parts += meta_json
        parts += f"\r\n--{boundary}\r\n".encode("utf-8")
        parts += f"Content-Type: {resolved_mime}\r\n\r\n".encode("utf-8")
        parts += file_bytes
        parts += f"\r\n--{boundary}--\r\n".encode("utf-8")

        url = f"{_UPLOAD_URL}"
        raw_key = self._key_provider()
        try:
            req = _make_req(
                url, data=parts,
                content_type=f"multipart/related; boundary={boundary}",
                extra_headers={"x-goog-api-key": raw_key} if raw_key else None
            )
            result = _call(req, self._ssl)
            return FileMetadata(result.get("file", result))
        finally:
            if raw_key:
                wipe_string(raw_key)

    def get_file(self, name: str) -> FileMetadata:
        """Retrieve file metadata by resource name (e.g. 'files/abc123').

        Args:
            name: File resource name. The 'files/' prefix is handled.

        Returns:
            FileMetadata with current .state (poll until 'ACTIVE' after upload).
        """
        clean = name.removeprefix("files/")
        url = f"{_FILES_URL}/{clean}"
        raw_key = self._key_provider()
        try:
            req = _make_req(url, method="GET", extra_headers={"x-goog-api-key": raw_key} if raw_key else None)
            req.data = None
            return FileMetadata(_call(req, self._ssl))
        finally:
            if raw_key:
                wipe_string(raw_key)

    def delete_file(self, name: str) -> None:
        """Delete a File API upload by resource name.

        Args:
            name: File resource name, e.g. 'files/abc123'.
        """
        clean = name.removeprefix("files/")
        url = f"{_FILES_URL}/{clean}"
        raw_key = self._key_provider()
        try:
            req = _make_req(url, method="DELETE", extra_headers={"x-goog-api-key": raw_key} if raw_key else None)
            req.data = None
            try:
                with urllib.request.urlopen(req, context=self._ssl, timeout=_TIMEOUT) as resp:
                    resp.read()  # DELETE returns empty 200
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"[GeminiClient] delete_file {exc.code}: {err_body[:200]}") from exc
        finally:
            if raw_key:
                wipe_string(raw_key)

    # ── Context Caching API ───────────────────────────────────────────────────

    def create_cached_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Create a cached context payload on Google's servers.

        Args:
            model: The base model to use (e.g., 'gemini-1.5-pro-001').
            contents: The context to cache.
            system_instruction: Optional system instruction to cache alongside.
            ttl_seconds: Time-to-live for the cache in seconds.

        Returns:
            The resource URI string (e.g., 'cachedContents/abc123xyz').
        """
        body = _build_cache_request_body(model, contents, system_instruction, ttl_seconds)
        url = "https://generativelanguage.googleapis.com/v1beta/cachedContents"
        raw_key = self._key_provider()
        try:
            req = _make_req(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), extra_headers={"x-goog-api-key": raw_key} if raw_key else None)
            result = _call(req, self._ssl, timeout=120)
            return str(result.get("name", ""))
        finally:
            if raw_key:
                wipe_string(raw_key)

    # ── Model listing (used by ModelRegistry) ─────────────────────────────────

    def list_models(self, page_size: int = 100) -> list[dict[str, Any]]:
        """Enumerate available models from the live API.

        Returns the raw model dicts from the API. Each dict contains at minimum:
          - name: 'models/gemini-2.5-flash'
          - supportedGenerationMethods: ['generateContent', 'streamGenerateContent']
          - displayName, description, inputTokenLimit, outputTokenLimit

        Args:
            page_size: Max models per page (API cap is typically 100).

        Returns:
            List of model dicts. Combined across pages automatically.
        """
        models: list[dict[str, Any]] = []
        page_token: str | None = None
        raw_key = self._key_provider()
        try:
            while True:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models"
                    f"?pageSize={page_size}"
                )
                if page_token:
                    url += f"&pageToken={page_token}"

                req = _make_req(url, method="GET", extra_headers={"x-goog-api-key": raw_key} if raw_key else None)
                req.data = None

                result = _call(req, self._ssl)
                models.extend(result.get("models", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            return models
        finally:
            if raw_key:
                wipe_string(raw_key)
