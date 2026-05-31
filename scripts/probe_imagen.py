"""
scripts/probe_imagen.py
Probe the Gemini API to find the working Imagen endpoint and model.
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

CANDIDATES = [
    # generateImages endpoint variants
    ("https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:generateImages", "POST_IMAGE"),
    ("https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict", "POST_IMAGE"),
    # List all models to see what's available
    ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=100", "GET"),
]

# Also try listing models with image support
print("=== Probing Imagen API endpoints ===\n")

# First list all available models
url = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={key}"
req = urllib.request.Request(url, method="GET")
try:
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
        models = json.loads(r.read().decode())
        all_models = [m["name"] for m in models.get("models", [])]
        imagen_models = [m for m in all_models if "imagen" in m.lower() or "image" in m.lower()]
        print(f"Total models: {len(all_models)}")
        print(f"Image-related models: {imagen_models}")
except Exception as e:
    print(f"Model list ERROR: {e}")

# Try the generateImages POST with a simple prompt
print("\n=== Probing generateImages endpoint ===")
test_models = [
    "imagen-3.0-generate-002",
    "imagen-3.0-generate-001",
    "gemini-2.0-flash-exp-image-generation",
    "gemini-2.0-flash-preview-image-generation",
]

body_imagen = json.dumps({
    "instances": [{"prompt": "A red apple on a table"}],
    "parameters": {"sampleCount": 1}
}).encode("utf-8")

body_generate = json.dumps({
    "contents": [{"role": "user", "parts": [
        {"text": "Generate an image of a red apple on a table"}
    ]}],
    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
}).encode("utf-8")

for model in test_models:
    for endpoint_fmt, body in [
        (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateImages?key={{key}}", body_imagen),
        (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{key}}", body_generate),
    ]:
        url = endpoint_fmt.replace("{key}", key)
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
                resp = json.loads(r.read().decode())
                keys = list(resp.keys())
                print(f"  OK  {model} @ {url.split('?')[0].split('/')[-1]} -> keys={keys}")
        except urllib.error.HTTPError as e:
            print(f"  {e.code} {model} @ {url.split('?')[0].split('/')[-1]}")
        except Exception as e:
            print(f"  ERR {model}: {e}")
