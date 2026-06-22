#!/bin/bash
# Deploy Lotus Inventory Web to VPS
# Usage: ./deploy.sh user@187.124.15.14

set -e
VPS="${1:-root@187.124.15.14}"
APP_DIR="/opt/lotus-inventory"
PORT=10000

echo "==> Deploying to $VPS..."

ssh "$VPS" "mkdir -p $APP_DIR"

rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude 'data/' \
  ./ "$VPS:$APP_DIR/"

ssh "$VPS" bash -s <<EOF
set -e
cd $APP_DIR

if ! command -v python3 &>/dev/null; then
  apt-get update && apt-get install -y python3 python3-pip python3-venv
fi

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p data/branding

# Install systemd service
cat > /etc/systemd/system/lotus-inventory.service <<UNIT
[Unit]
Description=Lotus Inventory Management Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=LOTUS_HOST=0.0.0.0
Environment=LOTUS_PORT=$PORT
Environment=LOTUS_SECRET_KEY=change-this-to-a-random-secret-key
Environment=LOTUS_ADMIN_USER=admin
Environment=LOTUS_ADMIN_PASS=admin
ExecStart=$APP_DIR/venv/bin/uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable lotus-inventory
systemctl restart lotus-inventory
systemctl status lotus-inventory --no-pager
EOF

echo ""
echo "Deployed! Access at: http://187.124.15.14:$PORT"
echo "Login: admin / admin"
echo "IMPORTANT: Change LOTUS_SECRET_KEY and admin password after first login."
