import os

# --- CONFIGURATION ---
TARGET_DIR = r"F:\Research\AI\ConversationHistory\RAWchiveCLEAN"

# The Footer phrase to remove
FOOTER_MARKER = "Gemini can make mistakes, so double-check it"

def clean_footers():
    if not os.path.exists(TARGET_DIR):
        print(f"❌ Error: Directory not found: {TARGET_DIR}")
        return

    cleaned_count = 0
    skipped_count = 0
    
    print(f"🧹 Scanning footers in {TARGET_DIR}...")

    for root, dirs, files in os.walk(TARGET_DIR):
        for filename in files:
            if filename.endswith(".md"):
                file_path = os.path.join(root, filename)
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # We strip trailing whitespace to ensure we catch the phrase even if there are newlines after it
                    clean_content = content.strip()
                    
                    if clean_content.endswith(FOOTER_MARKER):
                        # Remove the marker
                        # We slice off the length of the marker from the end
                        new_content = clean_content[:-len(FOOTER_MARKER)]
                        
                        # One final strip to remove any newlines left "above" the footer
                        new_content = new_content.strip()

                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        
                        cleaned_count += 1
                        # Optional: Print every 50 files so console isn't flooded
                        if cleaned_count % 50 == 0:
                            print(f"   ... Cleaned {cleaned_count} files so far ...")
                    else:
                        skipped_count += 1

                except Exception as e:
                    print(f"❌ Error processing {filename}: {e}")

    print("-" * 30)
    print(f"🎉 FOOTER CLEANUP COMPLETE.")
    print(f"   - Files Scrubbed: {cleaned_count}")
    print(f"   - No Footer Found: {skipped_count}")

if __name__ == "__main__":
    clean_footers()