with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if 'self.write_nexus_log(f"[red]Error populating selects: {e}[/red]")' in line:
        prev_line = lines[i-1]
        indent = len(prev_line) - len(prev_line.lstrip())
        if "except Exception as e" in prev_line:
            new_line = (' ' * (indent + 4)) + 'pass\n'
        else:
            new_line = (' ' * (indent + 4)) + 'pass\n'
        new_lines.append(new_line)
    else:
        new_lines.append(line)

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
