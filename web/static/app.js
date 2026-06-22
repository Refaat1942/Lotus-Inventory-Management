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

let currentUser = null;
let permissionsCatalog = {};
const files = {};

const templateGrid = document.getElementById("templateGrid");
const uploadGrid = document.getElementById("uploadGrid");
const runBtn = document.getElementById("runBtn");
const clearBtn = document.getElementById("clearBtn");
const historyBtn = document.getElementById("historyBtn");
const stoThreshold = document.getElementById("stoThreshold");
const customSto = document.getElementById("customSto");
const zeroOverstock = document.getElementById("zeroOverstock");
const progressPanel = document.getElementById("progressPanel");
const progressText = document.getElementById("progressText");
const progressFill = document.getElementById("progressFill");
const toast = document.getElementById("toast");
const adminBtn = document.getElementById("adminBtn");
const userBadge = document.getElementById("userBadge");

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
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove("show"), 4500);
}

function applyBranding(b) {
  if (!b) return;
  if (b.app_title) document.getElementById("brandTitle").textContent = b.app_title;
  if (b.app_tagline) document.getElementById("brandTagline").textContent = b.app_tagline;
  if (b.footer_text) document.getElementById("appFooter").textContent = b.footer_text;
  if (b.accent_color) {
    document.documentElement.style.setProperty("--accent", b.accent_color);
    document.documentElement.style.setProperty("--accent-hover", b.accent_color);
  }
  document.title = b.app_title || "Lotus Inventory Management";
  const logoEl = document.getElementById("brandLogo");
  if (b.logo_url) {
    logoEl.innerHTML = `<img src="${b.logo_url}?t=${Date.now()}" alt="Logo" />`;
    logoEl.classList.add("has-image");
  } else {
    logoEl.textContent = "LOTUS";
    logoEl.classList.remove("has-image");
  }
}

function applyPermissions() {
  document.getElementById("templatesSection").classList.toggle("hidden", !hasPerm("templates"));
  document.getElementById("uploadSection").classList.toggle("hidden", !hasPerm("engine_run"));
  document.getElementById("configSection").classList.toggle("hidden", !hasPerm("engine_run"));
  document.getElementById("actionsSection").classList.toggle("hidden", !hasPerm("engine_run") && !hasPerm("history"));
  runBtn.classList.toggle("hidden", !hasPerm("engine_run"));
  clearBtn.classList.toggle("hidden", !hasPerm("engine_run"));
  historyBtn.classList.toggle("hidden", !hasPerm("history"));

  const canAdmin = hasPerm("users_manage") || hasPerm("branding");
  adminBtn.classList.toggle("hidden", !canAdmin);
}

function updateRunButton() {
  if (!hasPerm("engine_run")) return;
  const required = UPLOADS.filter((u) => u.required).map((u) => u.id);
  runBtn.disabled = !required.every((id) => files[id]);
}

function buildTemplates() {
  templateGrid.innerHTML = "";
  TEMPLATES.forEach(({ id, label }, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-template animate-in";
    btn.style.animationDelay = `${i * 0.05}s`;
    btn.textContent = label;
    btn.addEventListener("click", async () => {
      window.location.href = `/api/templates/${id}`;
    });
    templateGrid.appendChild(btn);
  });
}

function setupUpload({ id, label, required }, index) {
  const item = document.createElement("div");
  item.className = "upload-item animate-in";
  item.style.animationDelay = `${index * 0.04}s`;
  item.innerHTML = `
    <label>${label}${required ? ' <span class="req">*</span>' : ""}</label>
    <div class="file-drop" data-id="${id}">
      <span class="drop-icon">📄</span>
      <span>Drop file or click</span>
      <span class="filename">No file selected</span>
      <input type="file" accept=".xlsx,.xls" />
    </div>
  `;
  uploadGrid.appendChild(item);

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
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    setFile(e.dataTransfer.files[0]);
  });
}

async function initSession() {
  const res = await api("/api/auth/me");
  if (!res.ok) { window.location.href = "/login"; return; }
  const data = await res.json();
  currentUser = data.user;
  permissionsCatalog = data.permissions_catalog || {};
  userBadge.textContent = currentUser.is_admin ? `${currentUser.username} (Admin)` : currentUser.username;
  applyBranding(data.branding);
  applyPermissions();
  if (hasPerm("templates")) buildTemplates();
  if (hasPerm("engine_run")) UPLOADS.forEach(setupUpload);
  if (hasPerm("users_manage") || hasPerm("branding")) initAdmin();
}

// --- Admin Panel ---
function initAdmin() {
  document.querySelectorAll(".modal-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".modal-tabs .tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });

  adminBtn.addEventListener("click", () => {
    document.getElementById("adminModal").classList.remove("hidden");
    if (hasPerm("users_manage")) loadUsers();
    if (hasPerm("branding")) loadBrandingForm();
  });

  document.getElementById("closeAdmin").addEventListener("click", () =>
    document.getElementById("adminModal").classList.add("hidden")
  );

  if (hasPerm("users_manage")) {
    document.getElementById("addUserBtn").addEventListener("click", () => openUserModal());
    document.getElementById("closeUserModal").addEventListener("click", closeUserModal);
    document.getElementById("cancelUser").addEventListener("click", closeUserModal);
    document.getElementById("userForm").addEventListener("submit", saveUser);
    document.getElementById("editIsAdmin").addEventListener("change", (e) => {
      document.getElementById("permFieldset").classList.toggle("hidden", e.target.checked);
    });
  } else {
    document.querySelector('[data-tab="users"]').classList.add("hidden");
    document.getElementById("tab-users").classList.add("hidden");
    document.querySelector('[data-tab="branding"]').click();
  }

  if (hasPerm("branding")) {
    document.getElementById("brandingForm").addEventListener("submit", saveBranding);
  } else {
    document.querySelector('[data-tab="branding"]').classList.add("hidden");
  }
}

function renderPermLegend() {
  const el = document.getElementById("permLegend");
  el.innerHTML = Object.entries(permissionsCatalog).map(([k, v]) =>
    `<span class="perm-chip" title="${k}">${v}</span>`
  ).join("");
}

async function loadUsers() {
  const res = await api("/api/admin/users");
  const data = await res.json();
  permissionsCatalog = data.permissions;
  renderPermLegend();
  renderPermCheckboxes();

  const tbody = document.querySelector("#usersTable tbody");
  tbody.innerHTML = data.users.map((u) => `
    <tr>
      <td><strong>${u.username}</strong></td>
      <td>${u.is_admin ? '<span class="tag tag-admin">Admin</span>' : '<span class="tag">User</span>'}</td>
      <td>${u.is_active ? '<span class="tag tag-active">Active</span>' : '<span class="tag tag-off">Disabled</span>'}</td>
      <td class="perm-cell">${u.is_admin ? "All permissions" : (u.permissions || []).map(p => `<span class="perm-chip-sm">${permissionsCatalog[p] || p}</span>`).join("")}</td>
      <td class="actions-cell">
        <button class="btn btn-sm btn-ghost" data-edit="${u.id}">Edit</button>
        ${u.id !== currentUser.id ? `<button class="btn btn-sm btn-danger" data-del="${u.id}">Delete</button>` : ""}
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll("[data-edit]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const user = data.users.find((u) => u.id === +btn.dataset.edit);
      openUserModal(user);
    })
  );
  tbody.querySelectorAll("[data-del]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this user?")) return;
      await api(`/api/admin/users/${btn.dataset.del}`, { method: "DELETE" });
      showToast("User deleted");
      loadUsers();
    })
  );
}

function renderPermCheckboxes(selected = []) {
  const el = document.getElementById("permCheckboxes");
  el.innerHTML = Object.entries(permissionsCatalog)
    .filter(([k]) => k !== "users_manage" || hasPerm("users_manage"))
    .map(([k, v]) => `
      <label class="checkbox-label">
        <input type="checkbox" name="perm" value="${k}" ${selected.includes(k) ? "checked" : ""} />
        ${v}
      </label>
    `).join("");
}

function openUserModal(user = null) {
  document.getElementById("userModalTitle").textContent = user ? "Edit User" : "Add User";
  document.getElementById("editUserId").value = user?.id || "";
  document.getElementById("editUsername").value = user?.username || "";
  document.getElementById("editUsername").disabled = !!user;
  document.getElementById("editPassword").value = "";
  document.getElementById("editPassword").required = !user;
  document.getElementById("pwdHint").textContent = user ? "(leave blank to keep current)" : "(required for new users)";
  document.getElementById("editIsAdmin").checked = user?.is_admin || false;
  document.getElementById("editIsActive").checked = user?.is_active ?? true;
  document.getElementById("permFieldset").classList.toggle("hidden", user?.is_admin || false);
  renderPermCheckboxes(user?.permissions || []);
  document.getElementById("userModal").classList.remove("hidden");
}

function closeUserModal() {
  document.getElementById("userModal").classList.add("hidden");
}

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

  if (!res.ok) {
    const err = await res.json();
    showToast(err.detail || "Failed to save user", "error");
    return;
  }
  showToast("User saved");
  closeUserModal();
  loadUsers();
}

function loadBrandingForm() {
  api("/api/auth/me").then(async (res) => {
    const data = await res.json();
    const b = data.branding;
    document.getElementById("brandAppTitle").value = b.app_title || "";
    document.getElementById("brandTagline").value = b.app_tagline || "";
    document.getElementById("brandAccent").value = b.accent_color || "#1e8449";
    document.getElementById("brandFooter").value = b.footer_text || "";
    const preview = document.getElementById("logoPreview");
    if (b.logo_url) {
      preview.src = b.logo_url + "?t=" + Date.now();
      preview.classList.remove("hidden");
    } else {
      preview.classList.add("hidden");
    }
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
  const me = await (await api("/api/auth/me")).json();
  applyBranding(me.branding);
  if (me.branding?.logo_url) {
    document.getElementById("logoPreview").src = me.branding.logo_url + "?t=" + Date.now();
    document.getElementById("logoPreview").classList.remove("hidden");
  }
}

// --- Main actions ---
stoThreshold.addEventListener("change", () => {
  customSto.classList.toggle("hidden", stoThreshold.value !== "custom");
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

clearBtn.addEventListener("click", () => {
  UPLOADS.forEach(({ id }) => delete files[id]);
  document.querySelectorAll(".file-drop").forEach((drop) => {
    drop.classList.remove("loaded");
    drop.querySelector(".filename").textContent = "No file selected";
    drop.querySelector("input").value = "";
  });
  updateRunButton();
  showToast("All uploaded sheets cleared.");
});

historyBtn.addEventListener("click", async () => {
  try {
    const res = await api("/api/history");
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "No history found"); }
    await downloadBlob(res, "Lotus_Inventory_History.xlsx");
    showToast("History exported successfully.");
  } catch (err) { showToast(err.message, "error"); }
});

async function downloadBlob(response, fallbackName) {
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="(.+)"/);
  const filename = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

runBtn.addEventListener("click", async () => {
  const form = new FormData();
  UPLOADS.forEach(({ id }) => { if (files[id]) form.append(id, files[id]); });
  form.append("zero_overstock", zeroOverstock.checked ? "true" : "false");
  let threshold = stoThreshold.value;
  if (threshold === "custom") {
    threshold = customSto.value;
    if (!threshold) { showToast("Please enter a custom STO threshold.", "error"); return; }
  }
  form.append("sto_threshold", threshold);

  progressPanel.classList.remove("hidden");
  progressText.textContent = "Running Smart Inventory Engine...";
  progressFill.style.width = "30%";
  runBtn.disabled = true;

  try {
    const res = await api("/api/process", { method: "POST", body: form });
    progressFill.style.width = "90%";
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Processing failed"); }
    await downloadBlob(res, "Lotus_Inventory_Decision.xlsx");
    progressFill.style.width = "100%";
    progressText.textContent = "Done! File downloaded.";
    showToast("Engine run successfully. Results downloaded.");
  } catch (err) {
    showToast(err.message, "error");
    progressText.textContent = "Failed.";
  } finally {
    setTimeout(() => progressPanel.classList.add("hidden"), 1500);
    progressFill.style.width = "0%";
    updateRunButton();
  }
});

initSession();
