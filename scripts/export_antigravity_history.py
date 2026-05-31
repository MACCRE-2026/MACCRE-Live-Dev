import os
import json
from pathlib import Path
import logging
import sys

# Ensure Python can find the maccre_core module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Use MACCREv2's path resolver to guarantee portability
from maccre_core.utils.path_resolver import get_datacenter_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)

def parse_chat_log(overview_path: Path) -> str:
    """Parses the JSONL overview.txt file and formats it into a readable Markdown transcript."""
    if not overview_path.exists():
        return "*No overview.txt transcript found.*"
        
    lines = overview_path.read_text(encoding="utf-8", errors="replace").splitlines()
    output: list[str] = ["## Conversation Transcript\n"]
    
    for line in lines:
        if not line.strip():
            continue
            
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
            
        source = data.get("source", "UNKNOWN")
        content = data.get("content", "")
        tool_calls = data.get("tool_calls", [])
        created_at = data.get("created_at", "")
        
        timestamp_str = f" ({created_at})" if created_at else ""
        
        # Format the speaker
        if source == "USER_EXPLICIT":
            output.append(f"### 👤 User{timestamp_str}")
            if content:
                # Strip out the noisy <ADDITIONAL_METADATA> blocks if present
                if "<ADDITIONAL_METADATA>" in content:
                    content = content.split("<ADDITIONAL_METADATA>")[0].strip()
                output.append(f"{content}\n")
                
        elif source == "MODEL":
            if content:
                output.append(f"### 🤖 Antigravity{timestamp_str}")
                output.append(f"{content}\n")
            if tool_calls:
                output.append(f"### ⚙️ Tool Execution{timestamp_str}")
                for tc in tool_calls:
                    name = tc.get("name", "unknown_tool")
                    args = tc.get("args", {})
                    output.append(f"**`{name}`** -> `{json.dumps(args, indent=None)}`\n")
                    
    return "\n".join(output)

def extract_artifacts(brain_folder: Path) -> str:
    """Gathers all markdown and python files from the root of the brain folder."""
    output: list[str] = ["## Final Artifacts\n"]
    found = False
    
    # Exclude the metadata and resolved files
    for file_path in brain_folder.iterdir():
        if file_path.is_file() and (file_path.suffix in [".md", ".py"]) and not file_path.name.endswith(".resolved"):
            if "metadata" in file_path.name:
                continue
                
            found = True
            output.append(f"### Artifact: `{file_path.name}`")
            output.append("```" + ("python" if file_path.suffix == ".py" else "markdown"))
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                output.append(content)
            except Exception as e:
                output.append(f"Error reading artifact: {e}")
                
            output.append("```\n")
            
    if not found:
        output.append("*No root artifacts found.*")
        
    return "\n".join(output)

def export_all_conversations() -> None:
    """Main routine: Extracts all Antigravity chats and routes them to GLOBAL/AntigravityExport."""
    app_data_dir = Path(r"B:\MACCREv2\.gemini\antigravity\brain")
    
    if not app_data_dir.exists():
        _log.error(f"Cannot find backup Antigravity brain directory at: {app_data_dir}")
        return
        
    # We must temporarily set MACCRE_ACTIVE_PROJECT to resolve the datacenter path correctly
    os.environ["MACCRE_ACTIVE_PROJECT"] = "GLOBAL/AntigravityExport"
    output_dir = get_datacenter_path("01_Raw_Source")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    _log.info(f"Targeting Datacenter Archive: {output_dir}")
    
    folders = [f for f in app_data_dir.iterdir() if f.is_dir() and len(f.name) == 36] # UUID check
    _log.info(f"Found {len(folders)} Antigravity conversations.")
    
    for i, folder in enumerate(folders, 1):
        conv_id = folder.name
        _log.info(f"[{i}/{len(folders)}] Parsing: {conv_id}")
        
        overview_path = folder / ".system_generated" / "logs" / "overview.txt"
        
        # 1. Parse Chat
        chat_markdown = parse_chat_log(overview_path)
        
        # 2. Extract Artifacts
        artifacts_markdown = extract_artifacts(folder)
        
        # 3. Assemble Final Document
        final_doc = f"# Antigravity Session: {conv_id}\n\n"
        final_doc += chat_markdown
        final_doc += "\n---\n\n"
        final_doc += artifacts_markdown
        
        # 4. Save to Datacenter
        out_file = output_dir / f"Antigravity_Chat_{conv_id}.md"
        out_file.write_text(final_doc, encoding="utf-8")
        
    _log.info(f"Successfully exported {len(folders)} files to {output_dir}")

if __name__ == "__main__":
    export_all_conversations()
