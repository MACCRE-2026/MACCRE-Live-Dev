
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
