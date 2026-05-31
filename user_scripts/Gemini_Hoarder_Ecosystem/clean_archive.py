import os

# --- CONFIGURATION ---
# Updated target path
TARGET_DIR = r"C:\Users\wilke\Downloads\T&C sheets\may-batch\RAWchive"

# The "Anchor" phrase. We delete everything before this.
START_MARKER = "Conversation with Gemini"

def clean_files():
    if not os.path.exists(TARGET_DIR):
        print(f"❌ Error: Directory not found: {TARGET_DIR}")
        return

    cleaned_count = 0
    skipped_count = 0
    error_count = 0

    print(f"🧹 Scanning {TARGET_DIR}...")

    # Walk through all subfolders
    for root, dirs, files in os.walk(TARGET_DIR):
        for filename in files:
            if filename.endswith(".md"):
                file_path = os.path.join(root, filename)
                
                try:
                    # Read the file
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Check if the file needs cleaning
                    if START_MARKER in content:
                        split_index = content.find(START_MARKER)
                        
                        # If marker is at index 0, it's already clean
                        if split_index == 0:
                            skipped_count += 1
                            continue

                        # Slicing: Keep everything from the marker to the end
                        new_content = content[split_index:]

                        # Overwrite with clean version
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        
                        cleaned_count += 1
                        print(f"✅ Cleaned: {filename}")
                    
                    else:
                        print(f"⚠️  Marker not found (Skipped): {filename}")
                        skipped_count += 1

                except Exception as e:
                    print(f"❌ Error processing {filename}: {e}")
                    error_count += 1

    print("-" * 30)
    print(f"🎉 COMPLETED.")
    print(f"   - Files Cleaned: {cleaned_count}")
    print(f"   - Skipped/No Marker: {skipped_count}")
    print(f"   - Errors: {error_count}")

if __name__ == "__main__":
    clean_files()