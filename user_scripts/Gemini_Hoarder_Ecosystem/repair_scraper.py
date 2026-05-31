import os

# --- CONFIGURATION ---
# EXTENSION PATH (Update if different)
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- FILE CONTENTS ---

MANIFEST_JSON = """{
  "manifest_version": 3,
  "name": "Gemini Hoarder v1.1",
  "version": "1.1",
  "description": "Scrape Gemini chats (Text + Assets) or Batch Archive history.",
  "permissions": ["activeTab", "scripting", "downloads"],
  "background": {
    "service_worker": "background.js"
  },
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

BACKGROUND_JS = """
chrome.runtime.onMessage.addListener((arg, sender, sendResponse) => {
  if (arg.action === "download_file") {
    chrome.downloads.download({
      url: arg.url,
      filename: arg.filename,
      saveAs: false,
      conflictAction: "overwrite"
    });
  }
});
"""

POPUP_HTML = """<!DOCTYPE html>
<html>
<head>
  <style>
    body { width: 280px; padding: 15px; font-family: sans-serif; }
    button { width: 100%; padding: 10px; margin-bottom: 8px; cursor: pointer; border-radius: 4px; font-weight: bold; border: 1px solid #ccc;}
    
    #btn-select { background-color: #e3f2fd; border-color: #2196f3; color: #0d47a1; }
    #btn-select:hover { background-color: #bbdefb; }
    
    #btn-all { background-color: #e8f5e9; border-color: #4caf50; color: #1b5e20; }
    #btn-all:hover { background-color: #c8e6c9; }
    
    #btn-batch { background-color: #fff3e0; border-color: #ff9800; color: #e65100; }
    #btn-batch:hover { background-color: #ffe0b2; }

    #status { font-size: 12px; color: #666; margin-top: 10px; text-align: center; border-top: 1px solid #eee; padding-top: 10px;}
  </style>
</head>
<body>
  <h3 style="margin-top:0">Gemini Hoarder</h3>
  <button id="btn-select">🎯 Select Frame</button>
  <button id="btn-all">📑 Scrape Page (+Assets)</button>
  <button id="btn-batch">📚 Batch Archive All</button>
  <div id="status">Ready</div>
  <script src="popup.js"></script>
</body>
</html>"""

POPUP_JS = """
async function sendMessageToContentScript(action) {
  const statusDiv = document.getElementById('status');
  try {
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab || !tab.url.includes("gemini.google.com")) {
      statusDiv.innerText = "⚠️ Only works on Gemini tabs!";
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: action }, (response) => {
      if (chrome.runtime.lastError) {
        // This usually means content script isn't loaded yet
        statusDiv.innerHTML = "❌ <b>Needs Refresh:</b><br>Reload page & try again.";
        return;
      }
      
      if (action === "start_selection") window.close();
      else if (action === "batch_archive") statusDiv.innerText = "🚀 Batch started... check sidebar!";
      else statusDiv.innerText = "✅ Scraper running...";
    });
  } catch (err) {
    statusDiv.innerText = "❌ Error: " + err.message;
  }
}

// Check if buttons exist before adding listeners to prevent crashes
if(document.getElementById('btn-select')) 
    document.getElementById('btn-select').addEventListener('click', () => sendMessageToContentScript("start_selection"));

if(document.getElementById('btn-all')) 
    document.getElementById('btn-all').addEventListener('click', () => sendMessageToContentScript("scrape_all"));

if(document.getElementById('btn-batch')) 
    document.getElementById('btn-batch').addEventListener('click', () => sendMessageToContentScript("batch_archive"));
"""

CONTENT_JS = """
let selectionMode = false;
let turndownService = new TurndownService();

turndownService.addRule('codeBlock', {
  filter: ['pre'],
  replacement: function (content, node) {
    return '\\n```\\n' + node.textContent + '\\n```\\n';
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "start_selection") toggleSelectionMode(true);
  if (request.action === "scrape_all") scrapeContent(document.body, true);
  if (request.action === "batch_archive") runBatchArchiver();
  sendResponse({status: "received"}); // Keep channel open
});

// --- UI HELPERS ---
function showToast(msg, duration = 3000) {
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    toast.style.cssText = "position:fixed;top:20px;right:20px;background:#333;color:white;padding:12px;border-radius:6px;z-index:99999;font-family:sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.3);";
    document.body.appendChild(toast);
  }
  toast.innerText = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- SINGLE SCRAPE ---
function toggleSelectionMode(active) {
  selectionMode = active;
  if (active) {
    document.body.style.cursor = "crosshair";
    document.addEventListener("mouseover", handleHover);
    document.addEventListener("click", handleClick);
    showToast("🎯 Hover to select. Click to scrape.");
  } else {
    document.body.style.cursor = "default";
    document.removeEventListener("mouseover", handleHover);
    document.removeEventListener("click", handleClick);
  }
}

function handleHover(e) {
  if (!selectionMode) return;
  document.querySelectorAll(".gemini-scraper-highlight").forEach(el => el.classList.remove("gemini-scraper-highlight"));
  if (['DIV', 'SECTION', 'ARTICLE', 'MAIN'].includes(e.target.tagName)) {
    e.target.classList.add("gemini-scraper-highlight");
    // Add visual style directly if CSS file is lagging
    e.target.style.outline = "4px solid #00e676";
  }
}

function handleClick(e) {
  if (!selectionMode) return;
  e.preventDefault(); e.stopPropagation();
  const target = e.target;
  target.style.outline = "none";
  target.classList.remove("gemini-scraper-highlight");
  toggleSelectionMode(false);
  scrapeContent(target, true);
}

async function scrapeContent(rootElement, includeAssets = true) {
  showToast(includeAssets ? "📦 Compressing..." : "📄 Saving Text...");
  
  const zip = new JSZip();
  const assetsFolder = zip.folder("assets");
  const clone = rootElement.cloneNode(true);
  
  clone.querySelectorAll("script, style, button, svg").forEach(e => e.remove());

  if (includeAssets) {
    const images = clone.querySelectorAll("img");
    let imgCount = 0;
    for (let img of images) {
        const src = img.src;
        // FILTER: Ignore data URLs, profile pics, and favicons to stop errors
        if (src && src.startsWith("http") && 
            !src.includes("googleusercontent") && 
            !src.includes("favicon") && 
            !src.includes("gstatic")) {
            try {
                const blob = await fetch(src).then(r => r.blob());
                const filename = `img_${Date.now()}_${imgCount}.png`;
                assetsFolder.file(filename, blob);
                img.src = `assets/${filename}`;
                imgCount++;
            } catch (e) { console.log("Skipping asset:", src); }
        }
    }
  } else {
     clone.querySelectorAll("img, video").forEach(e => e.remove());
  }

  const markdown = turndownService.turndown(clone.innerHTML);
  zip.file("conversation.md", markdown);

  const content = await zip.generateAsync({ type: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(content);
  a.download = `Gemini_Scrape_${Date.now()}.zip`;
  a.click();
  showToast("✅ Done!");
}

// --- BATCH ARCHIVER ---
async function runBatchArchiver() {
  showToast("📚 STARTING BATCH ARCHIVE...", 0);
  
  // 1. Expand Sidebar
  const nav = document.querySelector("nav");
  if (!nav) { showToast("❌ No sidebar found."); return; }
  
  const scroller = nav.closest("div[class*='-container']") || nav;
  for (let i = 0; i < 3; i++) {
     scroller.scrollTop = scroller.scrollHeight;
     await new Promise(r => setTimeout(r, 800));
  }

  // 2. Collect Links
  const links = Array.from(document.querySelectorAll("a[href^='/app/']"));
  const total = links.length;
  showToast(`📚 Found ${total} chats. Processing...`, 0);

  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  for (let i = 0; i < total; i++) {
    const link = links[i];
    const title = (link.innerText || `Chat_${i}`).trim().replace(/[^a-z0-9]/gi, '_').substring(0, 50);
    
    showToast(`Downloading ${i+1}/${total}: ${title}`, 0);
    link.click();
    
    // Wait for load
    await new Promise(r => setTimeout(r, 2500));

    const mainChat = document.querySelector("main");
    if (mainChat) {
        const clone = mainChat.cloneNode(true);
        // Aggressive cleaning for raw text
        clone.querySelectorAll("*").forEach(el => {
            if(el.tagName === 'IMG' || el.tagName === 'VIDEO' || el.tagName === 'SVG' || el.tagName === 'SCRIPT') el.remove();
        });
        
        const markdown = turndownService.turndown(clone.innerHTML);
        const blob = new Blob([markdown], {type: "text/markdown"});
        
        chrome.runtime.sendMessage({
            action: "download_file", 
            url: URL.createObjectURL(blob), 
            filename: `RAWchive/${dateStr}/${title}.md`
        });
    }
  }
  showToast("✅ BATCH COMPLETE!");
}
"""

def repair_project():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ Error: Path not found: {PROJECT_PATH}")
        return

    files = {
        "manifest.json": MANIFEST_JSON,
        "background.js": BACKGROUND_JS,
        "popup.html": POPUP_HTML,
        "popup.js": POPUP_JS,
        "content.js": CONTENT_JS
    }

    for filename, content in files.items():
        file_path = os.path.join(PROJECT_PATH, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"🛠️  Repaired: {filename}")

    print("\n✅ REPAIR COMPLETE.")
    print("👉 GO TO CHROME -> EXTENSIONS -> Click Reload (Circular Arrow) on 'Gemini Hoarder'")
    print("👉 REFRESH your Gemini Tab (F5) before clicking the button.")

if __name__ == "__main__":
    repair_project()