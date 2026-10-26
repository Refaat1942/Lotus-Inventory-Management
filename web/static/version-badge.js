// Shows the running program version: under the login form on the login page,
// and as a badge in the top-right corner of every other page.
(async function showVersion() {
  let data;
  try {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (!res.ok) return;
    data = await res.json();
  } catch {
    return;
  }
  const clean = (v) => String(v || "").replace(/\s*\(Web\)\s*$/i, "").trim();
  const parts = [];
  if (data.purchase) parts.push(`Purchase ${clean(data.purchase)}`);
  if (data.replenishment) parts.push(`Replenishment ${clean(data.replenishment)}`);
  if (!parts.length) return;

  const el = document.createElement("div");
  el.id = "appVersion";
  el.textContent = parts.join(" · ");
  el.title = "Program version";

  const loginCard = document.querySelector(".login-card");
  if (loginCard) {
    el.className = "app-version app-version-login";
    loginCard.appendChild(el);
  } else {
    el.className = "app-version app-version-corner";
    document.body.appendChild(el);
  }
})();
