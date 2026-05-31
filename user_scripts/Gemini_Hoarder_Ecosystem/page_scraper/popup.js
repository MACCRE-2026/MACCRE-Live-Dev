
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
