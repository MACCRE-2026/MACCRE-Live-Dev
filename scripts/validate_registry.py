"""
scripts/validate_registry.py
Validate the Phase 6 ModelRegistry against the live API.
Prints each model, its detected surface, and whether it's in the right bucket.
"""
import sys
sys.path.insert(0, "B:/MACCREv2")
from maccre_core.orchestration.windows_vault import get_native_credential
from maccre_core._net.model_registry import get_registry, ModelSurface

key = str(get_native_credential("MACCRE_Sovereign")).strip()
registry = get_registry(key)

# Force a fresh probe
registry.probe_now()

print("=== ModelRegistry Phase 6 Surface Validation ===\n")
print(f"Total models indexed: {len(registry.all_models())}")
print(f"generateContent models: {len(registry.available_models())}\n")


for surface in ModelSurface:
    models = registry.get_models_for_surface(surface)
    if models:
        print(f"[{surface.value.upper():20}] ({len(models)} models)")
        for m in models:
            print(f"  {m}")
        print()

print("\n=== Failover Chain Tests ===\n")
test_cases = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.1-pro-preview",
]
for m in test_cases:
    chain = registry.get_failover_chain(m)
    print(f"  chain({m}):")
    for c in chain:
        surface = registry.surface_of(c)
        print(f"    → {c} [{surface.value}]")

print("\n=== TTS Models (render_executor will use these) ===")
tts = registry.get_models_for_surface(ModelSurface.TTS)
print(f"  {tts}")

print("\n=== Image Models (render_executor will use these) ===")
imgs = registry.get_models_for_surface(ModelSurface.IMAGE_GENERATION)
print(f"  {imgs}")

print("\n=== Deep Research Models ===")
dr = registry.get_models_for_surface(ModelSurface.DEEP_RESEARCH)
print(f"  {dr}")

print("\n=== Video Models (Veo) ===")
vids = registry.get_models_for_surface(ModelSurface.VIDEO)
print(f"  {vids}")
