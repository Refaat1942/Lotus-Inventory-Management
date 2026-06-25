/** Shared logo/branding helpers for all Lotus web pages. */
function setLogoImage(imgEl, textEl, containerEl, url) {
  if (!imgEl || !textEl) return;
  if (url) {
    imgEl.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
    imgEl.classList.remove("hidden");
    textEl.classList.add("hidden");
    containerEl?.classList.add("has-image");
    imgEl.onerror = () => {
      if (url.startsWith("/branding/")) {
        setLogoImage(imgEl, textEl, containerEl, "/api/branding/logo");
        return;
      }
      imgEl.classList.add("hidden");
      imgEl.removeAttribute("src");
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

function applyAccentColor(color) {
  if (!color) return;
  document.documentElement.style.setProperty("--accent", color);
  document.documentElement.style.setProperty("--accent-hover", color);
}
