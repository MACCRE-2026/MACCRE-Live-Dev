import re
with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

css_match = re.search(r'CSS = \"\"\"(.*?)\"\"\"', content, re.DOTALL)
if css_match:
    lines = css_match.group(1).split('\n')
    for i, line in enumerate(lines):
        if 'panel-section' in line or 'flow-execution' in line or 'flow-select-row' in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 7)
            print(f'\n--- Context around {line.strip()} ---')
            print('\n'.join(lines[start:end]))
