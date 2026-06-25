import os

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- 1. MANIFEST (Unlock "all_frames") ---
# We add "all_frames": true to the content_scripts.
MANIFEST_JSON = """{
  "manifest_version": 3,
  "name": "Gemini Hoarder (God Mode)",
  "version": "2.1",
  "description": "Scraper with All-Frame access.",
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
      "css": ["styles.css"],
      "all_frames": true
    }
  ]
}"""

# --- 2. CONTENT SCRIPT (Frame-Aware Scanner) ---
CONTENT_JS = """
let turndownService = new TurndownService();

// --- LISTENER ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "batch_archive") runBatchArchiver();
  // We answer "ok" so the popup knows we heard it
  sendResponse({status: "ok", frame: window.location.href}); 
});

// --- TOAST HELPER ---
function showToast(msg, duration = 4000) {
  // Create toast only if it doesn't exist
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    toast.style.cssText = "position:fixed; top:10px; right:10px; background:#000; color:#0f0; padding:10px; border:1px solid #0f0; z-index:999999; font-family:monospace; font-size:12px; max-width:300px;";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- RECURSIVE LINK FINDER (The "Deep" Scanner) ---
function getAllClickables(root = document.body) {
    let items = Array.from(root.querySelectorAll("a, div[role='button'], div[role='link']"));
    
    // Shadow DOM Recursion
    const allElements = root.querySelectorAll('*');
    for (let el of allElements) {
        if (el.shadowRoot) {
            items = items.concat(getAllClickables(el.shadowRoot));
        }
    }
    return items;
}

// --- BATCH ARCHIVER ---
async function runBatchArchiver() {
  // 1. Identify where we are running
  const isIframe = window !== window.top;
  const url = window.location.href;
  
  // 2. Scan for Chats
  const candidates = getAllClickables(document.body);
  
  // 3. Filter for likely History items
  const chatLinks = candidates.filter(el => {
      const txt = (el.innerText || "").trim().toLowerCase();
      // Heuristic: Chat history usually has text, is visible, and isn't "New Chat"
      const isVisible = el.offsetHeight > 0;
      const validText = txt.length > 3 && !txt.includes("new chat") && !txt.includes("upgrade") && !txt.includes("gemini");
      
      // Look for specific attributes often used in history
      const hasHref = el.tagName === 'A' && el.href.includes("/app/");
      const isRole = el.getAttribute("role") === "link" || el.getAttribute("role") === "button";
      
      // STRICT FILTER: If it doesn't look like a chat, ignore it
      return isVisible && validText && (hasHref || isRole);
  });

  // If this frame has 0 chats, stay silent (other frames might have them)
  if (chatLinks.length === 0) {
      if (!isIframe) console.log("Main frame found 0 chats.");
      return;
  }

  showToast(`✅ <b>FRAME LOCKED</b><br>Found ${chatLinks.length} chats here.`, 0);

  // 4. PREPARE QUEUE
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  // 5. PROCESS
  // We only process the first 50 to avoid infinite loops if detection is too loose
  const queue = chatLinks.slice(0, 50); 
  
  for (let i = 0; i < queue.length; i++) {
    const el = queue[i];
    const cleanTitle = (el.innerText || "Chat").trim().replace(/[^a-z0-9]/gi, '_').substring(0, 50);
    
    showToast(`Archiving [${i+1}/${queue.length}]:<br>${cleanTitle}`, 0);

    // CLICK
    el.click();
    
    // WAIT
    await new Promise(r => setTimeout(r, 2500)); 

    // FIND CONTENT (Main Chat)
    // We try to find the main content container
    let main = document.querySelector("main");
    if (!main) {
        // Fallback: Find the largest container with text
        const divs = Array.from(document.querySelectorAll("div"));
        main = divs.sort((a, b) => b.innerText.length - a.innerText.length)[0]; // Risky but effective
    }

    if (main) {
        const clone = main.cloneNode(true);
        // Cleaning
        clone.querySelectorAll("img, video, svg, script, style, button").forEach(e => e.remove());
        
        const markdown = turndownService.turndown(clone.innerHTML);
        
        if (markdown.length > 20) {
            const blob = new Blob([markdown], {type: "text/markdown"});
            chrome.runtime.sendMessage({
                action: "download_file", 
                url: URL.createObjectURL(blob), 
                filename: `RAWchive/${dateStr}/${cleanTitle}.md`
            });
        }
    }
  }
  showToast("✅ BATCH FINISHED IN THIS FRAME", 5000);
}
"""

def apply_god_mode():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    # 1. Write Manifest
    with open(os.path.join(PROJECT_PATH, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(MANIFEST_JSON)

    # 2. Write Content Script
    with open(os.path.join(PROJECT_PATH, "content.js"), "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)

    print("\n✅ GOD MODE ENABLED.")
    print("1. Chrome -> Extensions -> RELOAD Gemini Hoarder")
    print("2. Gemini Page -> REFRESH (F5)")
    print("3. Try Batch Archive.")
    print("(Note: If you see multiple 'Toasts' appear, that's good! It means multiple frames are active.)")

if __name__ == "__main__":
    apply_god_mode()