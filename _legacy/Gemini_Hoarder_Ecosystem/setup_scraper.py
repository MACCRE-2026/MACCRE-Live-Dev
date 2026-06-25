import os
import urllib.request

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"
JSZIP_URL = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"
TURNDOWN_URL = "https://cdnjs.cloudflare.com/ajax/libs/turndown/7.1.2/turndown.js"

# --- FILE CONTENTS ---

MANIFEST_JSON = """{
  "manifest_version": 3,
  "name": "Gemini Hoarder",
  "version": "1.0",
  "description": "Scrape Gemini chats (Text + Assets) to Markdown.",
  "permissions": ["activeTab", "scripting", "downloads"],
  "action": {
    "default_popup": "popup.html"
  },
  "content_scripts": [
    {
      "matches": ["https://gemini.google.com/*"],
      "js": ["jszip.min.js", "turndown.js", "content.js"],
      "css": ["styles.css"]
    }
  ]
}"""

POPUP_HTML = """<!DOCTYPE html>
<html>
<head>
  <style>
    body { width: 250px; padding: 15px; font-family: sans-serif; }
    button { width: 100%; padding: 10px; margin-bottom: 10px; cursor: pointer; border-radius: 4px; font-weight: bold;}
    #btn-select { background-color: #e3f2fd; border: 1px solid #2196f3; color: #0d47a1; }
    #btn-select:hover { background-color: #bbdefb; }
    #btn-all { background-color: #e8f5e9; border: 1px solid #4caf50; color: #1b5e20; }
    #btn-all:hover { background-color: #c8e6c9; }
    #status { font-size: 12px; color: #666; margin-top: 10px; text-align: center; border-top: 1px solid #eee; padding-top: 10px;}
  </style>
</head>
<body>
  <h3 style="margin-top:0">Gemini Hoarder</h3>
  <button id="btn-select">🎯 Select Frame</button>
  <button id="btn-all">📑 Scrape Full Page</button>
  <div id="status">Ready to scrape</div>
  <script src="popup.js"></script>
</body>
</html>"""

POPUP_JS = """
document.getElementById('btn-select').addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: "start_selection" });
  window.close();
});

document.getElementById('btn-all').addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  document.getElementById('status').innerText = "Scraping...";
  chrome.tabs.sendMessage(tab.id, { action: "scrape_all" });
});
"""

STYLES_CSS = """
/* The highlighting box for selection mode */
.gemini-scraper-highlight {
  outline: 4px solid #00e676 !important;
  background-color: rgba(0, 230, 118, 0.1) !important;
  cursor: crosshair !important;
  transition: all 0.1s ease;
}

/* A processing overlay so you know it's working */
.gemini-scraper-overlay {
  position: fixed; top: 20px; right: 20px; 
  background: #333; color: white; padding: 15px 20px; 
  border-radius: 8px; z-index: 99999; font-family: sans-serif;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  font-size: 14px;
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
"""

CONTENT_JS = """
let selectionMode = false;
let turndownService = new TurndownService();

// Configure Turndown to handle code blocks better
turndownService.addRule('codeBlock', {
  filter: ['pre'],
  replacement: function (content, node) {
    return '\\n```\\n' + node.textContent + '\\n```\\n';
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "start_selection") toggleSelectionMode(true);
  if (request.action === "scrape_all") scrapeContent(document.body);
});

// --- SELECTION LOGIC ---
function toggleSelectionMode(active) {
  selectionMode = active;
  if (active) {
    document.body.style.cursor = "crosshair";
    document.addEventListener("mouseover", handleHover);
    document.addEventListener("click", handleClick);
    showToast("🎯 Hover to select a chat/area. Click to download.");
  } else {
    document.body.style.cursor = "default";
    document.removeEventListener("mouseover", handleHover);
    document.removeEventListener("click", handleClick);
  }
}

function handleHover(e) {
  if (!selectionMode) return;
  document.querySelectorAll(".gemini-scraper-highlight").forEach(el => el.classList.remove("gemini-scraper-highlight"));
  // Target relevant blocks (divs, sections, articles) to avoid selecting tiny spans
  if (['DIV', 'SECTION', 'ARTICLE', 'MAIN'].includes(e.target.tagName)) {
    e.target.classList.add("gemini-scraper-highlight");
  }
}

function handleClick(e) {
  if (!selectionMode) return;
  e.preventDefault();
  e.stopPropagation();
  
  const target = e.target;
  target.classList.remove("gemini-scraper-highlight");
  toggleSelectionMode(false);
  
  scrapeContent(target);
}

// --- SCRAPING LOGIC ---
async function scrapeContent(rootElement) {
  showToast("📦 Analyzing content & gathering assets...");
  
  const zip = new JSZip();
  const assetsFolder = zip.folder("assets");
  
  // Clone element to modify it safely
  const clone = rootElement.cloneNode(true);
  
  // 1. Process Images
  const images = clone.querySelectorAll("img");
  let imgCount = 0;
  for (let img of images) {
    const src = img.src;
    // Skip data URLs (small icons) and internal UI icons
    if (src && !src.startsWith("data:") && src.startsWith("http")) {
      try {
        const ext = src.split('.').pop().split(/[?#]/)[0] || 'png';
        const filename = `img_${Date.now()}_${imgCount}.${ext}`;
        
        // Fetch blob
        const blob = await fetch(src).then(r => r.blob());
        assetsFolder.file(filename, blob);
        
        // Rewrite Markdown link
        img.src = `assets/${filename}`;
        img.alt = img.alt || "image";
        imgCount++;
      } catch (err) {
        console.warn("Failed to download image:", src);
      }
    }
  }

  // 2. Process Videos (gemini usually uses standard video tags)
  const videos = clone.querySelectorAll("video");
  let vidCount = 0;
  for (let vid of videos) {
    let src = vid.src || vid.querySelector("source")?.src;
    if (src && src.startsWith("http")) {
      try {
        const filename = `video_${Date.now()}_${vidCount}.mp4`;
        const blob = await fetch(src).then(r => r.blob());
        assetsFolder.file(filename, blob);
        
        // Replace video player with link
        const link = document.createElement("p");
        link.innerHTML = `**[📹 Attached Video: ${filename}](assets/${filename})**`;
        vid.replaceWith(link);
        vidCount++;
      } catch (err) {
        console.warn("Failed to download video:", src);
      }
    }
  }

  // 3. Clean Garbage (Scripts, styles, buttons)
  clone.querySelectorAll("script, style, button, svg").forEach(e => e.remove());

  // 4. Convert to Markdown
  const markdown = turndownService.turndown(clone.innerHTML);
  zip.file("conversation.md", markdown);

  // 5. Download Zip
  showToast("💾 Compressing & Saving...");
  const content = await zip.generateAsync({ type: "blob" });
  
  const a = document.createElement("a");
  a.href = URL.createObjectURL(content);
  a.download = `Gemini_Scrape_${new Date().toISOString().slice(0,10)}.zip`;
  a.click();
  showToast("✅ Download Complete!");
}

function showToast(msg) {
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    toast.className = "gemini-scraper-overlay";
    document.body.appendChild(toast);
  }
  toast.innerText = msg;
  setTimeout(() => toast.remove(), 4000);
}
"""

# --- MAIN EXECUTION ---

def create_project():
    # 1. Create Directory
    if not os.path.exists(PROJECT_PATH):
        try:
            os.makedirs(PROJECT_PATH)
            print(f"✅ Created directory: {PROJECT_PATH}")
        except OSError as e:
            print(f"❌ Error creating directory: {e}")
            return
    else:
        print(f"⚠️  Directory already exists: {PROJECT_PATH}")

    # 2. Write Text Files
    files = {
        "manifest.json": MANIFEST_JSON,
        "popup.html": POPUP_HTML,
        "popup.js": POPUP_JS,
        "styles.css": STYLES_CSS,
        "content.js": CONTENT_JS
    }

    for filename, content in files.items():
        file_path = os.path.join(PROJECT_PATH, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"📄 Written: {filename}")

    # 3. Download Libraries
    print("⬇️  Downloading libraries...")
    
    try:
        urllib.request.urlretrieve(JSZIP_URL, os.path.join(PROJECT_PATH, "jszip.min.js"))
        print("   - jszip.min.js downloaded.")
    except Exception as e:
        print(f"   ❌ Failed to download jszip: {e}")

    try:
        urllib.request.urlretrieve(TURNDOWN_URL, os.path.join(PROJECT_PATH, "turndown.js"))
        print("   - turndown.js downloaded.")
    except Exception as e:
        print(f"   ❌ Failed to download turndown: {e}")

    print("\n✨ Project setup complete! Load the folder in chrome://extensions")

if __name__ == "__main__":
    create_project()