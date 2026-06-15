import sys
import os
sys.path.append(os.path.abspath('.'))

from maccre_core.orchestration.windows_vault import get_native_credential

def test():
    gemini_key = get_native_credential("MACCRE_Sovereign")
    if not gemini_key:
        print("Gemini key NOT FOUND")
        return
        
    try:
        import urllib.request
        import json
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key.strip()}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    print("Found text model:", m.get('name'))
    except Exception as e:
        print("Model list failed:", e)

if __name__ == "__main__":
    test()
