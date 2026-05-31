import os

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- CONTENT SCRIPT (The Logic Update) ---
CONTENT_JS = """
let selectionMode = false;
let turndownService = new TurndownService();

// --- LISTENER ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "start_selection") toggleSelectionMode(true);
  if (request.action === "scrape_all") scrapeContent(document.body, true);
  if (request.action === "batch_archive") runBatchArchiver();
  sendResponse({status: "ok"}); 
});

// --- HELPER: TOAST (Visual Feedback) ---
function showToast(msg, duration = 4000) {
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    // Centered at top, large text
    toast.style.cssText = "position:fixed; top:20px; left:50%; transform:translateX(-50%); background:#222; color:#fff; padding:15px 25px; border-radius:8px; z-index:99999; font-family:sans-serif; font-size:16px; box-shadow:0 4px 15px rgba(0,0,0,0.6); border:1px solid #555; text-align:center;";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- BATCH ARCHIVER (IMPROVED) ---
async function runBatchArchiver() {
  showToast("🕵️‍♀️ <b>Scanning Page...</b>", 0);
  
  // 1. SEARCH FOR HISTORY LINKS (Anywhere on page)
  // Gemini chat links always start with /app/
  let allLinks = Array.from(document.querySelectorAll("a[href^='/app/']"));
  
  // Filter out non-chat links (like 'Help' or empty icons)
  // We assume a real chat title has at least 3 letters.
  let chatLinks = allLinks.filter(link => {
      return link.innerText && link.innerText.trim().length > 2;
  });

  // 2. IF NO LINKS FOUND -> User likely has history closed
  if (chatLinks.length === 0) {
      showToast("❌ <b>CANNOT FIND HISTORY!</b><br>Please click the ☰ Menu icon (Top Left)<br>to open your chat list.", 6000);
      return;
  }

  // 3. SCROLL THE CONTAINER (To load older chats)
  showToast(`found ${chatLinks.length} visible chats...<br>Attempting to scroll for more...`, 0);
  
  // Find the parent container of the first link to scroll it
  let scroller = chatLinks[0].closest("div[class*='-container']") || chatLinks[0].parentElement.parentElement;
  
  if (scroller) {
      for (let i = 0; i < 3; i++) {
         scroller.scrollTop = scroller.scrollHeight;
         await new Promise(r => setTimeout(r, 800));
      }
      // Re-scan after scrolling
      allLinks = Array.from(document.querySelectorAll("a[href^='/app/']"));
      chatLinks = allLinks.filter(l => l.innerText && l.innerText.trim().length > 2);
  }

  const total = chatLinks.length;
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  showToast(`🚀 <b>Starting Batch Archive</b><br>Queue: ${total} conversations`, 0);

  // 4. PROCESS LOOP
  for (let i = 0; i < total; i++) {
    const link = chatLinks[i];
    const rawTitle = link.innerText;
    const cleanTitle = rawTitle.trim().replace(/[^a-z0-9]/gi, '_').substring(0, 60);
    
    showToast(`<b>Processing ${i+1} of ${total}</b><br>${rawTitle}`, 0);

    // CLICK THE CHAT
    link.click();
    
    // WAIT FOR LOAD (Crucial)
    await new Promise(r => setTimeout(r, 2500)); 

    const mainChat = document.querySelector("main");
    if (mainChat) {
        // Clone and Strip Assets
        const clone = mainChat.cloneNode(true);
        // Remove Images, Videos, SVGs to keep it purely text
        clone.querySelectorAll("img, video, svg, script, style, button").forEach(e => e.remove());
        
        const markdown = turndownService.turndown(clone.innerHTML);
        const blob = new Blob([markdown], {type: "text/markdown"});
        
        chrome.runtime.sendMessage({
            action: "download_file", 
            url: URL.createObjectURL(blob), 
            filename: `RAWchive/${dateStr}/${cleanTitle}.md`
        });
    }
  }
  showToast("✅ <b>BATCH COMPLETE!</b><br>Check your Downloads folder.", 5000);
}

// --- STANDARD SCRAPER LOGIC (Unchanged) ---
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
  showToast(includeAssets ? "📦 Zipping..." : "📄 Saving...");
  const zip = new JSZip();
  const assetsFolder = zip.folder("assets");
  const clone = rootElement.cloneNode(true);
  clone.querySelectorAll("script, style, button, svg").forEach(e => e.remove());

  if (includeAssets) {
    const images = clone.querySelectorAll("img");
    let imgCount = 0;
    for (let img of images) {
        if (img.src && img.src.startsWith("http") && !img.src.includes("googleusercontent")) {
            try {
                const blob = await fetch(img.src).then(r => r.blob());
                const filename = `img_${Date.now()}_${imgCount}.png`;
                assetsFolder.file(filename, blob);
                img.src = `assets/${filename}`;
                imgCount++;
            } catch (e) {}
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
"""

def apply_sidebar_fix():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    # We only need to overwrite content.js
    path = os.path.join(PROJECT_PATH, "content.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)
        
    print(f"🛠️  Updated: {path}")
    print("\n✅ PATCH APPLIED.")
    print("1. Go to chrome://extensions -> Click Reload (Circular Arrow)")
    print("2. Go to Gemini -> REFRESH PAGE (F5)")
    print("3. OPEN THE SIDEBAR MENU (Left Side) so the chats are visible.")
    print("4. Click 'Batch Archive History'")

if __name__ == "__main__":
    apply_sidebar_fix()