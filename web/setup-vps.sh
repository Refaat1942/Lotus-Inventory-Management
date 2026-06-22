#!/bin/bash
# Run this ON the VPS after uploading files to /opt/lotus-inventory
set -e

APP_DIR="/opt/lotus-inventory"
PORT=10000

echo "==> Lotus Inventory — VPS Setup"
echo "    Directory: $APP_DIR"
echo "    Port: $PORT"

if [ ! -f "$APP_DIR/requirements.txt" ]; then
  echo "ERROR: $APP_DIR/requirements.txt not found."
  echo "Upload the web folder first. See deploy-from-windows.ps1 on your PC."
  exit 1
fi

cd "$APP_DIR"

# System packages (Ubuntu/Debian)
if ! command -v python3 &>/dev/null; then
  apt-get update
  apt-get install -y python3 python3-pip python3-venv
fi

# Fresh venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data/branding

# Install systemd service
cp lotus-inventory.service /etc/systemd/system/lotus-inventory.service
systemctl daemon-reload
systemctl enable lotus-inventory
systemctl restart lotus-inventory

# Firewall (ignore if ufw not installed)
if command -v ufw &>/dev/null; then
  ufw allow "$PORT/tcp" || true
fi

echo ""
echo "==> Done!"
systemctl status lotus-inventory --no-pager || true
echo ""
echo "Open in browser: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_VPS_IP'):$PORT"
echo "Login: admin / admin"
