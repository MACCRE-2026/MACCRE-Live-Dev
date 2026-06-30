import re
with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

ofe_re = re.compile(r'\s*@on\(Button.Pressed, "#btn-flow-editor"\)\s*def action_open_flow_editor\(self\).*?(?=\n\s*@on|\n\s*class|\n\s*def )', re.DOTALL)
content = ofe_re.sub('', content)

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("patch4 done")
