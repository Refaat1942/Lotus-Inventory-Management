#!/bin/bash
# Quick redeploy after code changes — run on VPS
# Usage: bash /opt/lotus-inventory/redeploy.sh

set -e
APP_DIR="/opt/lotus-inventory"
REPO_DIR="/tmp/lotus-inventory-repo"
REPO_URL="${LOTUS_REPO_URL:-https://github.com/Refaat1942/Lotus-Inventory-Management.git}"

cd "$APP_DIR"

echo "==> Pulling latest code..."
if [ -d "$APP_DIR/.git" ]; then
  git pull origin main
else
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
  cp -r "$REPO_DIR/web/"* "$APP_DIR/"
  rm -rf "$REPO_DIR"
fi

echo "==> Updating dependencies..."
source "$APP_DIR/venv/bin/activate"
pip install -r requirements.txt -q

echo "==> Restarting service..."
systemctl restart lotus-inventory
systemctl status lotus-inventory --no-pager

echo ""
echo "==> Redeploy complete — http://187.124.15.14:10000"
