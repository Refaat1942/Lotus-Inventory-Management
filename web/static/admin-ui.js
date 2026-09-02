/** Central admin panel — used only on /settings (admin-only page). */
const AdminPanel = {
  deps: null,
  permissionsCatalog: {},

  MODULE_GROUPS: {
    purchase: {
      title: "Purchase Module",
      access: "purchase",
      features: ["templates", "engine_run", "history"],
    },
    replenishment: {
      title: "Replenishment Module",
      access: "replenishment",
      features: ["replenishment_templates", "replenishment_run", "replenishment_history"],
    },
  },

  init(deps) {
    this.deps = deps;
    document.getElementById("addUserBtn")?.addEventListener("click", () => this.openUserModal());
    document.getElementById("closeUserModal")?.addEventListener("click", () => this.closeUserModal());
    document.getElementById("cancelUser")?.addEventListener("click", () => this.closeUserModal());
    document.getElementById("userForm")?.addEventListener("submit", (e) => this.saveUser(e));
    document.getElementById("editIsAdmin")?.addEventListener("change", (e) => {
      document.getElementById("permFieldset")?.classList.toggle("hidden", e.target.checked);
    });
    document.getElementById("brandingForm")?.addEventListener("submit", (e) => this.saveBranding(e));
    this.buildPermTabPanels();
    document.querySelectorAll("#permModuleTabs .module-tab").forEach((tab) => {
      tab.addEventListener("click", () => this.switchPermTab(tab.dataset.tab));
    });
  },

  buildPermTabPanels() {
    const container = document.getElementById("permTabPanels");
    if (!container) return;
    container.innerHTML = Object.entries(this.MODULE_GROUPS)
      .map(
        ([key, group], i) => `
      <div class="perm-tab-panel ${i === 0 ? "active" : "hidden"}" id="permPanel-${key}" data-panel="${key}">
        <label class="checkbox-label module-access-label">
          <input type="checkbox" name="perm" value="${group.access}" data-module-access="${key}" />
          <strong>Allow access to ${group.title}</strong>
        </label>
        <div class="perm-features" id="permFeatures-${key}"></div>
      </div>`
      )
      .join("");

    Object.entries(this.MODULE_GROUPS).forEach(([key, group]) => {
      const featEl = document.getElementById(`permFeatures-${key}`);
      featEl.innerHTML = group.features
        .map(
          (f) =>
            `<label class="checkbox-label"><input type="checkbox" name="perm" value="${f}" data-module-feature="${key}" /> <span class="perm-label-${f}">${f}</span></label>`
        )
        .join("");

      document.querySelector(`input[data-module-access="${key}"]`)?.addEventListener("change", (e) => {
        featEl.querySelectorAll(`input[data-module-feature="${key}"]`).forEach((inp) => {
          inp.disabled = !e.target.checked;
          if (!e.target.checked) inp.checked = false;
        });
      });
    });
  },

  switchPermTab(tabKey) {
    document.querySelectorAll("#permModuleTabs .module-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tabKey);
    });
    document.querySelectorAll(".perm-tab-panel").forEach((p) => {
      p.classList.toggle("hidden", p.dataset.panel !== tabKey);
      p.classList.toggle("active", p.dataset.panel === tabKey);
    });
  },

  formatTime(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  },

  moduleSummary(perms, moduleKey) {
    const group = this.MODULE_GROUPS[moduleKey];
    if (!perms.includes(group.access)) return '<span class="tag tag-off">No access</span>';
    const feats = group.features.filter((f) => perms.includes(f));
    if (feats.length === group.features.length) return '<span class="tag tag-active">Full</span>';
    if (feats.length === 0) return '<span class="tag">Access only</span>';
    return `<span class="tag tag-active">${feats.length}/${group.features.length} features</span>`;
  },

  renderPermCheckboxes(selected = []) {
    Object.entries(this.MODULE_GROUPS).forEach(([key, group]) => {
      const accessInput = document.querySelector(`input[data-module-access="${key}"]`);
      const accessChecked = selected.includes(group.access);
      if (accessInput) accessInput.checked = accessChecked;
      group.features.forEach((f) => {
        const inp = document.querySelector(`input[data-module-feature="${key}"][value="${f}"]`);
        const label = document.querySelector(`.perm-label-${f}`);
        if (label) label.textContent = this.permissionsCatalog[f] || f;
        if (inp) {
          inp.checked = selected.includes(f);
          inp.disabled = !accessChecked;
        }
      });
    });
  },

  async loadReports() {
    try {
      const res = await this.deps.api("/api/admin/reports");
      if (!res.ok) throw new Error((await res.json()).detail || "Failed to load reports");
      const d = await res.json();
      document.getElementById("statsGrid").innerHTML = `
        <div class="stat-card"><span class="stat-val">${d.total_engine_runs}</span><span class="stat-label">Engine Runs</span></div>
        <div class="stat-card"><span class="stat-val">${d.history_runs}</span><span class="stat-label">History Runs</span></div>
        <div class="stat-card"><span class="stat-val">${d.history_records}</span><span class="stat-label">History Records</span></div>
        <div class="stat-card"><span class="stat-val">${d.active_users}/${d.total_users}</span><span class="stat-label">Active Users</span></div>
        <div class="stat-card"><span class="stat-val">${d.total_logins}</span><span class="stat-label">Total Logins</span></div>`;
      document.querySelector("#recentActivityTable tbody").innerHTML =
        (d.recent_activity || [])
          .map(
            (r) =>
              `<tr><td>${this.formatTime(r.created_at)}</td><td>${r.username}</td><td><span class="tag tag-active">${r.action}</span></td><td>${r.details || "—"}</td></tr>`
          )
          .join("") || "<tr><td colspan='4'>No activity yet</td></tr>";
    } catch (err) {
      document.getElementById("statsGrid").innerHTML = `<p class="hint">${err.message}</p>`;
    }
  },

  async loadLogs() {
    try {
      const res = await this.deps.api("/api/admin/logs");
      if (!res.ok) throw new Error((await res.json()).detail || "Failed to load logs");
      const data = await res.json();
      document.querySelector("#logsTable tbody").innerHTML =
        (data.logs || [])
          .map(
            (l) =>
              `<tr>
        <td>${this.formatTime(l.created_at)}</td>
        <td><strong>${l.username}</strong></td>
        <td><span class="tag tag-active">${l.action}</span></td>
        <td>${l.details || "—"}</td>
        <td>${l.ip_address || "—"}</td>
      </tr>`
          )
          .join("") || "<tr><td colspan='5'>No logs yet</td></tr>";
    } catch (err) {
      document.querySelector("#logsTable tbody").innerHTML = `<tr><td colspan='5'>${err.message}</td></tr>`;
    }
  },

  async loadUsers() {
    const res = await this.deps.api("/api/admin/users");
    const data = await res.json();
    this.permissionsCatalog = data.permissions;
    const me = this.deps.getUser();
    document.querySelector("#usersTable tbody").innerHTML = data.users
      .map((u) => {
        const perms = u.permissions || [];
        return `
    <tr>
      <td><strong>${u.username}</strong></td>
      <td>${u.is_admin ? '<span class="tag tag-admin">Admin</span>' : '<span class="tag">User</span>'}</td>
      <td>${u.is_active ? '<span class="tag tag-active">Active</span>' : '<span class="tag tag-off">Blocked</span>'}</td>
      <td>${u.is_admin ? '<span class="tag tag-admin">Full</span>' : this.moduleSummary(perms, "purchase")}</td>
      <td>${u.is_admin ? '<span class="tag tag-admin">Full</span>' : this.moduleSummary(perms, "replenishment")}</td>
      <td class="actions-cell">
        <button class="btn btn-sm btn-ghost" data-edit="${u.id}">Edit</button>
        ${
          u.id !== me.id
            ? `<button class="btn btn-sm ${u.is_active ? "btn-warning" : "btn-success"}" data-toggle="${u.id}" data-active="${u.is_active}">${u.is_active ? "Block" : "Activate"}</button>
        <button class="btn btn-sm btn-danger" data-del="${u.id}">Delete</button>`
            : ""
        }
      </td>
    </tr>`;
      })
      .join("");

    document.querySelectorAll("[data-edit]").forEach((btn) =>
      btn.addEventListener("click", () => this.openUserModal(data.users.find((u) => u.id === +btn.dataset.edit)))
    );
    document.querySelectorAll("[data-toggle]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const u = data.users.find((x) => x.id === +btn.dataset.toggle);
        const active = btn.dataset.active === "true";
        await this.deps.api(`/api/admin/users/${u.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_active: !active }),
        });
        this.deps.showToast(active ? "User blocked" : "User activated");
        this.loadUsers();
      })
    );
    document.querySelectorAll("[data-del]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this user permanently?")) return;
        await this.deps.api(`/api/admin/users/${btn.dataset.del}`, { method: "DELETE" });
        this.deps.showToast("User deleted");
        this.loadUsers();
      })
    );
  },

  openUserModal(user = null) {
    document.getElementById("userModalTitle").textContent = user ? "Edit User" : "Add User";
    document.getElementById("editUserId").value = user?.id || "";
    document.getElementById("editUsername").value = user?.username || "";
    document.getElementById("editUsername").disabled = false;
    document.getElementById("editPassword").value = "";
    document.getElementById("editPassword").required = !user;
    document.getElementById("pwdHint").textContent = user ? "(leave blank to keep)" : "(required)";
    document.getElementById("editIsAdmin").checked = user?.is_admin || false;
    document.getElementById("editIsActive").checked = user?.is_active ?? true;
    document.getElementById("permFieldset").classList.toggle("hidden", user?.is_admin || false);
    this.switchPermTab("purchase");
    this.renderPermCheckboxes(user?.permissions || []);
    document.getElementById("userModal").classList.remove("hidden");
  },

  closeUserModal() {
    document.getElementById("userModal").classList.add("hidden");
  },

  async saveUser(e) {
    e.preventDefault();
    const id = document.getElementById("editUserId").value;
    const perms = [...document.querySelectorAll('#permFieldset input[name="perm"]:checked')].map((c) => c.value);
    const body = {
      username: document.getElementById("editUsername").value.trim(),
      password: document.getElementById("editPassword").value || undefined,
      is_admin: document.getElementById("editIsAdmin").checked,
      is_active: document.getElementById("editIsActive").checked,
      permissions: perms,
    };
    if (id) {
      const res = await this.deps.api(`/api/admin/users/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        this.deps.showToast((await res.json()).detail || "Failed", "error");
        return;
      }
      this.deps.showToast("User saved");
      this.closeUserModal();
      this.loadUsers();
      return;
    }
    const res = await this.deps.api("/api/admin/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
    if (!res.ok) {
      this.deps.showToast((await res.json()).detail || "Failed", "error");
      return;
    }
    this.deps.showToast("User saved");
    this.closeUserModal();
    this.loadUsers();
  },

  loadBrandingForm() {
    this.deps.api("/api/auth/me").then(async (res) => {
      const b = (await res.json()).branding;
      document.getElementById("brandAppTitle").value = b.app_title || "";
      document.getElementById("brandTagline").value = b.app_tagline || "";
      document.getElementById("brandAccent").value = b.accent_color || "#1e8449";
      document.getElementById("brandFooter").value = b.footer_text || "";
      this.deps.applyBranding(b);
    });
  },

  async saveBranding(e) {
    e.preventDefault();
    await this.deps.api("/api/admin/branding", {
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
      await this.deps.api("/api/admin/branding/logo", { method: "POST", body: fd });
    }
    this.deps.showToast("Branding saved");
    this.deps.applyBranding((await (await this.deps.api("/api/auth/me")).json()).branding);
  },

  onNavigate(view) {
    if (view === "reports") this.loadReports();
    if (view === "logs") this.loadLogs();
    if (view === "users") this.loadUsers();
    if (view === "branding") this.loadBrandingForm();
  },
};
