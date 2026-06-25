import os

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- CONTENT SCRIPT (The Brute Force Update) ---
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

// --- HELPER: TOAST (Debug Mode) ---
function showToast(msg, duration = 4000) {
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    // Large, Red/White High Contrast for visibility
    toast.style.cssText = "position:fixed; top:10px; left:10px; background:#000; color:#fff; padding:15px; border:2px solid #f00; border-radius:4px; z-index:999999; font-family:sans-serif; font-size:14px; max-width: 400px; box-shadow: 0 0 20px rgba(0,0,0,0.8);";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- BATCH ARCHIVER (BRUTE FORCE) ---
async function runBatchArchiver() {
  showToast("💥 <b>BRUTE FORCE SCANNING...</b><br>Looking at EVERY link on the page.", 0);
  
  // 1. GET EVERY LINK IN THE DOM
  const allLinks = Array.from(document.querySelectorAll("a"));
  
  // 2. FILTER: FIND THE CHATS
  const chatLinks = allLinks.filter(link => {
      const href = (link.getAttribute("href") || "").toLowerCase();
      const txt = (link.innerText || "").trim().toLowerCase();
      
      // RULE 1: Must look like a chat link (/app/...)
      if (!href.includes("/app/")) return false;
      
      // RULE 2: Ignore "New Chat" buttons (they are also /app/ links)
      if (txt.includes("new chat") || txt === "gemini") return false;
      
      // RULE 3: Must have actual text (Titles)
      if (txt.length < 2) return false;
      
      // RULE 4: Ignore "Upgrade" or "Help" links
      if (txt.includes("upgrade") || txt.includes("help")) return false;

      return true;
  });

  // DEBUG REPORT
  if (chatLinks.length === 0) {
      showToast(`❌ <b>STILL FAILED.</b><br>Scanned ${allLinks.length} total links.<br>0 matched the filter.<br>Please expand the sidebar manually.`, 8000);
      return;
  }

  // 3. ATTEMPT TO SCROLL (To load more)
  // We grab the parent of the first found link and try to scroll it
  showToast(`✅ Found ${chatLinks.length} visible chats.<br>Scrolling to find more...`, 0);
  
  try {
      let scroller = chatLinks[0].closest("div[class*='-container']") || chatLinks[0].parentElement.parentElement;
      if (scroller) {
          for (let i = 0; i < 4; i++) {
             scroller.scrollTop = scroller.scrollHeight;
             await new Promise(r => setTimeout(r, 800));
          }
          // Re-scan to catch lazy-loaded items
          const reScanLinks = Array.from(document.querySelectorAll("a"));
          const newChats = reScanLinks.filter(link => {
             const href = (link.getAttribute("href") || "").toLowerCase();
             const txt = (link.innerText || "").trim().toLowerCase();
             return href.includes("/app/") && !txt.includes("new chat") && txt.length > 1;
          });
          // Add new items to our list
          newChats.forEach(nc => chatLinks.push(nc));
      }
  } catch(e) { console.log("Scroll failed, proceeding with visible links."); }

  // 4. DEDUPLICATE (Remove duplicates by URL)
  const uniqueQueue = [];
  const seenUrls = new Set();
  
  // Reverse the list so we start from OLDEST (usually at bottom) or NEWEST depending on preference.
  // Standard array is Top-to-Bottom.
  chatLinks.forEach(link => {
      if (!seenUrls.has(link.href)) {
          seenUrls.add(link.href);
          uniqueQueue.push(link);
      }
  });

  const total = uniqueQueue.length;
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  showToast(`🚀 <b>STARTING BATCH...</b><br>Queue: ${total} Chats`, 0);

  // 5. EXECUTION LOOP
  for (let i = 0; i < total; i++) {
    const link = uniqueQueue[i];
    const rawTitle = link.innerText;
    const cleanTitle = rawTitle.trim().replace(/[^a-z0-9]/gi, '_').substring(0, 60);
    
    showToast(`<b>[${i+1}/${total}]</b> Archiving:<br>${cleanTitle}`, 0);

    // CLICK
    link.click();
    
    // WAIT (3 Seconds for load)
    await new Promise(r => setTimeout(r, 3000)); 

    // SCRAPE
    const mainChat = document.querySelector("main");
    if (mainChat) {
        const clone = mainChat.cloneNode(true);
        // Strip Assets
        clone.querySelectorAll("img, video, svg, script, style, button, input").forEach(e => e.remove());
        
        const markdown = turndownService.turndown(clone.innerHTML);
        
        if (markdown.length > 50) {
            const blob = new Blob([markdown], {type: "text/markdown"});
            chrome.runtime.sendMessage({
                action: "download_file", 
                url: URL.createObjectURL(blob), 
                filename: `RAWchive/${dateStr}/${cleanTitle}.md`
            });
        }
    }
  }
  showToast("✅ <b>COMPLETE!</b><br>Check Downloads folder.", 6000);
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

def apply_brute_force():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    path = os.path.join(PROJECT_PATH, "content.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)
        
    print(f"🛠️  Updated: {path}")
    print("\n✅ BRUTE FORCE PATCH APPLIED.")
    print("1. Chrome -> Extensions -> Reload Gemini Hoarder")
    print("2. Gemini Page -> Refresh (F5)")
    print("3. Try Batch Archive again.")

if __name__ == "__main__":
    apply_brute_force()