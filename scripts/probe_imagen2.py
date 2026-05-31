"""
scripts/probe_imagen2.py
Test the live Imagen 4 models with the correct endpoint.
"""
import urllib.request
import urllib.error
import json
import ssl
import sys

sys.path.insert(0, "B:/MACCREv2")
from maccre_core.orchestration.windows_vault import get_native_credential

key = str(get_native_credential("MACCRE_Sovereign")).strip()
ssl_ctx = ssl.create_default_context()

# The registry returned 'models/imagen-4.0-generate-001' etc.
# Strip the 'models/' prefix for the URL path
image_models = [
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
]

gemini_image_models = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
]

body_imagen = json.dumps({
    "instances": [{"prompt": "A golden ring on a stone, glowing, epic fantasy"}],
    "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
}).encode("utf-8")

body_gen_img = json.dumps({
    "contents": [{"role": "user", "parts": [
        {"text": "Generate an image of a golden ring on a stone, glowing, epic fantasy"}
    ]}],
    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
}).encode("utf-8")

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

print("=== Testing Imagen 4 :generateImages ===")
for m in image_models:
    for action, body in [("generateImages", body_imagen), ("generateContent", body_gen_img)]:
        url = f"{BASE}/{m}:{action}?key={key}"
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as r:
                resp = json.loads(r.read().decode())
                keys = list(resp.keys())
                # Check for image data
                has_image = False
                for pred in resp.get("predictions", []):
                    if pred.get("bytesBase64Encoded"):
                        has_image = True
                for c in resp.get("candidates", []):
                    for p in c.get("content", {}).get("parts", []):
                        if p.get("inlineData", {}).get("mimeType", "").startswith("image/"):
                            has_image = True
                print(f"  OK  {m}:{action} keys={keys} has_image={has_image}")
        except urllib.error.HTTPError as e:
            body_preview = b""
            try:
                body_preview = e.read()[:300]
            except Exception:
                pass
            print(f"  {e.code} {m}:{action} -> {body_preview[:200]}")
        except Exception as e:
            print(f"  ERR {m}:{action}: {e}")

print("\n=== Testing Gemini image models :generateContent ===")
for m in gemini_image_models:
    url = f"{BASE}/{m}:generateContent?key={key}"
    req = urllib.request.Request(
        url, data=body_gen_img, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as r:
            resp = json.loads(r.read().decode())
            keys = list(resp.keys())
            has_image = False
            for c in resp.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    if p.get("inlineData", {}).get("mimeType", "").startswith("image/"):
                        has_image = True
            print(f"  OK  {m}:generateContent keys={keys} has_image={has_image}")
    except urllib.error.HTTPError as e:
        body_preview = b""
        try:
            body_preview = e.read()[:300]
        except Exception:
            pass
        print(f"  {e.code} {m}:generateContent -> {body_preview[:200]}")
    except Exception as e:
        print(f"  ERR {m}: {e}")
