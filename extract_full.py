import json
transcript_path = r'C:\Users\wilke\.gemini\antigravity\brain\f0eaafdc-85d9-4d65-b7df-08fc73e62647\.system_generated\logs\transcript_full.jsonl'
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        created_at = data.get('created_at', '')
        if created_at == '2026-06-24T01:11:34Z':
            tool_calls = data.get('tool_calls', [])
            for tc in tool_calls:
                if 'write_to_file' == tc['name'] or 'run_command' == tc['name']:
                    with open('B:\\EXO_GANS\\scratch_node_modal_full.py', 'w', encoding='utf-8') as outf:
                        code = tc['args'].get('CodeContent', '')
                        if not code:
                            code = tc['args'].get('CommandLine', '')
                        # Try decoding string escapes
                        outf.write(code.encode('utf-8').decode('unicode_escape'))
