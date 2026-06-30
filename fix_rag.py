import sys
with open('maccre_core/tools/rag_tools.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip() == 'if not triplets:':
        break
    new_lines.append(line)

new_content = ''.join(new_lines) + '''    # ── Phase 2: Vectorize knowledge triplets into SovereignPinStore (SQLite) ─────
    try:
        from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
        
        unified_ledger_path = get_datacenter_path("04_Code_Artifacts", session_id, "unified_session_ledger.md")
        if unified_ledger_path.exists():
            engine = CognitiveMemoryEngine()
            engine.extract_from_canonized_ledger(str(unified_ledger_path), session_id)
            results.append("[thought_pins] Extracted pins from unified ledger into SovereignPinStore.")
        else:
            results.append("[thought_pins] unified_session_ledger.md not found, skipping extraction.")
            
    except Exception as tp_err:
        results.append(f"[thought_pins] Extraction error: {tp_err!s}")
        
    return "\\n".join(results)
'''
with open('maccre_core/tools/rag_tools.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Fixed rag_tools.py')
