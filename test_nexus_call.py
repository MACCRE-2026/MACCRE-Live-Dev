import sys
import os
import json
sys.path.append(os.path.abspath('.'))

from maccre_core.orchestration.windows_vault import get_native_credential
from maccre_core._net.gemini_client import GeminiClient

def test():
    gemini_key = get_native_credential("MACCRE_Sovereign")
    client = GeminiClient(api_key=str(gemini_key).strip())
    
    # Simulate the exact request
    history = [{"role": "user", "parts": [{"text": "Hello, what can you tell me about Lychrel numbers?"}]}]
    
    tools = [
        {
            "name": "search_web",
            "description": "Searches the live internet for external concepts using Brave Search.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The search query."},
                    "freshness": {"type": "STRING"}
                },
                "required": ["query"]
            }
        }
    ]
    
    try:
        resp = client.generate_content(
            model="gemini-3.1-pro-preview",
            contents=history,
            system_instruction="You are Nexus...",
            temperature=1.0,
            tool_declarations=tools,
            search_grounding=True
        )
        print("RAW RESPONSE BODY:")
        print(json.dumps(resp.raw, indent=2))
        print("TEXT:", repr(resp.text))
        print("FUNC:", resp.function_call)
    except Exception as e:
        print("EXCEPTION:", e)

if __name__ == "__main__":
    test()
