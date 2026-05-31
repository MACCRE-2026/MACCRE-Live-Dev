import os

# --- CONFIGURATION ---
PROJECT_PATH = r"F:\Development\Projects\page_scraper"

# --- CONTENT SCRIPT (Shadow DOM Support) ---
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
    toast.style.cssText = "position:fixed; top:10px; left:50%; transform:translateX(-50%); background:#222; color:#0f0; padding:15px; border:1px solid #0f0; border-radius:5px; z-index:999999; font-family:monospace; font-size:14px; text-align:center; box-shadow:0 0 20px rgba(0,0,0,0.8);";
    document.body.appendChild(toast);
  }
  toast.innerHTML = msg;
  if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- HELPER: SHADOW DOM PIERCER ---
// This function recursively searches inside open Shadow Roots
function getAllLinks(root = document.body) {
    let links = Array.from(root.querySelectorAll("a"));
    
    // Find all elements that might have a shadowRoot
    const allElements = root.querySelectorAll('*');
    for (let el of allElements) {
        if (el.shadowRoot) {
            // Recursively dig deeper
            links = links.concat(getAllLinks(el.shadowRoot));
        }
    }
    return links;
}

// --- BATCH ARCHIVER (SHADOW MODE) ---
async function runBatchArchiver() {
  showToast("🔦 <b>PIERCING SHADOW DOM...</b>", 0);
  
  // 1. DEEP SCAN for links
  const allLinks = getAllLinks(document.body);
  
  // 2. FILTER for Chats
  const chatLinks = allLinks.filter(link => {
      const href = (link.getAttribute("href") || "").toLowerCase();
      const txt = (link.innerText || "").trim().toLowerCase();
      
      // Look for /app/ OR logic that suggests it's a history item
      // Sometimes href is not explicitly /app/ in shadow dom, so we rely on context
      const isAppLink = href.includes("/app/");
      const isTitleValid = txt.length > 2 && !txt.includes("new chat") && !txt.includes("upgrade") && !txt.includes("gemini");
      
      return isAppLink && isTitleValid;
  });

  if (chatLinks.length === 0) {
      showToast(`❌ <b>STILL 0 CHATS.</b><br>Scanned ${allLinks.length} total elements.<br>Please ensure you are logged in.`, 8000);
      return;
  }

  showToast(`✅ Found ${chatLinks.length} chats.<br>Scrolling...`, 0);

  // 3. SCROLLING (Try to scroll the parent of the found links)
  try {
      // Find the container (usually a few levels up from the link)
      let scroller = chatLinks[0].closest("div[class*='scroll']") || 
                     chatLinks[0].closest("div[class*='container']") || 
                     chatLinks[0].parentElement.parentElement;
      
      if (scroller) {
          for (let i = 0; i < 3; i++) {
             scroller.scrollTop = scroller.scrollHeight;
             await new Promise(r => setTimeout(r, 800));
          }
          // RESCAN after scrolling (using the Deep Scan again)
          const freshLinks = getAllLinks(document.body);
          const newChats = freshLinks.filter(link => {
             const href = (link.getAttribute("href") || "").toLowerCase();
             const txt = (link.innerText || "").trim().toLowerCase();
             return href.includes("/app/") && txt.length > 2 && !txt.includes("new chat");
          });
          
          // Merge lists
          newChats.forEach(nc => chatLinks.push(nc));
      }
  } catch(e) { console.log("Scroll logic skipped", e); }

  // 4. DEDUPLICATE
  const uniqueQueue = [];
  const seenUrls = new Set();
  chatLinks.forEach(link => {
      // Use href or text as unique key
      const key = link.href || link.innerText;
      if (!seenUrls.has(key)) {
          seenUrls.add(key);
          uniqueQueue.push(link);
      }
  });

  const total = uniqueQueue.length;
  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  showToast(`🚀 <b>STARTING...</b><br>Queue: ${total} Chats`, 0);

  // 5. PROCESS
  for (let i = 0; i < total; i++) {
    const link = uniqueQueue[i];
    const rawTitle = link.innerText || "Untitled_Chat";
    const cleanTitle = rawTitle.trim().replace(/[^a-z0-9]/gi, '_').substring(0, 60);
    
    showToast(`<b>[${i+1}/${total}]</b> Archiving:<br>${cleanTitle}`, 0);

    // CLICK
    link.click();
    
    // WAIT 3s
    await new Promise(r => setTimeout(r, 3000)); 

    // SCRAPE
    // We try to find <main> normally, or inside shadow roots if needed
    let mainChat = document.querySelector("main");
    
    // If <main> is hidden in shadow dom, try to find it
    if (!mainChat) {
        const mains = getAllLinks(document.body).filter(el => el.tagName === "MAIN");
        if (mains.length > 0) mainChat = mains[0];
    }

    if (mainChat) {
        const clone = mainChat.cloneNode(true);
        // Cleaning
        const junk = clone.querySelectorAll("img, video, svg, script, style, button, input, form");
        junk.forEach(e => e.remove());
        
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
  showToast("✅ <b>COMPLETE!</b>", 5000);
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

def apply_shadow_fix():
    if not os.path.exists(PROJECT_PATH):
        print(f"❌ PATH ERROR: Could not find {PROJECT_PATH}")
        return

    path = os.path.join(PROJECT_PATH, "content.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT_JS)
        
    print(f"🛠️  Updated: {path}")
    print("\n✅ SHADOW DOM PATCH APPLIED.")
    print("1. Chrome -> Extensions -> Reload Gemini Hoarder")
    print("2. Gemini Page -> Refresh (F5)")
    print("3. Try Batch Archive again.")

if __name__ == "__main__":
    apply_shadow_fix()