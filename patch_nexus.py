import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Rename 'Build an Agent' to 'Agent Builder'
content = content.replace('yield Label("Build an Agent", classes="pane-title")', 'yield Label("Agent Builder", classes="pane-title")')

# 2. Fix on_mount exception handler and loader
content = re.sub(
    r'from maccre_core\.orchestration\.roster_loader import load_agent_names_from_library as loader_func',
    'from maccre_core.agent_library import get_agent_store',
    content
)
content = re.sub(
    r'agents = loader_func\(self\.active_project\)',
    'agents = get_agent_store("GLOBAL").get_names()',
    content
)
content = re.sub(
    r'except Exception:\s+pass',
    r'except Exception as e:\n            self.write_nexus_log(f"[red]Error populating selects: {e}[/red]")',
    content
)

# 3. Fix action_save_agent
content = re.sub(
    r'existing = load_agent_names_from_library\(self\.active_project\)',
    'existing = get_agent_store("GLOBAL").get_names()',
    content
)

# Replace get_agent_store(self.active_project) with get_agent_store("GLOBAL") in action_save_agent
content = re.sub(
    r'store = get_agent_store\(self\.active_project\)',
    'store = get_agent_store("GLOBAL")',
    content
)

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)
