// background.js — routes messages to native Python host

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!["AGENT", "SCRAPE", "MEDICAL"].includes(msg.type)) return;

  const port = chrome.runtime.connectNative("com.ai_scraper.host");

  // Build payload based on message type
  let payload;
  if (msg.type === "MEDICAL") {
    payload = {
      mode:       "medical",
      patient_id: msg.patient_id,
      files:      msg.files,      // array of {name, content}
      format:     msg.format
    };
  } else {
    payload = {
      mode:    "agent",
      url:     msg.url,
      request: msg.request,
      format:  msg.format,
      pages:   msg.pages || 10
    };
  }

  port.postMessage(payload);

  port.onMessage.addListener(response => {
    sendResponse(response);
    port.disconnect();
  });

  port.onDisconnect.addListener(() => {
    if (chrome.runtime.lastError) {
      sendResponse({ error: "Native host not running. Start native_host.py first." });
    }
  });

  return true; // keep async channel open
});