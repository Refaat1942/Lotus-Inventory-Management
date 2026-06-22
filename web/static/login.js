async function loadBranding() {
  try {
    const res = await fetch("/api/branding");
    if (!res.ok) return;
    const b = await res.json();
    if (b.app_title) document.getElementById("loginTitle").textContent = b.app_title;
    if (b.app_tagline) document.getElementById("loginTagline").textContent = b.app_tagline;
    if (b.footer_text) document.getElementById("loginFooter").textContent = b.footer_text;
    if (b.accent_color) document.documentElement.style.setProperty("--accent", b.accent_color);
    if (b.logo_url) {
      const logo = document.getElementById("loginLogo");
      logo.innerHTML = `<img src="${b.logo_url}?t=${Date.now()}" alt="Logo" />`;
      logo.classList.add("has-image");
    }
  } catch (_) {}
}

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("loginBtn");
  const errEl = document.getElementById("loginError");
  errEl.classList.add("hidden");
  btn.disabled = true;
  btn.classList.add("loading");

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Login failed");
    }
    document.body.classList.add("login-success");
    setTimeout(() => { window.location.href = "/"; }, 400);
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.classList.remove("loading");
  }
});

loadBranding();
