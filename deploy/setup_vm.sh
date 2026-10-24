#!/usr/bin/env bash
# Run ON the Nebius VM (Ubuntu) as a sudoer:   bash deploy/setup_vm.sh <git-repo-url> [domain]
#   domain given  -> Caddy serves it over HTTPS (point its DNS A record at this VM first)
#   no domain     -> plain HTTP on port 80 (fine for an IP-only demo)
# Safe to re-run: after you fill in /opt/baitproof/.env, run it again (or `sudo systemctl restart baitproof baitproof-bot`).
set -euo pipefail
REPO="${1:?usage: setup_vm.sh <git-repo-url> [domain]}"
DOMAIN="${2:-}"
sudo apt-get update -y && sudo apt-get install -y python3-venv git caddy cron fonts-noto-cjk fonts-noto-core libfribidi0 libharfbuzz0b  # the fonts draw Chinese and Tamil on the share-card image (Tamil also needs Pillow's text shaping)
sudo useradd --system --home /opt/baitproof baitproof 2>/dev/null || true
sudo mkdir -p /opt/baitproof /var/lib/baitproof/logs
sudo chown baitproof:baitproof /opt/baitproof
cd /opt/baitproof
# Everything inside /opt/baitproof is made and updated by the service user, so this script can be re-run by whoever runs it (the .env file is locked to that user)
if [ -d .git ]; then sudo -u baitproof git pull; else sudo -u baitproof git clone "$REPO" .; fi
sudo -u baitproof python3 -m venv .venv && sudo -u baitproof .venv/bin/pip install -q -r requirements.txt
[ -f .env ] || sudo -u baitproof cp .env.example .env
sudo chown -R baitproof:baitproof /var/lib/baitproof
sudo chmod 600 .env
sudo cp deploy/baitproof.service /etc/systemd/system/

# A small server (1 GB) can run out of memory while pip builds things: give it a 1 GB swap file once
if [ -z "$(swapon --show --noheadings)" ]; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile \
    && (grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null) || echo "(could not add swap; continuing)"
fi

# Nightly upkeep as the service user: remove empty visitor profiles, then back up what is left (every cookie-less page view makes a ~130 KB file)
sudo tee /etc/cron.d/baitproof >/dev/null <<'CRON'
BAITPROOF_DB=/var/lib/baitproof/baitproof.sqlite
30 3 * * * baitproof cd /opt/baitproof && .venv/bin/python -m scripts.ops.backup >> /var/lib/baitproof/logs/maintenance.log 2>&1
15 3 * * * baitproof cd /opt/baitproof && .venv/bin/python -m scripts.ops.prune_profiles --apply >> /var/lib/baitproof/logs/maintenance.log 2>&1
CRON

# Caddy: automatic HTTPS for a domain, or plain HTTP for an IP-only demo
if [ -n "$DOMAIN" ]; then
  sed "s/baitproof.example.com/$DOMAIN/" deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile >/dev/null
else
  printf ':80 {\n    encode gzip\n    reverse_proxy 127.0.0.1:8000\n}\n' | sudo tee /etc/caddy/Caddyfile >/dev/null
fi

# The Telegram bot is optional: it only starts once TELEGRAM_BOT_TOKEN is in .env
if sudo grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env; then
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
for _ in $(seq 1 20); do curl -fsS -o /dev/null http://127.0.0.1:8000/ 2>/dev/null && break; sleep 2; done  # the app takes a little while to start on a small server
curl -fsS -o /dev/null -w "web app: HTTP %{http_code}\n" http://127.0.0.1:8000/ || echo "web app did not answer: sudo journalctl -u baitproof -n 50"
echo "Open ports 80 and 443 in your cloud firewall (security group). Fill in /opt/baitproof/.env (NEBIUS_API_KEY ...) and re-run this script if you have not."
