import sys
import os
sys.path.append(os.path.abspath('.'))

from maccre_core.orchestration.windows_vault import _try_wincred

def test():
    print("Testing Brave Key...")
    res = _try_wincred("BRAVE_SEARCH_API_KEY")
    print(f"Result: {repr(res)}")

if __name__ == "__main__":
    test()
