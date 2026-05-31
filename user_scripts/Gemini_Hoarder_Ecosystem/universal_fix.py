import os

# --- CONFIGURATION ---
# UPDATE THIS PATH if needed
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- CONTENT SCRIPT (The "Universal Vision" Update) ---
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
    // Centered, High Contrast
    toast.style.cssText = "position:fixed; top:20px; left:50%; transform:translateX(-50%); background:#111; color:#0f0; padding:15px 25px; border-radius:8px; z-index:99999; font-family:monospace; font-size:14px; box-shadow:0 10px 30px rgba(0,0,0,0.7); border:1px solid #333; text-align:center; max-width:80%;";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- BATCH ARCHIVER (UNIVERSAL FIX) ---
async function runBatchArchiver() {
  showToast("🕵️‍♀️ <b>Scanning Sidebar...</b>", 0);
  
  // STRATEGY 1: Get ALL links in the navigation container
  // We look for 'nav' or role='navigation'
  const nav = document.querySelector("nav") || document.querySelector("[role='navigation']");
  
  let chatLinks = [];

  if (nav) {
      // If we found a nav, grab ALL visible links inside it
      const allNavLinks = Array.from(nav.querySelectorAll("a"));
      
      // Filter: Must have text, and NOT be a system link
      chatLinks = allNavLinks.filter(l => {
          const txt = l.innerText.toLowerCase().trim();
          return txt.length > 0 && 
                 !txt.includes("help") && 
                 !txt.includes("setting") && 
                 !txt.includes("activity") &&
                 !txt.includes("google") && // Copyright links
                 l.offsetParent !== null; // Must be visible
      });
  } 
  
  // STRATEGY 2: If Nav failed, brute force search for /app/ links anywhere
  if (chatLinks.length === 0) {
      // "href*=" means CONTAINS, not starts-with. Handles https:// prefix.
      const rawLinks = Array.from(document.querySelectorAll("a[href*='/app/']"));
      chatLinks = rawLinks.filter(l => l.innerText && l.innerText.trim().length > 2);
  }

  // CHECK RESULT
  if (chatLinks.length === 0) {
      const debugInfo = nav ? "Found <nav> but filtered all links." : "Could not find <nav> tag.";
      showToast(`❌ <b>STILL BLIND!</b><br>${debugInfo}<br>Please ensure Sidebar is OPEN.`, 6000);
      return;
  }

  // SCROLLING LOGIC (To load older chats)
  showToast(`✅ Found ${chatLinks.length} chats.<br>Scrolling for more...`, 0);
  
  // Find the scroller container
  let scroller = nav ? (nav.closest("div[class*='-container']") || nav) : chatLinks[0].parentElement.parentElement;
  
  if (scroller) {
      for (let i = 0; i < 4; i++) {
         scroller.scrollTop = scroller.scrollHeight;
         await new Promise(r => setTimeout(r, 600));
      }
      // Re-scan DOM after scroll
      if (nav) {
          const allNavLinks = Array.from(nav.querySelectorAll("a"));
          chatLinks = allNavLinks.filter(l => {
              const txt = l.innerText.toLowerCase().trim();
              return txt.length > 0 && 
                     !txt.includes("help") && 
                     !txt.includes("setting") && 
                     !txt.includes("activity") &&
                     !txt.includes("google") &&
                     l.offsetParent !== null;
          });
      }
  }

  // REMOVE DUPLICATES (Scrolling often creates duplicate DOM entries in virtual lists)
  chatLinks = [...new Set(chatLinks)];
  const total = chatLinks.length;
  
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  showToast(`🚀 <b>Archiving ${total} Conversations</b>`, 0);

  // EXECUTION LOOP
  for (let i = 0; i < total; i++) {
    const link = chatLinks[i];
    const rawTitle = link.innerText;
    // Sanitize Title
    const cleanTitle = rawTitle.trim().replace(/[^a-z0-9]/gi, '_').substring(0, 60);
    
    showToast(`<b>[${i+1}/${total}]</b> Downloading:<br>${cleanTitle}`, 0);

    // CLICK
    link.click();
    
    // WAIT (Give Gemini 2.5s to render the new chat)
    await new Promise(r => setTimeout(r, 2500)); 

    const mainChat = document.querySelector("main");
    if (mainChat) {
        // Clone
        const clone = mainChat.cloneNode(true);
        // Clean
        clone.querySelectorAll("img, video, svg, script, style, button").forEach(e => e.remove());
        
        // Convert
        const markdown = turndownService.turndown(clone.innerHTML);
        const blob = new Blob([markdown], {type: "text/markdown"});
        
        // Send to Background
        chrome.runtime.sendMessage({
            action: "download_file", 
            url: URL.createObjectURL(blob), 
            filename: `RAWchive/${dateStr}/${cleanTitle}.md`
        });
    }
  }
  showToast("✅ <b>BATCH COMPLETE!</b>", 5000);
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

def apply_universal_fix():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    path = os.path.join(PROJECT_PATH, "content.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)
        
    print(f"🛠️  Updated: {path}")
    print("\n✅ UNIVERSAL PATCH APPLIED.")
    print("1. Chrome -> Extensions -> Reload Gemini Hoarder")
    print("2. Gemini Page -> Refresh (F5)")
    print("3. Try Batch Archive again.")

if __name__ == "__main__":
    apply_universal_fix()