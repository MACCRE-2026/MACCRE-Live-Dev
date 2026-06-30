import json
transcript_path = r'C:\Users\wilke\.gemini\antigravity\brain\f0eaafdc-85d9-4d65-b7df-08fc73e62647\.system_generated\logs\transcript.jsonl'
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        created_at = data.get('created_at', '')
        if created_at == '2026-06-24T01:11:34Z':
            tool_calls = data.get('tool_calls', [])
            for tc in tool_calls:
                if 'write_to_file' == tc['name']:
                    with open('B:\\EXO_GANS\\scratch_node_modal.py', 'w', encoding='utf-8') as outf:
                        # tc['args']['CodeContent'] is already a standard python string since it was json parsed
                        outf.write(tc['args']['CodeContent'])
