#!/usr/bin/env bash
# Run ON the Nebius VM (Ubuntu) as a sudoer:  bash deploy/setup_vm.sh <git-repo-url>
# Then: edit /opt/baitproof/.env (keys), edit deploy/Caddyfile domain, restart services.
set -euo pipefail
REPO="${1:?usage: setup_vm.sh <git-repo-url>}"
sudo apt-get update -y && sudo apt-get install -y python3-venv git caddy fonts-noto-cjk  # fonts-noto-cjk draws the Chinese text on the share-card image
sudo useradd --system --home /opt/baitproof baitproof 2>/dev/null || true
sudo mkdir -p /opt/baitproof /var/lib/baitproof
sudo chown -R "$USER" /opt/baitproof
git clone "$REPO" /opt/baitproof 2>/dev/null || git -C /opt/baitproof pull
cd /opt/baitproof
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
sudo chown -R baitproof:baitproof /var/lib/baitproof
sudo chown -R baitproof /opt/baitproof && sudo chmod 600 .env
sudo cp deploy/baitproof.service /etc/systemd/system/
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload && sudo systemctl enable --now baitproof && sudo systemctl restart caddy
echo "Up. Check: curl -I http://127.0.0.1:8000/   (open ports 80/443 in the Nebius security group)"
