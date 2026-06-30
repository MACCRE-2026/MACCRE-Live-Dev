import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove LinearFlowScreen entirely
lfs_re = re.compile(r'class LinearFlowScreen\(ModalScreen\):.*?(?=\nclass FileCabinetModalScreen)', re.DOTALL)
content = lfs_re.sub('', content)

# Remove action_open_flow_editor
ofe_re = re.compile(r'\s*@on\(Button.Pressed,\s*"#btn-flow-editor"\)\s*def action_open_flow_editor\(self\) -> None:.*?(?=\n\s*@on\()', re.DOTALL)
content = ofe_re.sub('', content)

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("LinearFlowScreen purged")
