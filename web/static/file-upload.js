/** Use original File objects — cloning large sheets into memory causes hangs and OOM. */
async function prepareUploadFile(file) {
  if (!file) return null;
  return file;
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** fetch with timeout — works in browsers without AbortSignal.timeout */
function fetchWithTimeout(url, options = {}, timeoutMs = 600000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const { signal: _ignored, ...rest } = options;
  return fetch(url, { ...rest, signal: controller.signal }).finally(() => clearTimeout(timer));
}

function setDropLoading(drop, loading, message) {
  if (!drop) return;
  drop.classList.toggle("loading", loading);
  const filenameEl = drop.querySelector(".filename");
  if (filenameEl && message) filenameEl.textContent = message;
}
