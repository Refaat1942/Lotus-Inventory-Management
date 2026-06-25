const NAV_ITEMS = [
  { view: "users", icon: "👥", label: "Users & Permissions", sub: "Modules & features" },
  { view: "reports", icon: "📊", label: "Reports", sub: "Usage statistics" },
  { view: "logs", icon: "📋", label: "Activity Logs", sub: "Audit trail" },
  { view: "branding", icon: "🎨", label: "Branding", sub: "Logo & colors" },
  { view: "hub", icon: "🏠", label: "Modules", sub: "Back to hub", href: "/hub" },
];

const PAGE_META = {
  users: { title: "Users & Permissions", sub: "Manage users, module access, and platform branding" },
  reports: { title: "Reports", sub: "System usage and run statistics" },
  logs: { title: "Activity Logs", sub: "Track all user actions" },
  branding: { title: "Branding", sub: "Logo, title, and colors for the whole platform" },
};

let currentUser = null;

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "include", ...options });
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
  if (b.footer_text) document.getElementById("appFooter").textContent = b.footer_text;
  applyAccentColor(b.accent_color);
  setLogoImage(
    document.getElementById("brandLogoImg"),
    document.getElementById("brandLogoText"),
    document.getElementById("brandLogo"),
    b.logo_url || null
  );
  setLogoImage(
    document.getElementById("brandingLogoImg"),
    document.getElementById("brandingLogoText"),
    document.getElementById("brandingLogoPreview"),
    b.logo_url || null
  );
}

function buildSidebar() {
  const nav = document.getElementById("sidebarNav");
  nav.innerHTML = "";
  NAV_ITEMS.forEach((item) => {
    const el = document.createElement(item.href ? "a" : "button");
    if (item.href) {
      el.href = item.href;
      el.className = "nav-item";
    } else {
      el.type = "button";
      el.className = "nav-item";
      el.dataset.view = item.view;
      el.addEventListener("click", () => navigateTo(item.view));
    }
    el.innerHTML = `<span class="nav-icon">${item.icon}</span><span class="nav-text"><strong>${item.label}</strong><small>${item.sub}</small></span>`;
    nav.appendChild(el);
  });
}

function navigateTo(view) {
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
    n.classList.toggle("active", n.dataset.view === view);
  });
  const meta = PAGE_META[view] || PAGE_META.users;
  document.getElementById("pageTitle").textContent = meta.title;
  document.getElementById("pageSub").textContent = meta.sub;
  AdminPanel.onNavigate(view);
}

async function initSession() {
  const res = await api("/api/auth/me");
  if (!res.ok) {
    window.location.href = "/login";
    return;
  }
  const data = await res.json();
  currentUser = data.user;
  if (!currentUser.is_admin) {
    window.location.href = "/hub";
    return;
  }
  document.getElementById("userBadge").textContent = `${currentUser.username} · Admin`;
  applyBranding(data.branding);
  AdminPanel.init({
    api,
    showToast,
    applyBranding,
    getUser: () => currentUser,
  });
  buildSidebar();
  navigateTo("users");
}

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

initSession();
