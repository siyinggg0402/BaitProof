#!/usr/bin/env bash
# Run ON the Nebius VM (Ubuntu) as a sudoer:   bash deploy/setup_vm.sh <git-repo-url> [domain]
#   domain given  -> Caddy serves it over HTTPS (point its DNS A record at this VM first)
#   no domain     -> plain HTTP on port 80 (fine for an IP-only demo)
# Safe to re-run: after you fill in /opt/baitproof/.env, run it again (or `sudo systemctl restart baitproof baitproof-bot`).
set -euo pipefail
REPO="${1:?usage: setup_vm.sh <git-repo-url> [domain]}"
DOMAIN="${2:-}"
sudo apt-get update -y && sudo apt-get install -y python3-venv git caddy fonts-noto-cjk fonts-noto-core libfribidi0 libharfbuzz0b  # the fonts draw Chinese and Tamil on the share-card image (Tamil also needs Pillow's text shaping)
sudo useradd --system --home /opt/baitproof baitproof 2>/dev/null || true
sudo mkdir -p /opt/baitproof /var/lib/baitproof/logs
sudo chown -R "$USER" /opt/baitproof
git clone "$REPO" /opt/baitproof 2>/dev/null || git -C /opt/baitproof pull
cd /opt/baitproof
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
sudo chown -R baitproof:baitproof /var/lib/baitproof
sudo chown -R baitproof /opt/baitproof && sudo chmod 600 .env
sudo cp deploy/baitproof.service /etc/systemd/system/

# Caddy: automatic HTTPS for a domain, or plain HTTP for an IP-only demo
if [ -n "$DOMAIN" ]; then
  sed "s/baitproof.example.com/$DOMAIN/" deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile >/dev/null
else
  printf ':80 {\n    encode gzip\n    reverse_proxy 127.0.0.1:8000\n}\n' | sudo tee /etc/caddy/Caddyfile >/dev/null
fi

# The Telegram bot is optional: it only starts once TELEGRAM_BOT_TOKEN is in .env
if grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env; then
  sudo -u baitproof .venv/bin/pip install -q "python-telegram-bot>=21"
  sudo cp deploy/baitproof-bot.service /etc/systemd/system/
  BOT=baitproof-bot
else
  BOT=""
  echo "(no TELEGRAM_BOT_TOKEN in .env yet: the bot is not started; fill it in and re-run this script)"
fi

sudo systemctl daemon-reload
sudo systemctl enable --now baitproof $BOT
sudo systemctl restart baitproof $BOT caddy
sleep 3
curl -fsS -o /dev/null -w "web app: HTTP %{http_code}\n" http://127.0.0.1:8000/ || echo "web app did not answer: sudo journalctl -u baitproof -n 50"
echo "Open ports 80 and 443 in the Nebius security group. Fill in /opt/baitproof/.env (NEBIUS_API_KEY ...) and re-run if you have not."
