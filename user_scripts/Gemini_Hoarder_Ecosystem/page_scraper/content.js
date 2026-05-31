
let turndownService = new TurndownService();

// --- LISTENER ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "batch_archive") runBatchArchiver();
  sendResponse({status: "ok"}); 
});

// --- TOAST HELPER ---
function showToast(msg, duration = 4000) {
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

// --- RECURSIVE LINK FINDER ---
function getAllClickables(root = document.body) {
    let items = Array.from(root.querySelectorAll("a, div[role='button'], div[role='link']"));
    const allElements = root.querySelectorAll('*');
    for (let el of allElements) {
        if (el.shadowRoot) items = items.concat(getAllClickables(el.shadowRoot));
    }
    return items;
}

// --- BATCH ARCHIVER (UNLIMITED) ---
async function runBatchArchiver() {
  const isIframe = window !== window.top;
  
  // 1. Scan for Chats
  const candidates = getAllClickables(document.body);
  
  // 2. Filter
  const chatLinks = candidates.filter(el => {
      const txt = (el.innerText || "").trim().toLowerCase();
      const isVisible = el.offsetHeight > 0;
      const validText = txt.length > 3 && !txt.includes("new chat") && !txt.includes("upgrade") && !txt.includes("gemini");
      const hasHref = el.tagName === 'A' && el.href.includes("/app/");
      const isRole = el.getAttribute("role") === "link" || el.getAttribute("role") === "button";
      return isVisible && validText && (hasHref || isRole);
  });

  if (chatLinks.length === 0) return;

  showToast(`✅ <b>FRAME LOCKED</b><br>Found ${chatLinks.length} chats.`, 0);

  const dateStr = "RAW" + new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '').toUpperCase();
  
  // 3. REMOVED THE LIMIT (Now processes everything found)
  // We use a simple Set to avoid clicking the exact same element object twice in one run
  const processed = new Set();
  
  for (let i = 0; i < chatLinks.length; i++) {
    const el = chatLinks[i];
    if (processed.has(el)) continue;
    processed.add(el);

    const cleanTitle = (el.innerText || "Chat").trim().replace(/[^a-z0-9]/gi, '_').substring(0, 60);
    
    showToast(`Archiving [${i+1}/${chatLinks.length}]:<br>${cleanTitle}`, 0);

    el.click();
    await new Promise(r => setTimeout(r, 2500)); 

    let main = document.querySelector("main");
    if (!main) {
        const divs = Array.from(document.querySelectorAll("div"));
        main = divs.sort((a, b) => b.innerText.length - a.innerText.length)[0];
    }

    if (main) {
        const clone = main.cloneNode(true);
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
