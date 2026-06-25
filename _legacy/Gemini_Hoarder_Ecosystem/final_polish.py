import os

# --- CONFIGURATION ---
TARGET_DIR = r"F:\Research\Backup\RAWchiveCLEAN\RAW19JAN2026"

# The Anchor (We find this, delete everything before it, AND delete the phrase itself)
START_MARKER = "Conversation with Gemini"

# The Footer Hit List (Items to strip from the bottom)
FOOTER_MARKERS = [
    "Gemini can make mistakes, so double-check it",
    "Gemini may display inaccurate info, including about people, so double-check its responses.",
    "Google Privacy PolicyOpens in a new window",
    "Google Terms of ServiceOpens in a new window",
    "Your privacy & Gemini AppsOpens in a new window",
    "Conversation with Gemini"  # Added as requested
]

def clean_everything():
    if not os.path.exists(TARGET_DIR):
        print(f"❌ Error: Directory not found: {TARGET_DIR}")
        return

    files_processed = 0
    headers_cleaned = 0
    footers_removed = 0
    errors = 0

    print(f"🧽 Starting Final Polish in: {TARGET_DIR}")

    for root, dirs, files in os.walk(TARGET_DIR):
        for filename in files:
            if filename.lower().endswith(('.txt', '.md')):
                file_path = os.path.join(root, filename)
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    original_content = content
                    modified = False

                    # 1. HEADER CLEANUP
                    # Find the anchor
                    if START_MARKER in content:
                        split_index = content.find(START_MARKER)
                        if split_index >= 0:
                            # Keep everything AFTER the marker
                            # (split_index + len(START_MARKER)) skips the phrase itself
                            content = content[split_index + len(START_MARKER):].lstrip()
                            headers_cleaned += 1
                            modified = True
                    
                    # 2. ITERATIVE FOOTER CLEANUP
                    cleaning = True
                    while cleaning:
                        cleaning = False 
                        temp_content = content.strip()
                        
                        for marker in FOOTER_MARKERS:
                            if temp_content.endswith(marker):
                                # Slice off this marker
                                content = temp_content[:-len(marker)].strip()
                                footers_removed += 1
                                modified = True
                                cleaning = True # Check again in case another footer was hiding behind this one
                                break 

                    # 3. SAVE IF CHANGED
                    if modified:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        files_processed += 1
                        # print(f"✨ Polished: {filename}") 

                except Exception as e:
                    print(f"❌ Error reading {filename}: {e}")
                    errors += 1

    print("-" * 40)
    print(f"🎉 FINAL CLEAN COMPLETE.")
    print(f"   - Files Polished: {files_processed}")
    print(f"   - Headers Stripped: {headers_cleaned}")
    print(f"   - Footer Lines Removed: {footers_removed}")
    print(f"   - Errors: {errors}")

if __name__ == "__main__":
    clean_everything()