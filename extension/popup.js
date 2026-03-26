// popup.js — AI Data Extractor v2.0

let currentUrl = "";
let selectedFmtScrape = "csv";
let selectedFmtMed = "csv";
let uploadedFiles = [];  // [{name, content}]

// ── Tab switching ──────────────────────────────────────────
function switchTab(tab) {
  ["scrape","medical"].forEach(t => {
    document.getElementById("tab-" + t).classList.toggle("active", t === tab);
    document.getElementById("panel-" + t).classList.toggle("active", t === tab);
  });
}

// Attach tab click listeners (CSP blocks inline onclick in extensions)
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("tab-scrape").addEventListener("click", () => switchTab("scrape"));
  document.getElementById("tab-medical").addEventListener("click", () => switchTab("medical"));

  // Upload zone click → trigger file input
  document.getElementById("upload-zone").addEventListener("click", () => {
    document.getElementById("file-input").click();
  });
});

// ── Get current tab URL ────────────────────────────────────
chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
  if (tabs[0]) {
    currentUrl = tabs[0].url;
    document.getElementById("url-bar").textContent = currentUrl;
  }
});

// ── Format selectors ───────────────────────────────────────
document.querySelectorAll("#panel-scrape .fmt-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#panel-scrape .fmt-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedFmtScrape = btn.dataset.fmt;
  });
});

document.querySelectorAll("#med-fmt-row .fmt-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#med-fmt-row .fmt-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedFmtMed = btn.dataset.fmt;
  });
});

// ── Chat helpers ───────────────────────────────────────────
function addMsg(chatId, text, type = "bot") {
  const chat = document.getElementById(chatId);
  const div = Object.assign(document.createElement("div"), {
    className: `msg ${type}`,
    textContent: text
  });
  chat.appendChild(div);
  chat.scrollTop = 99999;
}

function addResult(chatId, records, summary, fmt, filename) {
  const chat = document.getElementById(chatId);
  const div = document.createElement("div");
  div.className = "result-box";
  div.innerHTML = `
    <span class="count">${records.length} records</span>
    ${summary ? `<div style="font-size:10px;margin-bottom:4px;color:#3fb950">${summary}</div>` : ""}
    <div style="font-size:10px">Format: <strong>${fmt.toUpperCase()}</strong></div>
    <div class="dl-btn" id="dl-${chatId}">Download ${fmt.toUpperCase()}</div>
  `;
  chat.appendChild(div);
  chat.scrollTop = 99999;

  div.querySelector(`#dl-${chatId}`).addEventListener("click", () => {
    downloadData(records, fmt, filename);
  });
}

function setLoading(btnId, labelId, spinnerId, on) {
  document.getElementById(btnId).disabled = on;
  document.getElementById(labelId).style.display = on ? "none" : "inline";
  document.getElementById(spinnerId).style.display = on ? "block" : "none";
}

// ── Download helper ────────────────────────────────────────
function downloadData(records, fmt, filename) {
  let blob, fname;
  if (fmt === "json") {
    blob = new Blob([JSON.stringify(records, null, 2)], {type: "application/json"});
    fname = filename + ".json";
  } else {
    const keys = Object.keys(records[0] || {});
    const csv = [
      keys.join(","),
      ...records.map(r => keys.map(k => {
        const v = String(r[k] ?? "").replace(/"/g, '""');
        return v.includes(",") || v.includes("\n") ? `"${v}"` : v;
      }).join(","))
    ].join("\n");
    blob = new Blob([csv], {type: "text/csv"});
    fname = filename + ".csv";
  }
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), {href: url, download: fname});
  a.click();
  URL.revokeObjectURL(url);
}

// ══════════════════════════════════════════════════════════
//  WEB SCRAPING MODE
// ══════════════════════════════════════════════════════════

addMsg("scrape-chat", "Navigate to Amazon.in or Flipkart.com, then describe what data you want to scrape.", "bot");

document.getElementById("scrape-btn").addEventListener("click", () => {
  const prompt = document.getElementById("scrape-prompt").value.trim();
  const pages  = parseInt(document.getElementById("pages-input").value) || 10;

  if (!prompt) return;
  if (!currentUrl.includes("amazon.in") && !currentUrl.includes("flipkart.com")) {
    addMsg("scrape-chat", "Please navigate to Amazon.in or Flipkart.com first, then click Scrape.", "bot");
    return;
  }

  addMsg("scrape-chat", prompt, "user");
  document.getElementById("scrape-prompt").value = "";
  setLoading("scrape-btn", "scrape-label", "scrape-spinner", true);
  addMsg("scrape-chat", `Starting agent — will scrape ${pages} pages...`, "status");

  chrome.runtime.sendMessage({
    type: "AGENT",
    url: currentUrl,
    request: prompt,
    format: selectedFmtScrape,
    pages: pages
  }, response => {
    setLoading("scrape-btn", "scrape-label", "scrape-spinner", false);

    if (chrome.runtime.lastError) {
      addMsg("scrape-chat", "Native host not connected. Start the Python backend first.", "bot");
      return;
    }
    if (response?.error) { addMsg("scrape-chat", "Error: " + response.error, "bot"); return; }

    const { records = [], summary = "" } = response;
    if (!records.length) { addMsg("scrape-chat", "No records found. Try a different prompt.", "bot"); return; }

    addResult("scrape-chat", records, summary, selectedFmtScrape, "scraped_data");
  });
});

// ══════════════════════════════════════════════════════════
//  MEDICAL OCR MODE
// ══════════════════════════════════════════════════════════

addMsg("med-chat", "Upload all OCR .txt files for one patient, enter a Patient ID, then click Extract Fields.", "bot");

// ── File upload via click ──────────────────────────────────
document.getElementById("file-input").addEventListener("change", e => {
  handleFiles(Array.from(e.target.files));
});

// ── Drag and drop ──────────────────────────────────────────
const zone = document.getElementById("upload-zone");
zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("dragover"); });
zone.addEventListener("dragleave", e => zone.classList.remove("dragover"));
zone.addEventListener("drop", e => {
  e.preventDefault();
  zone.classList.remove("dragover");
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith(".txt"));
  handleFiles(files);
});

function handleFiles(files) {
  const txtFiles = files.filter(f => f.name.endsWith(".txt"));
  if (!txtFiles.length) {
    addMsg("med-chat", "Please upload .txt files only.", "bot"); return;
  }

  let loaded = 0;
  txtFiles.forEach(file => {
    const reader = new FileReader();
    reader.onload = e => {
      // Avoid duplicates
      if (!uploadedFiles.find(f => f.name === file.name)) {
        uploadedFiles.push({ name: file.name, content: e.target.result });
      }
      loaded++;
      if (loaded === txtFiles.length) renderFileList();
    };
    reader.readAsText(file);
  });
}

function renderFileList() {
  const list = document.getElementById("file-list");
  list.innerHTML = "";
  uploadedFiles.forEach((f, i) => {
    const item = document.createElement("div");
    item.className = "file-item";

    const icon = document.createElement("span");
    icon.style.fontSize = "10px";
    icon.textContent = "📄";

    const fname = document.createElement("span");
    fname.className = "fname";
    fname.textContent = f.name;

    const rm = document.createElement("span");
    rm.className = "rm";
    rm.textContent = "✕";
    rm.addEventListener("click", () => {
      uploadedFiles.splice(i, 1);
      renderFileList();
    });

    item.appendChild(icon);
    item.appendChild(fname);
    item.appendChild(rm);
    list.appendChild(item);
  });

  // Update upload zone hint
  document.querySelector(".upload-zone .hint").innerHTML =
    `<strong>${uploadedFiles.length} file(s) loaded</strong><br>Click to add more`;
}

// ── Extract button ─────────────────────────────────────────
document.getElementById("med-btn").addEventListener("click", () => {
  if (!uploadedFiles.length) {
    addMsg("med-chat", "Please upload at least one .txt OCR file.", "bot"); return;
  }

  const patientId = document.getElementById("patient-id").value.trim() || "patient_001";
  addMsg("med-chat", `Extracting 39 fields for: ${patientId}`, "user");
  setLoading("med-btn", "med-label", "med-spinner", true);

  // Show progress bar
  const progressWrap = document.getElementById("progress-wrap");
  const progressBar  = document.getElementById("progress-bar");
  progressWrap.style.display = "block";
  progressBar.style.width = "10%";

  addMsg("med-chat",
    `Processing ${uploadedFiles.length} file(s)... This may take 30-60 seconds.`,
    "status");

  // Animate progress bar while waiting
  let progress = 10;
  const progressInterval = setInterval(() => {
    progress = Math.min(progress + 5, 85);
    progressBar.style.width = progress + "%";
  }, 2000);

  chrome.runtime.sendMessage({
    type: "MEDICAL",
    patient_id: patientId,
    files: uploadedFiles,   // [{name, content}] — sent to native host
    format: selectedFmtMed
  }, response => {
    clearInterval(progressInterval);
    progressBar.style.width = "100%";
    setTimeout(() => { progressWrap.style.display = "none"; }, 500);

    setLoading("med-btn", "med-label", "med-spinner", false);

    if (chrome.runtime.lastError) {
      addMsg("med-chat", "Native host not connected. Start the Python backend first.", "bot");
      return;
    }
    if (response?.error) { addMsg("med-chat", "Error: " + response.error, "bot"); return; }

    const { records = [], summary = "" } = response;
    if (!records.length) {
      addMsg("med-chat", "Could not extract data. Check that files are valid OCR text.", "bot");
      return;
    }

    addResult("med-chat", records, summary || `Extracted ${Object.keys(records[0]).length} fields for ${patientId}`,
              selectedFmtMed, `medical_${patientId}`);
  });
});