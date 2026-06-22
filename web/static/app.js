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
  { view: "reports", perm: "reports", icon: "📊", label: "Reports", sub: "Usage & run statistics" },
  { view: "logs", perm: "logs", icon: "📋", label: "Activity Logs", sub: "User actions history" },
  { view: "users", perm: "users_manage", icon: "👥", label: "Users", sub: "Manage access control" },
  { view: "branding", perm: "branding", icon: "🎨", label: "Branding", sub: "Logo & colors" },
];

const PAGE_META = {
  engine: { title: "Inventory Engine", sub: "Follow the steps to run the smart inventory engine" },
  reports: { title: "Reports", sub: "System usage and inventory run statistics" },
  logs: { title: "Activity Logs", sub: "Track all user actions on the system" },
  users: { title: "User Management", sub: "Control who sees what in the application" },
  branding: { title: "Branding", sub: "Customize logo, title, and colors" },
};

let currentUser = null;
let permissionsCatalog = {};
const files = {};

function hasPerm(key) {
  return currentUser?.permissions?.includes(key);
}

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "include", ...options });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}

function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove("show"), 4500);
}

function setLogoImage(imgEl, textEl, containerEl, url) {
  if (!imgEl || !textEl) return;
  if (url) {
    imgEl.src = url + "?t=" + Date.now();
    imgEl.classList.remove("hidden");
    textEl.classList.add("hidden");
    containerEl?.classList.add("has-image");
    imgEl.onerror = () => {
      imgEl.classList.add("hidden");
      textEl.classList.remove("hidden");
      containerEl?.classList.remove("has-image");
    };
  } else {
    imgEl.classList.add("hidden");
    imgEl.removeAttribute("src");
    textEl.classList.remove("hidden");
    containerEl?.classList.remove("has-image");
  }
}

function applyBranding(b) {
  if (!b) return;
  if (b.app_title) {
    document.getElementById("brandTitle").textContent = b.app_title;
    document.title = b.app_title;
  }
  if (b.app_tagline) document.getElementById("brandTagline").textContent = b.app_tagline;
  if (b.footer_text) document.getElementById("appFooter").textContent = b.footer_text;
  if (b.accent_color) {
    document.documentElement.style.setProperty("--accent", b.accent_color);
    document.documentElement.style.setProperty("--accent-hover", b.accent_color);
  }
  const url = b.logo_url || null;
  setLogoImage(
    document.getElementById("brandLogoImg"),
    document.getElementById("brandLogoText"),
    document.getElementById("brandLogo"),
    url
  );
  setLogoImage(
    document.getElementById("brandingLogoImg"),
    document.getElementById("brandingLogoText"),
    document.getElementById("brandingLogoPreview"),
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
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "nav-item";
    btn.dataset.view = item.view;
    if (item.scroll) btn.dataset.scroll = item.scroll;
    btn.innerHTML = `<span class="nav-icon">${item.icon}</span><span class="nav-text"><strong>${item.label}</strong><small>${item.sub}</small></span>`;
    btn.addEventListener("click", () => navigateTo(item.view, item.scroll));
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
  if (view === "reports") loadReports();
  if (view === "logs") loadLogs();
  if (view === "users") loadUsers();
  if (view === "branding") loadBrandingForm();
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
  const required = UPLOADS.filter((u) => u.required).map((u) => u.id);
  document.getElementById("runBtn").disabled = !required.every((id) => files[id]);
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
  const setFile = (file) => {
    if (!file) return;
    files[id] = file;
    drop.classList.add("loaded");
    filenameEl.textContent = file.name;
    updateRunButton();
  };
  input.addEventListener("change", () => setFile(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragover"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("dragover"); setFile(e.dataTransfer.files[0]); });
}

async function initSession() {
  const res = await api("/api/auth/me");
  if (!res.ok) { window.location.href = "/login"; return; }
  const data = await res.json();
  currentUser = data.user;
  permissionsCatalog = data.permissions_catalog || {};
  document.getElementById("userBadge").textContent = currentUser.is_admin ? `${currentUser.username} · Admin` : currentUser.username;
  applyBranding(data.branding);
  if (hasPerm("templates")) buildTemplates();
  if (hasPerm("engine_run")) UPLOADS.forEach(setupUpload);
  initUsers();
  initBranding();
  applyPermissions();
}

async function loadReports() {
  try {
    const res = await api("/api/admin/reports");
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to load reports");
    const d = await res.json();
  document.getElementById("statsGrid").innerHTML = `
    <div class="stat-card"><span class="stat-val">${d.total_engine_runs}</span><span class="stat-label">Engine Runs</span></div>
    <div class="stat-card"><span class="stat-val">${d.history_runs}</span><span class="stat-label">History Runs</span></div>
    <div class="stat-card"><span class="stat-val">${d.history_records}</span><span class="stat-label">History Records</span></div>
    <div class="stat-card"><span class="stat-val">${d.active_users}/${d.total_users}</span><span class="stat-label">Active Users</span></div>
    <div class="stat-card"><span class="stat-val">${d.total_logins}</span><span class="stat-label">Total Logins</span></div>`;
  const tbody = document.querySelector("#recentActivityTable tbody");
  tbody.innerHTML = (d.recent_activity || []).map((r) => `
    <tr><td>${formatTime(r.created_at)}</td><td>${r.username}</td><td><span class="tag tag-active">${r.action}</span></td><td>${r.details || "—"}</td></tr>
  `).join("") || "<tr><td colspan='4'>No activity yet</td></tr>";
  } catch (err) {
    document.getElementById("statsGrid").innerHTML = `<p class="hint">${err.message}</p>`;
  }
}

async function loadLogs() {
  try {
    const res = await api("/api/admin/logs");
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to load logs");
    const data = await res.json();
  document.querySelector("#logsTable tbody").innerHTML = (data.logs || []).map((l) => `
    <tr>
      <td>${formatTime(l.created_at)}</td>
      <td><strong>${l.username}</strong></td>
      <td><span class="tag tag-active">${l.action}</span></td>
      <td>${l.details || "—"}</td>
      <td>${l.ip_address || "—"}</td>
    </tr>
  `).join("") || "<tr><td colspan='5'>No logs yet</td></tr>";
  } catch (err) {
    document.querySelector("#logsTable tbody").innerHTML = `<tr><td colspan='5'>${err.message}</td></tr>`;
  }
}

function formatTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function initUsers() {
  document.getElementById("addUserBtn")?.addEventListener("click", () => openUserModal());
  document.getElementById("closeUserModal")?.addEventListener("click", closeUserModal);
  document.getElementById("cancelUser")?.addEventListener("click", closeUserModal);
  document.getElementById("userForm")?.addEventListener("submit", saveUser);
  document.getElementById("editIsAdmin")?.addEventListener("change", (e) => {
    document.getElementById("permFieldset").classList.toggle("hidden", e.target.checked);
  });
}

function initBranding() {
  document.getElementById("brandingForm")?.addEventListener("submit", saveBranding);
}

function renderPermLegend() {
  document.getElementById("permLegend").innerHTML = Object.entries(permissionsCatalog)
    .map(([k, v]) => `<span class="perm-chip" title="${k}">${v}</span>`).join("");
}

async function loadUsers() {
  if (!hasPerm("users_manage")) return;
  const res = await api("/api/admin/users");
  const data = await res.json();
  permissionsCatalog = data.permissions;
  renderPermLegend();
  renderPermCheckboxes();
  document.querySelector("#usersTable tbody").innerHTML = data.users.map((u) => `
    <tr>
      <td><strong>${u.username}</strong></td>
      <td>${u.is_admin ? '<span class="tag tag-admin">Admin</span>' : '<span class="tag">User</span>'}</td>
      <td>${u.is_active ? '<span class="tag tag-active">Active</span>' : '<span class="tag tag-off">Disabled</span>'}</td>
      <td class="perm-cell">${u.is_admin ? "Full access" : (u.permissions || []).map((p) => `<span class="perm-chip-sm">${permissionsCatalog[p] || p}</span>`).join("")}</td>
      <td class="actions-cell">
        <button class="btn btn-sm btn-ghost" data-edit="${u.id}">Edit</button>
        ${u.id !== currentUser.id ? `<button class="btn btn-sm btn-danger" data-del="${u.id}">Delete</button>` : ""}
      </td>
    </tr>`).join("");
  document.querySelectorAll("[data-edit]").forEach((btn) =>
    btn.addEventListener("click", () => openUserModal(data.users.find((u) => u.id === +btn.dataset.edit)))
  );
  document.querySelectorAll("[data-del]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this user?")) return;
      await api(`/api/admin/users/${btn.dataset.del}`, { method: "DELETE" });
      showToast("User deleted");
      loadUsers();
    })
  );
}

function renderPermCheckboxes(selected = []) {
  document.getElementById("permCheckboxes").innerHTML = Object.entries(permissionsCatalog)
    .map(([k, v]) => `<label class="checkbox-label"><input type="checkbox" name="perm" value="${k}" ${selected.includes(k) ? "checked" : ""} /> ${v}</label>`).join("");
}

function openUserModal(user = null) {
  document.getElementById("userModalTitle").textContent = user ? "Edit User" : "Add User";
  document.getElementById("editUserId").value = user?.id || "";
  document.getElementById("editUsername").value = user?.username || "";
  document.getElementById("editUsername").disabled = !!user;
  document.getElementById("editPassword").value = "";
  document.getElementById("editPassword").required = !user;
  document.getElementById("pwdHint").textContent = user ? "(leave blank to keep)" : "(required)";
  document.getElementById("editIsAdmin").checked = user?.is_admin || false;
  document.getElementById("editIsActive").checked = user?.is_active ?? true;
  document.getElementById("permFieldset").classList.toggle("hidden", user?.is_admin || false);
  renderPermCheckboxes(user?.permissions || []);
  document.getElementById("userModal").classList.remove("hidden");
}

function closeUserModal() { document.getElementById("userModal").classList.add("hidden"); }

async function saveUser(e) {
  e.preventDefault();
  const id = document.getElementById("editUserId").value;
  const perms = [...document.querySelectorAll('#permCheckboxes input[name="perm"]:checked')].map((c) => c.value);
  const body = {
    username: document.getElementById("editUsername").value.trim(),
    password: document.getElementById("editPassword").value || undefined,
    is_admin: document.getElementById("editIsAdmin").checked,
    is_active: document.getElementById("editIsActive").checked,
    permissions: perms,
  };
  const res = id
    ? await api(`/api/admin/users/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    : await api("/api/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) { showToast((await res.json()).detail || "Failed", "error"); return; }
  showToast("User saved");
  closeUserModal();
  loadUsers();
}

function loadBrandingForm() {
  api("/api/auth/me").then(async (res) => {
    const b = (await res.json()).branding;
    document.getElementById("brandAppTitle").value = b.app_title || "";
    document.getElementById("brandTagline").value = b.app_tagline || "";
    document.getElementById("brandAccent").value = b.accent_color || "#1e8449";
    document.getElementById("brandFooter").value = b.footer_text || "";
    applyBranding(b);
  });
}

async function saveBranding(e) {
  e.preventDefault();
  await api("/api/admin/branding", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      app_title: document.getElementById("brandAppTitle").value,
      app_tagline: document.getElementById("brandTagline").value,
      accent_color: document.getElementById("brandAccent").value,
      footer_text: document.getElementById("brandFooter").value,
    }),
  });
  const logoFile = document.getElementById("logoFile").files[0];
  if (logoFile) {
    const fd = new FormData();
    fd.append("logo", logoFile);
    await api("/api/admin/branding/logo", { method: "POST", body: fd });
  }
  showToast("Branding saved");
  applyBranding((await (await api("/api/auth/me")).json()).branding);
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
  const match = (response.headers.get("Content-Disposition") || "").match(/filename="(.+)"/);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match ? match[1] : fallbackName;
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById("runBtn").addEventListener("click", async () => {
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
  panel.classList.remove("hidden");
  document.getElementById("progressText").textContent = "Running engine...";
  fill.style.width = "30%";
  document.getElementById("runBtn").disabled = true;
  try {
    const res = await api("/api/process", { method: "POST", body: form });
    fill.style.width = "90%";
    if (!res.ok) throw new Error((await res.json()).detail || "Failed");
    await downloadBlob(res, "Lotus_Inventory_Decision.xlsx");
    fill.style.width = "100%";
    showToast("Done! File downloaded.");
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    setTimeout(() => panel.classList.add("hidden"), 1500);
    fill.style.width = "0%";
    updateRunButton();
  }
});

initSession();
