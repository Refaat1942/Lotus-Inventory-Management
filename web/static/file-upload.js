/** Clone a File into memory so it can be sent to multiple API calls reliably. */
async function cloneUploadFile(file) {
  if (!file) return null;
  const buf = await file.arrayBuffer();
  return new File([buf], file.name, {
    type: file.type || "application/octet-stream",
    lastModified: file.lastModified ?? Date.now(),
  });
}
