# Upload Lotus Inventory web app to VPS from Windows
# Usage: .\deploy-from-windows.ps1
#        .\deploy-from-windows.ps1 -VpsUser root -VpsHost 187.124.15.14

param(
    [string]$VpsUser = "root",
    [string]$VpsHost = "187.124.15.14",
    [string]$RemoteDir = "/opt/lotus-inventory"
)

$ErrorActionPreference = "Stop"
$LocalWeb = $PSScriptRoot

Write-Host "==> Uploading from: $LocalWeb"
Write-Host "==> To: ${VpsUser}@${VpsHost}:${RemoteDir}"

# Create remote directory
ssh "${VpsUser}@${VpsHost}" "mkdir -p $RemoteDir"

# Upload files (exclude cache and local db)
$files = @(
    "app.py", "auth.py", "config.py", "database.py", "engine.py",
    "replenishment_engine.py", "requirements.txt", "lotus-inventory.service",
    "setup-vps.sh", "redeploy.sh", ".env.example"
)
foreach ($f in $files) {
    if (Test-Path (Join-Path $LocalWeb $f)) {
        scp (Join-Path $LocalWeb $f) "${VpsUser}@${VpsHost}:${RemoteDir}/"
    }
}

# Upload static folder
scp -r (Join-Path $LocalWeb "static") "${VpsUser}@${VpsHost}:${RemoteDir}/"

# Upload scripts folder (optional build helpers)
if (Test-Path (Join-Path $LocalWeb "scripts")) {
    scp -r (Join-Path $LocalWeb "scripts") "${VpsUser}@${VpsHost}:${RemoteDir}/"
}

# Run setup on VPS (first install) or quick restart (update)
Write-Host "==> Restarting service on VPS..."
ssh "${VpsUser}@${VpsHost}" @"
if [ -x $RemoteDir/setup-vps.sh ] && [ ! -d $RemoteDir/venv ]; then
  chmod +x $RemoteDir/setup-vps.sh && bash $RemoteDir/setup-vps.sh
else
  source $RemoteDir/venv/bin/activate && pip install -r $RemoteDir/requirements.txt -q
  systemctl restart lotus-inventory
  systemctl status lotus-inventory --no-pager
fi
"@

Write-Host ""
Write-Host "Deployed! Open: http://${VpsHost}:10000"
Write-Host "Login: admin / admin"
