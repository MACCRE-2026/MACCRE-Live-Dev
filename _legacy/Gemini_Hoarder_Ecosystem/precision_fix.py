import os

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- CONTENT SCRIPT (The Precision Update) ---
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

// --- HELPER: TOAST ---
function showToast(msg, duration = 4000) {
  let toast = document.getElementById("gemini-scraper-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "gemini-scraper-toast";
    toast.style.cssText = "position:fixed; top:20px; left:50%; transform:translateX(-50%); background:#000; color:#0f0; padding:12px 20px; border:1px solid #0f0; border-radius:4px; z-index:99999; font-family:monospace; font-size:14px; text-align:center; box-shadow:0 0 15px rgba(0, 255, 0, 0.2);";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- BATCH ARCHIVER (PRECISION MODE) ---
async function runBatchArchiver() {
  showToast("🔎 <b>Scanning for History...</b>", 0);
  
  // 1. Grab ALL links on the page
  const allLinks = Array.from(document.querySelectorAll("a"));
  
  // 2. INTELLIGENT FILTERING
  const chatLinks = allLinks.filter(link => {
      const txt = (link.innerText || "").trim().toLowerCase();
      const href = (link.getAttribute("href") || "").toLowerCase();
      
      // MUST contain /app/
      if (!href.includes("/app/")) return false;
      
      // BLACKLIST: Explicitly ignore these buttons
      if (txt === "new chat") return false;
      if (txt === "gemini") return false;
      if (txt.includes("upgrade")) return false; // Ignore "Upgrade to Advanced"
      if (txt === "") return false; // Ignore icons without text
      
      // HEURISTIC: Real chat titles are usually longer than 2 chars
      if (txt.length < 2) return false;

      // VISIBILITY: Must be visible (height > 0)
      if (link.offsetHeight === 0) return false;

      return true;
  });

  if (chatLinks.length === 0) {
      showToast("❌ <b>No History Found.</b><br>Is the sidebar open?", 5000);
      return;
  }

  // 3. SCROLL FOR MORE (Target the parent of the first found link)
  showToast(`✅ Found ${chatLinks.length} items.<br>Scrolling sidebar...`, 0);
  let scroller = chatLinks[0].closest("div[class*='-container']") || chatLinks[0].parentElement.parentElement;
  
  if (scroller) {
      for (let i = 0; i < 3; i++) {
         scroller.scrollTop = scroller.scrollHeight;
         await new Promise(r => setTimeout(r, 600));
      }
      // Re-scan after scroll
      // (We duplicate the filter logic here to capture new items)
      const freshLinks = Array.from(document.querySelectorAll("a"));
      const freshChats = freshLinks.filter(link => {
          const txt = (link.innerText || "").trim().toLowerCase();
          const href = (link.getAttribute("href") || "").toLowerCase();
          if (!href.includes("/app/")) return false;
          if (txt === "new chat" || txt === "gemini" || txt.includes("upgrade") || txt.length < 2) return false;
          if (link.offsetHeight === 0) return false;
          return true;
      });
      chatLinks.push(...freshChats);
  }

  // 4. DEDUPLICATE (By Href to ensure we don't click the same chat twice)
  const uniqueLinks = [];
  const seenUrls = new Set();
  chatLinks.forEach(link => {
      const url = link.href;
      if (!seenUrls.has(url)) {
          seenUrls.add(url);
          uniqueLinks.push(link);
      }
  });

  const total = uniqueLinks.length;
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  showToast(`🚀 <b>Queue: ${total} Conversations</b>`, 0);

  // 5. EXECUTION LOOP
  for (let i = 0; i < total; i++) {
    const link = uniqueLinks[i];
    const rawTitle = link.innerText;
    const cleanTitle = rawTitle.trim().replace(/[^a-z0-9]/gi, '_').substring(0, 50);
    
    showToast(`<b>[${i+1}/${total}]</b> Archiving:<br>${cleanTitle}`, 0);

    // CLICK
    link.click();
    
    // WAIT longer (3s) to ensure "New Chat" page is gone and old chat loads
    await new Promise(r => setTimeout(r, 3000)); 

    // SCRAPE
    // We target <main> to avoid scraping the sidebar itself
    const mainChat = document.querySelector("main");
    if (mainChat) {
        const clone = mainChat.cloneNode(true);
        // Nuke non-text elements
        clone.querySelectorAll("img, video, svg, script, style, button, input").forEach(e => e.remove());
        
        const markdown = turndownService.turndown(clone.innerHTML);
        
        // Safety Check: Don't save empty files (failed loads)
        if (markdown.length > 50) {
            const blob = new Blob([markdown], {type: "text/markdown"});
            chrome.runtime.sendMessage({
                action: "download_file", 
                url: URL.createObjectURL(blob), 
                filename: `RAWchive/${dateStr}/${cleanTitle}.md`
            });
        } else {
             console.log("Skipping empty scrape (likely loading error)");
        }
    }
  }
  showToast("✅ <b>ALL DONE.</b>", 6000);
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

def apply_precision_fix():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    path = os.path.join(PROJECT_PATH, "content.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)
        
    print(f"🛠️  Updated: {path}")
    print("\n✅ PRECISION FILTER APPLIED.")
    print("1. Chrome -> Extensions -> Reload Gemini Hoarder")
    print("2. Gemini Page -> Refresh (F5)")
    print("3. Try Batch Archive again.")

if __name__ == "__main__":
    apply_precision_fix()