import sys

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. REMOVE BAD POPULATION CODE FROM AgentChatModalScreen
bad_pop_start = content.find('            # Populate inline flow editor selects')
bad_pop_end = content.find('            roster = load_agent_names_from_library(self.app.active_project)')

if bad_pop_start != -1 and bad_pop_end != -1:
    content = content[:bad_pop_start] + content[bad_pop_end:]
else:
    print('Warning: could not remove bad population code')

# 2. INSERT POPULATION CODE INTO NexusPlex.on_mount
good_pop_code = '''
        # Populate inline flow editor selects
        try:
            from maccre_core.macronode_registry import get_macronode_store
            from maccre_core.orchestration.roster_loader import load_agent_names_from_library as loader_func
            store = get_macronode_store()
            macros = store.list_all()
            macro_sel = self.query_one("#macro-select", Select)
            if macro_sel:
                macro_sel.set_options([(m, m) for m in macros])
            
            agents = loader_func(self.active_project)
            agent_sel = self.query_one("#agent-select", Select)
            if agent_sel:
                agent_sel.set_options([(a, a) for a in agents])
                
            special = ["MANUAL", "DET_ANCHOR", "DET_RECURSION", "DET_PAUSE", "DET_GATE", "DET_CHECKPOINT", "DET_DELAY", "DET_TRANSFORM"]
            special_sel = self.query_one("#special-select", Select)
            if special_sel:
                special_sel.set_options([(s, s) for s in special])
        except Exception:
            pass
'''
npm_mount_loc = content.find('self.set_active_project("GLOBAL")')
if npm_mount_loc != -1:
    end_of_line = content.find('\n', npm_mount_loc)
    content = content[:end_of_line] + '\n' + good_pop_code + content[end_of_line:]
else:
    print('Warning: could not insert into NexusPlex.on_mount')


# 3. ADD CSS TO NexusPlex.CSS
css_to_add = '''
    /* Flow Info Panels */
    #flow-select-row {
        height: 25;
        margin-bottom: 1;
        border: round #30363d;
        padding: 1;
    }

    .flow-select-group {
        width: 1fr;
        margin-right: 1;
        height: 100%;
    }

    .info-panel-container {
        height: 1fr;
        border: round #30363d;
        padding: 1;
        overflow-y: auto;
        margin-top: 1;
    }

    .info-panel-title {
        color: #8b949e;
        text-style: bold;
        margin-bottom: 1;
    }

    .info-panel-body {
        color: #c9d1d9;
    }

    .flow-add-btn {
        width: 100%;
        margin-top: 1;
    }
'''
css_loc = content.find('class NexusPlex(Screen):')
if css_loc != -1:
    css_insert = content.find('"""', content.find('CSS = """', css_loc) + 8)
    content = content[:css_insert] + css_to_add + content[css_insert:]

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patch part 1 done.')
