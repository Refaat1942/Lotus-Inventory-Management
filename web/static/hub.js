const MODULES = [
  {
    id: "purchase",
    perm: "purchase",
    title: "Purchase",
    desc: "Smart inventory engine — upload ERP data, run purchase decisions, and export results.",
    icon: "🛒",
    href: "/purchase",
    accent: "#1e8449",
  },
  {
    id: "replenishment",
    perm: "replenishment",
    title: "Replenishment",
    desc: "Branch replenishment engine — configure targets, allocate DC stock, and export requirements.",
    icon: "📦",
    href: "/replenishment",
    accent: "#2980b9",
  },
];

const SETTINGS_MODULE = {
  id: "settings",
  title: "Settings",
  desc: "Admin only — manage users, module permissions, branding, reports, and activity logs.",
  icon: "⚙️",
  href: "/settings",
  accent: "#6c5ce7",
};

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "include", ...options });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}

function applyBranding(b) {
  if (!b) return;
  if (b.app_title) document.getElementById("hubTitle").textContent = b.app_title;
  if (b.app_tagline) document.getElementById("hubTagline").textContent = "Select a module to continue";
  if (b.footer_text) document.getElementById("hubFooter").textContent = b.footer_text;
  applyAccentColor(b.accent_color);
  setLogoImage(
    document.getElementById("hubLogoImg"),
    document.getElementById("hubLogoText"),
    document.getElementById("hubLogo"),
    b.logo_url
  );
}

function hasPerm(user, key) {
  return user?.permissions?.includes(key);
}

function renderModules(user) {
  const grid = document.getElementById("moduleGrid");
  const empty = document.getElementById("hubEmpty");
  const available = MODULES.filter((m) => hasPerm(user, m.perm));
  const cards = [...available];
  if (user.is_admin) cards.push(SETTINGS_MODULE);

  if (cards.length === 0) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");

  if (cards.length === 1 && !user.is_admin) {
    window.location.href = cards[0].href;
    return;
  }

  grid.innerHTML = cards
    .map(
      (m) => `
    <a class="module-card" href="${m.href}" style="--module-accent:${m.accent}">
      <span class="module-icon">${m.icon}</span>
      <h2>${m.title}</h2>
      <p>${m.desc}</p>
      <span class="module-cta">Open ${m.title} →</span>
    </a>`
    )
    .join("");
}

async function init() {
  const res = await api("/api/auth/me");
  const data = await res.json();
  const user = data.user;
  document.getElementById("hubUserBadge").textContent = user.username + (user.is_admin ? " (Admin)" : "");
  applyBranding(data.branding);
  renderModules(user);
}

document.getElementById("hubLogoutBtn").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/login";
});

init().catch(() => {
  window.location.href = "/login";
});
