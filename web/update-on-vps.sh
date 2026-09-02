#!/bin/bash
# One-command update on VPS (no git credentials needed).
# Usage: bash update-on-vps.sh

set -e
APP_DIR="/opt/lotus-inventory"
TMP="/tmp/lotus-update-$$"
ZIP_URL="https://github.com/Refaat1942/Lotus-Inventory-Management/archive/refs/heads/main.zip"

echo "==> Downloading latest code..."
mkdir -p "$TMP"
curl -fsSL -o "$TMP/main.zip" "$ZIP_URL"
unzip -q "$TMP/main.zip" -d "$TMP"

echo "==> Copying to $APP_DIR..."
cp -r "$TMP"/Lotus-Inventory-Management-main/web/* "$APP_DIR/"

echo "==> Installing dependencies..."
source "$APP_DIR/venv/bin/activate"
pip install -r "$APP_DIR/requirements.txt" -q

echo "==> Restarting lotus-inventory..."
systemctl restart lotus-inventory
sleep 1
systemctl is-active lotus-inventory

echo "==> Deployed versions (from files):"
grep 'APP_VERSION' "$APP_DIR/engine.py" | head -1
grep 'APP_VERSION' "$APP_DIR/replenishment_engine.py" | head -1

rm -rf "$TMP"
echo ""
echo "==> Live API version:"
curl -sf http://127.0.0.1:10000/api/version || echo "(API not responding yet)"
echo ""
echo "Purchase should be v9.8.6 (Web) — blocked+Display, editable username, case-insensitive login."
echo "Open: http://187.124.15.14:10000/purchase — then Ctrl+F5 before testing."
