"""
scripts/probe_all_models.py
Fetch every model from the Gemini API and categorize by supportedGenerationMethods.
This gives us the ground truth for what the ModelRegistry should index.
"""
import json
import ssl
import urllib.request
import sys
from collections import defaultdict

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maccre_core.orchestration.windows_vault import get_native_credential

key = str(get_native_credential("MACCRE_Sovereign")).strip()
ssl_ctx = ssl.create_default_context()

url = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=500&key={key}"
req = urllib.request.Request(url, method="GET")
with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as r:
    data = json.loads(r.read().decode())

models = data.get("models", [])
print(f"Total models from API: {len(models)}\n")

# Group by supportedGenerationMethods
by_methods: dict[str, list[str]] = defaultdict(list)
for m in models:
    methods = tuple(sorted(m.get("supportedGenerationMethods", [])))
    name = m["name"].removeprefix("models/")
    by_methods[str(methods)].append(name)

for methods_key, names in sorted(by_methods.items()):
    print(f"Methods: {methods_key}")
    for n in sorted(names):
        print(f"  {n}")
    print()

# Also print a flat sorted list with their primary method
print("\n=== FULL MODEL INVENTORY ===")
for m in sorted(models, key=lambda x: x["name"]):
    name = m["name"].removeprefix("models/")
    methods = m.get("supportedGenerationMethods", [])
    desc = m.get("description", "")[:80]
    print(f"  {name:55} {methods}")
