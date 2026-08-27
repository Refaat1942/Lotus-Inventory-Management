const TEMPLATES = [
  { id: "main", label: "Main Dataset" },
  { id: "targets", label: "Targets" },
  { id: "rank", label: "Rank" },
  { id: "blocked", label: "Blocked Items" },
  { id: "similar", label: "Similar Items" },
];

const UPLOADS = [
  { id: "main_file", label: "1. Main Dataset", required: true, triggersBranches: true },
  { id: "targets_file", label: "2. Targets", required: false, appliesTargets: true },
  { id: "rank_file", label: "3. Rank", required: false },
  { id: "blocked_file", label: "4. Blocked Items", required: false },
  { id: "similar_file", label: "5. Similar Items", required: false },
];

const NAV_ITEMS = [
  { view: "engine", perm: "replenishment_run", icon: "⚡", label: "Engine", sub: "Upload & run" },
  { view: "engine", perm: "replenishment_templates", icon: "📥", label: "Templates", sub: "Download Excel templates", scroll: "templatesSection" },
  { view: "hub", perm: "replenishment", icon: "🏠", label: "Modules", sub: "Back to hub", href: "/hub" },
];

const PAGE_META = {
  engine: { title: "Replenishment Engine", sub: "Follow the steps to run the replenishment engine" },
};

let currentUser = null;
let branches = [];
let branchSectionCollapsed = true;

function updateBranchMeta() {
  const meta = document.getElementById("branchMeta");
  if (!meta) return;
  if (!branches.length) {
    meta.textContent = "";
    return;
  }
  meta.textContent = `${branches.length} branch${branches.length === 1 ? "" : "es"}`;
}

function setBranchSectionCollapsed(collapsed) {
  branchSectionCollapsed = collapsed;
  const section = document.getElementById("branchSection");
  const btn = document.getElementById("branchToggleBtn");
  const label = btn?.querySelector(".collapse-toggle-label");
  if (!section || !btn) return;
  section.classList.toggle("is-collapsed", collapsed);
  btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (label) label.textContent = collapsed ? "Show" : "Hide";
}

function setupBranchCollapse() {
  document.getElementById("branchToggleBtn")?.addEventListener("click", () => {
    setBranchSectionCollapsed(!branchSectionCollapsed);
  });
}
const files = {};

function hasPerm(key) {
  return currentUser?.permissions?.includes(key);
}

function canRepl(key) {
  if (hasPerm(key)) return true;
  if (hasPerm("replenishment") && (key === "replenishment" || key.startsWith("replenishment_"))) return true;
  return false;
}

function navAllowed(perm) {
  if (perm === "replenishment" || perm.startsWith("replenishment_")) return canRepl(perm);
  return hasPerm(perm);
}

async function api(url, options = {}) {
  const res = await fetchWithTimeout(url, { credentials: "include", ...options }, options.timeoutMs || 600000);
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
  if (b.app_title) document.getElementById("brandTitle").textContent = "Replenishment";
  if (b.footer_text) document.getElementById("appFooter").textContent = b.footer_text;
  applyAccentColor(b.accent_color);
  const url = b.logo_url || null;
  setLogoImage(document.getElementById("brandLogoImg"), document.getElementById("brandLogoText"), document.getElementById("brandLogo"), url);
}

function buildSidebar() {
  const nav = document.getElementById("sidebarNav");
  nav.innerHTML = "";
  const seen = new Set();
  NAV_ITEMS.forEach((item) => {
    if (!navAllowed(item.perm)) return;
    const key = item.view + (item.scroll || "") + (item.href || "");
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
  const canRun = canRepl("replenishment_run");
  const canTemplates = canRepl("replenishment_templates");
  document.getElementById("templatesSection")?.classList.toggle("hidden", !canTemplates);
  document.getElementById("uploadSection")?.classList.toggle("hidden", !canRun);
  document.getElementById("branchSection")?.classList.toggle("hidden", !canRun || branches.length === 0);
  document.getElementById("actionsSection")?.classList.toggle("hidden", !canRun && !canRepl("replenishment_history"));
  document.getElementById("runBtn")?.classList.toggle("hidden", !canRun);
  document.getElementById("clearBtn")?.classList.toggle("hidden", !canRun);
  document.getElementById("historyBtn")?.classList.toggle("hidden", !canRepl("replenishment_history"));
  if (!canRun && !canTemplates) {
    document.getElementById("view-engine")?.classList.add("hidden");
  } else {
    document.getElementById("view-engine")?.classList.remove("hidden");
  }
  buildSidebar();
  const first = NAV_ITEMS.find((i) => navAllowed(i.perm));
  if (first && !first.href) navigateTo(first.view, first.scroll);
}

function updateJourney() {
  const steps = document.querySelectorAll(".journey-step");
  const hasTemplates = canRepl("replenishment_templates");
  const mainReady = !!files.main_file;
  const branchReady = mainReady && branches.length > 0;
  steps.forEach((s) => s.classList.remove("active", "done"));
  if (hasTemplates) document.querySelector('[data-step="1"]')?.classList.add("done");
  if (mainReady) {
    document.querySelector('[data-step="1"]')?.classList.add("done");
    document.querySelector('[data-step="2"]')?.classList.add("done");
    if (branchReady) {
      document.querySelector('[data-step="3"]')?.classList.add("done");
      document.querySelector('[data-step="4"]')?.classList.add("active");
    } else {
      document.querySelector('[data-step="3"]')?.classList.add("active");
    }
  } else if (Object.keys(files).length) {
    document.querySelector('[data-step="1"]')?.classList.add("done");
    document.querySelector('[data-step="2"]')?.classList.add("active");
  } else if (hasTemplates) {
    document.querySelector('[data-step="1"]')?.classList.add("active");
  }
}

function updateRunButton() {
  if (!canRepl("replenishment_run")) return;
  document.getElementById("runBtn").disabled = !files.main_file;
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
    btn.addEventListener("click", () => {
      window.location.href = `/api/replenishment/templates/${id}`;
    });
    grid.appendChild(btn);
  });
}

function renderBranchTable(list) {
  branches = list;
  document.getElementById("branchBody").innerHTML = list
    .map(
      (b) => `
    <tr>
      <td>${b}</td>
      <td><input type="number" min="0" step="1" data-branch="${b}" data-type="pharma" placeholder="Pharma" /></td>
      <td><input type="number" min="0" step="1" data-branch="${b}" data-type="non_pharma" placeholder="Non-Pharma" /></td>
    </tr>`
    )
    .join("");
  if (list.length) {
    document.getElementById("branchSection").classList.remove("hidden");
    setBranchSectionCollapsed(true);
  }
  updateBranchMeta();
  applyPermissions();
  updateRunButton();
}

async function loadBranchesFromMain(file) {
  const fd = new FormData();
  fd.append("main_file", file);
  const res = await api("/api/replenishment/branches", { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to load branches");
  }
  const data = await res.json();
  renderBranchTable(data.branches);
  showToast(`Loaded ${data.branches.length} branches from main dataset`);
}

async function applyTargetsFromFile(file) {
  if (!files.main_file) {
    showToast("Upload Main Dataset first", "error");
    return;
  }
  const fd = new FormData();
  fd.append("main_file", files.main_file);
  fd.append("targets_file", file);
  const res = await api("/api/replenishment/apply-targets", { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to apply targets");
  }
  const data = await res.json();
  Object.entries(data.targets).forEach(([branch, vals]) => {
    document.querySelectorAll(`#branchBody input[data-branch="${CSS.escape(branch)}"]`).forEach((inp) => {
      inp.value = vals[inp.dataset.type] ?? "";
    });
  });
  showToast("Targets applied to branch configuration");
}

function setupUpload(uploadDef) {
  const item = document.createElement("div");
  item.className = "upload-item";
  item.innerHTML = `
    <label>${uploadDef.label}${uploadDef.required ? ' <span class="req">*</span>' : ""}</label>
    <div class="file-drop" data-id="${uploadDef.id}">
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
    input.value = "";
    let stored;
    try {
      stored = await prepareUploadFile(file);
    } catch {
      showToast("Could not read file", "error");
      return;
    }
    files[uploadDef.id] = stored;
    drop.classList.add("loaded");
    filenameEl.textContent = stored.name;
    try {
      if (uploadDef.triggersBranches) await loadBranchesFromMain(stored);
      if (uploadDef.appliesTargets) await applyTargetsFromFile(stored);
    } catch (err) {
      showToast(err.message, "error");
      delete files[uploadDef.id];
      drop.classList.remove("loaded");
      filenameEl.textContent = "No file selected";
      return;
    }
    updateRunButton();
  };

  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("change", () => setFile(input.files[0]));
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("dragover");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    setFile(e.dataTransfer.files[0]);
  });
}

function getBranchTargets() {
  const map = {};
  branches.forEach((b) => {
    map[b] = { pharma: 0, non_pharma: 0 };
  });
  document.querySelectorAll("#branchBody input").forEach((inp) => {
    const b = inp.dataset.branch;
    const val = parseFloat(inp.value);
    if (!map[b]) map[b] = { pharma: 0, non_pharma: 0 };
    map[b][inp.dataset.type] = Number.isFinite(val) ? val : 0;
  });
  return map;
}

async function downloadBlob(response, fallbackName) {
  const blob = await response.blob();
  const match = (response.headers.get("Content-Disposition") || "").match(/filename="(.+)"/);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match ? match[1] : fallbackName;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function initSession() {
  const res = await api("/api/auth/me");
  if (!res.ok) {
    window.location.href = "/login";
    return;
  }
  const data = await res.json();
  currentUser = data.user;
  if (!hasPerm("replenishment")) {
    window.location.href = "/hub";
    return;
  }
  document.getElementById("userBadge").textContent = currentUser.is_admin
    ? `${currentUser.username} · Admin`
    : currentUser.username;
  if (data.replenishment_version) {
    document.getElementById("pageSub").textContent += ` · ${data.replenishment_version}`;
  }
  applyBranding(data.branding);

  if (canRepl("replenishment_templates")) buildTemplates();
  if (canRepl("replenishment_run")) {
    UPLOADS.forEach(setupUpload);
    setupBranchCollapse();
  }
  applyPermissions();
}

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

document.getElementById("clearBtn").addEventListener("click", () => {
  UPLOADS.forEach(({ id }) => delete files[id]);
  branches = [];
  document.getElementById("branchBody").innerHTML = "";
  document.getElementById("branchSection").classList.add("hidden");
  updateBranchMeta();
  document.querySelectorAll(".file-drop").forEach((drop) => {
    drop.classList.remove("loaded");
    drop.querySelector(".filename").textContent = "No file selected";
    drop.querySelector("input").value = "";
  });
  updateRunButton();
  showToast("Cleared");
});

document.getElementById("historyBtn").addEventListener("click", async () => {
  try {
    const res = await api("/api/replenishment/history");
    if (!res.ok) throw new Error((await res.json()).detail || "No history");
    await downloadBlob(res, "Lotus_Replenishment_History.xlsx");
    showToast("History exported");
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("runBtn").addEventListener("click", async () => {
  if (!files.main_file) {
    showToast("Upload Main Dataset first", "error");
    return;
  }
  const form = new FormData();
  form.append("main_file", files.main_file);
  form.append("branch_targets", JSON.stringify(getBranchTargets()));
  ["rank_file", "blocked_file", "similar_file"].forEach((id) => {
    if (files[id]) form.append(id, files[id]);
  });

  const panel = document.getElementById("progressPanel");
  const fill = document.getElementById("progressFill");
  panel.classList.remove("hidden");
  document.getElementById("progressText").textContent = "Running replenishment engine...";
  fill.style.width = "30%";
  document.getElementById("runBtn").disabled = true;

  try {
    const res = await api("/api/replenishment/process", { method: "POST", body: form });
    fill.style.width = "90%";
    if (!res.ok) throw new Error((await res.json()).detail || "Processing failed");
    await downloadBlob(res, "Replenishment_Results.xlsx");
    fill.style.width = "100%";
    document.getElementById("progressText").textContent = "Export completed";
    showToast("Results exported successfully");
  } catch (err) {
    showToast(err.message, "error");
    document.getElementById("progressText").textContent = err.message;
  } finally {
    setTimeout(() => panel.classList.add("hidden"), 1500);
    fill.style.width = "0%";
    updateRunButton();
  }
});

initSession();
