const TEMPLATES = [
  { id: "main", label: "Main Data" },
  { id: "targets", label: "Targets" },
  { id: "purchase_targets", label: "Purchase Trg" },
  { id: "rank", label: "Rank" },
  { id: "blocked", label: "Blocked Items" },
  { id: "blocked_os", label: "Blocked OS" },
  { id: "avoid_zero", label: "Avoid Zero" },
  { id: "similar", label: "Similar" },
];

const UPLOADS = [
  { id: "main_file", label: "1. ERP Sheet", required: true },
  { id: "targets_file", label: "2. Targets", required: true },
  { id: "purchase_targets_file", label: "2.b Purchase Trg", required: false },
  { id: "rank_file", label: "3. Rank", required: true },
  { id: "avoid_zero_file", label: "4. Avoid Zero", required: true },
  { id: "blocked_file", label: "5. Blocked Items", required: false },
  { id: "blocked_os_file", label: "6. Blocked OS", required: false },
  { id: "similar_file", label: "7. Similar", required: false },
];

const NAV_ITEMS = [
  { view: "engine", perm: "engine_run", icon: "⚡", label: "Inventory Engine", sub: "Upload & run engine" },
  { view: "engine", perm: "templates", icon: "📥", label: "Templates", sub: "Download Excel templates", scroll: "templatesSection" },
  { view: "hub", perm: "purchase", icon: "🏠", label: "Modules", sub: "Back to module hub", href: "/hub" },
];

const PAGE_META = {
  engine: { title: "Inventory Engine", sub: "Follow the steps to run the smart inventory engine" },
};

let currentUser = null;
const files = {};
let lastFinishedJobId = null;

const JOB_STORAGE_KEY = "lotus_engine_job_id";

function ensureDownloadButton() {
  let btn = document.getElementById("downloadResultBtn");
  if (!btn) {
    const actions = document.querySelector("#actionsSection .actions");
    if (!actions) return null;
    btn = document.createElement("button");
    btn.type = "button";
    btn.id = "downloadResultBtn";
    btn.className = "btn btn-primary btn-lg";
    btn.textContent = "Download Excel Result";
    actions.insertBefore(btn, actions.firstChild);
  }
  return btn;
}

function showJobRecoveryBanner(jobId) {
  const banner = document.getElementById("jobRecoveryBanner");
  const btn = document.getElementById("jobRecoveryDownload");
  if (!banner || !btn) return;
  banner.classList.remove("hidden");
  btn.onclick = async () => {
    try {
      await downloadEngineResult(jobId);
    } catch (err) {
      showToast(err.message, "error");
    }
  };
}

function hideJobRecoveryBanner() {
  document.getElementById("jobRecoveryBanner")?.classList.add("hidden");
}

function hideDownloadButton() {
  const btn = document.getElementById("downloadResultBtn");
  if (btn) btn.classList.add("hidden");
  lastFinishedJobId = null;
  sessionStorage.removeItem(JOB_STORAGE_KEY);
  hideJobRecoveryBanner();
}

function showDownloadButton(jobId) {
  lastFinishedJobId = jobId;
  sessionStorage.setItem(JOB_STORAGE_KEY, jobId);
  const btn = ensureDownloadButton();
  if (btn) {
    btn.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Download Excel Result";
    btn.onclick = () => downloadEngineResult(jobId);
  }
  showJobRecoveryBanner(jobId);
}

/** Chrome-friendly download — opens file in new tab with session cookie. */
function downloadViaLink(jobId) {
  window.open(`/api/process/async/${jobId}/download`, "_blank", "noopener,noreferrer");
}

async function downloadEngineResult(jobId) {
  const progressText = document.getElementById("progressText");
  const panel = document.getElementById("progressPanel");
  panel?.classList.remove("hidden");
  progressText.textContent = "Checking result…";
  const stRes = await api(`/api/process/async/${jobId}`, { timeoutMs: 60000 });
  if (!stRes.ok) {
    throw new Error("Job not found — run the engine again");
  }
  const st = await stRes.json();
  if (st.status === "failed") {
    throw new Error(st.message || st.error || "Engine failed — fix data and run again");
  }
  if (st.status !== "done") {
    throw new Error("Still processing — wait until progress shows Complete");
  }
  progressText.textContent = "Opening Excel download in Chrome…";
  downloadViaLink(jobId);
  progressText.textContent = "Download started — press Ctrl+J in Chrome to see the file.";
  showToast("Excel download started — check Ctrl+J");
}

async function pollJobUntilDone(jobId, fill, progressText) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 3600; i++) {
    await sleep(2000);
    const stRes = await api(`/api/process/async/${jobId}`, { timeoutMs: 120000 });
    if (!stRes.ok) throw new Error("Lost connection while processing");
    const st = await stRes.json();
    const pct = Math.max(10, Math.min(98, (st.progress || 0) * 100));
    fill.style.width = `${pct}%`;
    progressText.textContent = st.message || st.status || "Processing…";
    if (st.status === "done") return st;
    if (st.status === "failed") throw new Error(st.message || st.error || "Engine failed");
  }
  throw new Error("Processing timed out on server — contact admin");
}

function hasPerm(key) {
  return currentUser?.permissions?.includes(key);
}

async function api(url, options = {}) {
  const res = await fetchWithTimeout(url, { credentials: "include", ...options }, options.timeoutMs || 3600000);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (res.status === 403) {
    window.location.href = "/hub";
    throw new Error("Access denied");
  }
  return res;
}

function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove("show"), 4500);
}

function applyBranding(b) {
  if (!b) return;
  if (b.app_title) {
    document.getElementById("brandTitle").textContent = b.app_title;
    document.title = b.app_title;
  }
  if (b.app_tagline) document.getElementById("brandTagline").textContent = b.app_tagline;
  if (b.footer_text) document.getElementById("appFooter").textContent = b.footer_text;
  applyAccentColor(b.accent_color);
  const url = b.logo_url || null;
  setLogoImage(
    document.getElementById("brandLogoImg"),
    document.getElementById("brandLogoText"),
    document.getElementById("brandLogo"),
    url
  );
}

function buildSidebar() {
  const nav = document.getElementById("sidebarNav");
  nav.innerHTML = "";
  const seen = new Set();
  NAV_ITEMS.forEach((item) => {
    if (!hasPerm(item.perm)) return;
    const key = item.view + (item.scroll || "");
    if (seen.has(key)) return;
    seen.add(key);
    const btn = document.createElement(item.href ? "a" : "button");
    if (item.href) {
      btn.href = item.href;
      btn.className = "nav-item";
    } else {
      btn.type = "button";
      btn.className = "nav-item";
      btn.dataset.view = item.view;
      if (item.scroll) btn.dataset.scroll = item.scroll;
      btn.addEventListener("click", () => navigateTo(item.view, item.scroll));
    }
    btn.innerHTML = `<span class="nav-icon">${item.icon}</span><span class="nav-text"><strong>${item.label}</strong><small>${item.sub}</small></span>`;
    nav.appendChild(btn);
  });
}

function navigateTo(view, scrollId) {
  document.querySelectorAll(".view").forEach((v) => {
    v.classList.remove("active");
    v.classList.add("hidden");
  });
  const target = document.getElementById(`view-${view}`);
  if (target) {
    target.classList.remove("hidden");
    target.classList.add("active");
  }
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.view === view && (!scrollId || n.dataset.scroll === scrollId));
  });
  const meta = PAGE_META[view] || PAGE_META.engine;
  document.getElementById("pageTitle").textContent = scrollId === "templatesSection" ? "Download Templates" : meta.title;
  document.getElementById("pageSub").textContent = meta.sub;
  if (scrollId) {
    setTimeout(() => document.getElementById(scrollId)?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
  }
}

function applyPermissions() {
  const canEngine = hasPerm("engine_run");
  const canTemplates = hasPerm("templates");
  document.getElementById("templatesSection")?.classList.toggle("hidden", !canTemplates);
  document.getElementById("uploadSection")?.classList.toggle("hidden", !canEngine);
  document.getElementById("configSection")?.classList.toggle("hidden", !canEngine);
  document.getElementById("actionsSection")?.classList.toggle("hidden", !canEngine && !hasPerm("history"));
  document.getElementById("runBtn")?.classList.toggle("hidden", !canEngine);
  document.getElementById("clearBtn")?.classList.toggle("hidden", !canEngine);
  document.getElementById("historyBtn")?.classList.toggle("hidden", !hasPerm("history"));
  if (!canEngine && !canTemplates) {
    document.getElementById("view-engine")?.classList.add("hidden");
  } else {
    document.getElementById("view-engine")?.classList.remove("hidden");
  }
  buildSidebar();
  const first = NAV_ITEMS.find((i) => hasPerm(i.perm));
  if (first) navigateTo(first.view, first.scroll);
}

function updateJourney() {
  const steps = document.querySelectorAll(".journey-step");
  const hasTemplates = hasPerm("templates");
  const required = UPLOADS.filter((u) => u.required).map((u) => u.id);
  const uploadsReady = required.every((id) => files[id]);
  steps.forEach((s) => s.classList.remove("active", "done"));
  if (hasTemplates) document.querySelector('[data-step="1"]')?.classList.add("done");
  if (uploadsReady) {
    document.querySelector('[data-step="1"]')?.classList.add("done");
    document.querySelector('[data-step="2"]')?.classList.add("done");
    document.querySelector('[data-step="3"]')?.classList.add("active");
    document.querySelector('[data-step="4"]')?.classList.add("active");
  } else if (Object.keys(files).length) {
    document.querySelector('[data-step="1"]')?.classList.add("done");
    document.querySelector('[data-step="2"]')?.classList.add("active");
  } else if (hasTemplates) {
    document.querySelector('[data-step="1"]')?.classList.add("active");
  }
}

function updateRunButton() {
  if (!hasPerm("engine_run")) return;
  const required = UPLOADS.filter((u) => u.required);
  const missing = required.filter((u) => !files[u.id]).map((u) => u.label);
  const ready = missing.length === 0;
  const runBtn = document.getElementById("runBtn");
  const statusEl = document.getElementById("runStatus");
  runBtn.disabled = !ready;
  if (statusEl) {
    statusEl.textContent = ready
      ? "All required files loaded. Click Run to process."
      : `Waiting for: ${missing.join(", ")}`;
    statusEl.classList.toggle("ready", ready);
  }
  updateJourney();
}

function buildTemplates() {
  const grid = document.getElementById("templateGrid");
  grid.innerHTML = "";
  TEMPLATES.forEach(({ id, label }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-template";
    btn.textContent = label;
    btn.addEventListener("click", () => { window.location.href = `/api/templates/${id}`; });
    grid.appendChild(btn);
  });
}

function setupUpload({ id, label, required }, index) {
  const item = document.createElement("div");
  item.className = "upload-item";
  item.innerHTML = `
    <label>${label}${required ? ' <span class="req">*</span>' : ""}</label>
    <div class="file-drop" data-id="${id}">
      <span class="drop-icon">📄</span>
      <span>Drop file or click</span>
      <span class="filename">No file selected</span>
      <input type="file" accept=".xlsx,.xls" />
    </div>`;
  document.getElementById("uploadGrid").appendChild(item);
  const drop = item.querySelector(".file-drop");
  const input = item.querySelector("input");
  const filenameEl = item.querySelector(".filename");
  const setFile = async (file) => {
    if (!file) return;
    if (!/\.(xlsx|xls)$/i.test(file.name)) {
      showToast("Please upload an Excel file (.xlsx or .xls)", "error");
      return;
    }
    drop.classList.remove("loaded");
    setDropLoading(drop, true, `Reading ${formatFileSize(file.size)}...`);
    try {
      const stored = await prepareUploadFile(file);
      if (!stored) throw new Error("Empty file");
      files[id] = stored;
      drop.classList.add("loaded");
      filenameEl.textContent = `${stored.name} (${formatFileSize(stored.size)})`;
      showToast(`${label} loaded`);
      updateRunButton();
      if (UPLOADS.filter((u) => u.required).every((u) => files[u.id])) {
        showToast("All required files ready — click Run", "success");
        document.getElementById("actionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      delete files[id];
      drop.classList.remove("loaded");
      filenameEl.textContent = "Upload failed — try again";
      showToast(err.message || "Could not read file", "error");
      updateRunButton();
    } finally {
      setDropLoading(drop, false);
      input.value = "";
    }
  };
  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("change", () => setFile(input.files[0]));
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragover"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("dragover"); setFile(e.dataTransfer.files[0]); });
}

async function initSession() {
  const res = await api("/api/auth/me");
  if (!res.ok) { window.location.href = "/login"; return; }
  const data = await res.json();
  currentUser = data.user;
  if (!hasPerm("purchase")) {
    window.location.href = "/hub";
    return;
  }
  document.getElementById("userBadge").textContent = currentUser.is_admin ? `${currentUser.username} · Admin` : currentUser.username;
  applyBranding(data.branding);
  if (hasPerm("templates")) buildTemplates();
  if (hasPerm("engine_run")) UPLOADS.forEach(setupUpload);
  applyPermissions();
  await recoverEngineJobIfAny();
}

async function recoverEngineJobIfAny() {
  if (!hasPerm("engine_run")) return;
  const saved = sessionStorage.getItem(JOB_STORAGE_KEY);
  if (!saved) return;
  try {
    const stRes = await api(`/api/process/async/${saved}`, { timeoutMs: 30000 });
    if (!stRes.ok) {
      sessionStorage.removeItem(JOB_STORAGE_KEY);
      return;
    }
    const st = await stRes.json();
    const panel = document.getElementById("progressPanel");
    const progressText = document.getElementById("progressText");
    if (st.status === "done") {
      showDownloadButton(saved);
      panel?.classList.remove("hidden");
      progressText.textContent = "Excel is ready — click Download Excel Result.";
      showToast("Your Excel is ready — click Download Excel Result", "success");
    } else if (st.status === "failed") {
      panel?.classList.remove("hidden");
      progressText.textContent = `Last run failed: ${st.message || st.error || "unknown error"}`;
      showToast(st.message || "Last run failed — upload and run again", "error");
      sessionStorage.removeItem(JOB_STORAGE_KEY);
    } else if (st.status === "running" || st.status === "queued") {
      panel?.classList.remove("hidden");
      progressText.textContent = "Resuming previous run…";
      document.getElementById("runBtn").disabled = true;
      const fill = document.getElementById("progressFill");
      await pollJobUntilDone(saved, fill, progressText);
      showDownloadButton(saved);
      progressText.textContent = "Complete! Click Download Excel Result.";
      showToast("Engine finished — click Download Excel Result", "success");
      document.getElementById("runBtn").disabled = false;
    }
  } catch {
    sessionStorage.removeItem(JOB_STORAGE_KEY);
  }
}

document.getElementById("stoThreshold").addEventListener("change", () => {
  document.getElementById("customSto").classList.toggle("hidden", document.getElementById("stoThreshold").value !== "custom");
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

document.getElementById("clearBtn").addEventListener("click", () => {
  UPLOADS.forEach(({ id }) => delete files[id]);
  document.querySelectorAll(".file-drop").forEach((drop) => {
    drop.classList.remove("loaded");
    drop.querySelector(".filename").textContent = "No file selected";
    drop.querySelector("input").value = "";
  });
  hideDownloadButton();
  updateRunButton();
  showToast("Cleared");
});

document.getElementById("historyBtn").addEventListener("click", async () => {
  try {
    const res = await api("/api/history");
    if (!res.ok) throw new Error((await res.json()).detail || "No history");
    await downloadBlob(res, "Lotus_Inventory_History.xlsx");
    showToast("History exported");
  } catch (err) { showToast(err.message, "error"); }
});

async function downloadBlob(response, fallbackName) {
  const blob = await response.blob();
  if (!blob || blob.size === 0) {
    throw new Error("Server returned an empty file — check VPS logs or redeploy latest version");
  }
  const match = (response.headers.get("Content-Disposition") || "").match(/filename="(.+)"/);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match ? match[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

document.getElementById("runBtn").addEventListener("click", async () => {
  const required = UPLOADS.filter((u) => u.required);
  const missing = required.filter((u) => !files[u.id]);
  if (missing.length) {
    showToast(`Missing: ${missing.map((u) => u.label).join(", ")}`, "error");
    return;
  }

  const form = new FormData();
  UPLOADS.forEach(({ id }) => { if (files[id]) form.append(id, files[id]); });
  form.append("zero_overstock", document.getElementById("zeroOverstock").checked ? "true" : "false");
  let threshold = document.getElementById("stoThreshold").value;
  if (threshold === "custom") {
    threshold = document.getElementById("customSto").value;
    if (!threshold) { showToast("Enter STO threshold", "error"); return; }
  }
  form.append("sto_threshold", threshold);

  const panel = document.getElementById("progressPanel");
  const fill = document.getElementById("progressFill");
  const progressText = document.getElementById("progressText");
  const runBtn = document.getElementById("runBtn");
  panel.classList.remove("hidden");
  progressText.textContent = "Uploading files to server…";
  fill.style.width = "10%";
  runBtn.disabled = true;
  ensureDownloadButton()?.classList.add("hidden");
  hideJobRecoveryBanner();

  try {
    const startRes = await api("/api/process/async", {
      method: "POST",
      body: form,
      timeoutMs: 3600000,
    });
    if (!startRes.ok) {
      let detail = "Could not start engine";
      try {
        const data = await startRes.json();
        detail = data.detail || detail;
      } catch {
        detail = await startRes.text() || detail;
      }
      throw new Error(detail);
    }
    const { job_id, version } = await startRes.json();
    sessionStorage.setItem(JOB_STORAGE_KEY, job_id);
    fill.style.width = "15%";
    progressText.textContent = `Engine ${version || ""} started — processing…`;

    await pollJobUntilDone(job_id, fill, progressText);

    fill.style.width = "100%";
    progressText.textContent = "Complete! Click Download Excel Result.";
    showDownloadButton(job_id);
    showToast("Engine finished — click Download Excel Result", "success");
  } catch (err) {
    const saved = sessionStorage.getItem(JOB_STORAGE_KEY);
    const msg = err.name === "AbortError"
      ? "Upload timed out — if processing continued, refresh page or click Download Excel Result"
      : (err.message || "Engine failed");
    progressText.textContent = msg;
    if (saved) {
      showDownloadButton(saved);
      showToast("Try Download Excel Result or refresh the page", "error");
    } else {
      showToast(msg, "error");
    }
  } finally {
    if (!lastFinishedJobId) {
      setTimeout(() => panel.classList.add("hidden"), 6000);
      fill.style.width = "0%";
    }
    updateRunButton();
  }
});

initSession();
