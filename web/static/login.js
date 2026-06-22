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
  }
}

async function loadBranding() {
  try {
    const res = await fetch("/api/branding");
    if (!res.ok) return;
    const b = await res.json();
    if (b.app_title) document.getElementById("loginTitle").textContent = b.app_title;
    if (b.app_tagline) document.getElementById("loginTagline").textContent = b.app_tagline;
    if (b.footer_text) document.getElementById("loginFooter").textContent = b.footer_text;
    if (b.accent_color) {
      document.documentElement.style.setProperty("--accent", b.accent_color);
      document.documentElement.style.setProperty("--accent-hover", b.accent_color);
    }
    setLogoImage(
      document.getElementById("loginLogoImg"),
      document.getElementById("loginLogoText"),
      document.getElementById("loginLogo"),
      b.logo_url
    );
  } catch (_) {}
}

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("loginBtn");
  const errEl = document.getElementById("loginError");
  errEl.classList.add("hidden");
  btn.disabled = true;

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
    window.location.href = "/";
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
    btn.disabled = false;
  }
});

loadBranding();
