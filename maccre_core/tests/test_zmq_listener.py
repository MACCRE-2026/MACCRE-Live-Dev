import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
from maccre_core.orchestration.live_session_manager import LiveSessionManager

def print_event(payload: dict) -> None:
    print(f"\n[INTERCEPT] EVENT: {json.dumps(payload, indent=2)}")

if __name__ == "__main__":
    print("Initializing LiveSessionManager Hub...")
    manager = LiveSessionManager()
    
    print("Registering wildcard listener...")
    manager.register_callback("*", print_event)
    
    print("Entering listener loop. Send a Swarm job in another terminal to see real-time routing!")
    try:
        manager.listen_loop()
    except KeyboardInterrupt:
        print("\nExiting listener.")
        sys.exit(0)
