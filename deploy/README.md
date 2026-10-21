# Deploying Baitproof on a Nebius VM

About 20 minutes. You need: a Nebius account with a VM, your Token Factory API key, and (optional) a domain and a Telegram bot token.
Inference stays on Nebius Token Factory; the VM only runs the web app (and the bot).

## 1. Create the VM
- Ubuntu 22.04 or 24.04, 2 vCPU / 4 GB RAM is plenty (the model runs on Token Factory, not on the VM). A public IP.
- Security group: allow **22** (SSH), **80** and **443** (web).

## 2. Domain (optional, recommended)
Create an `A` record for your domain pointing at the VM's public IP. With a domain, Caddy gets an HTTPS certificate automatically. Without one the app is served over plain HTTP on the IP, which is fine for a quick demo (but Telegram deep links and `https` cookies are nicer with a domain).

## 3. Install
```bash
ssh ubuntu@<vm-ip>
git clone <your-public-repo-url> baitproof && cd baitproof
bash deploy/setup_vm.sh <your-public-repo-url> [your.domain.com]
```
The script installs Python, Caddy and `fonts-noto-cjk` (so the share card can draw Chinese), puts the app in `/opt/baitproof`, creates a locked-down `baitproof` user, installs two systemd services (`baitproof`, and `baitproof-bot` once a Telegram token exists) and starts Caddy. It is safe to re-run.

## 4. Configure
```bash
sudo -u baitproof nano /opt/baitproof/.env      # never commit this file
```
| Variable | Value |
|---|---|
| `NEBIUS_API_KEY` | your Token Factory key |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1/` |
| `NEBIUS_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| `BAITPROOF_URL` | the public address, e.g. `https://your.domain.com` (the bot uses it for links) |
| `BAITPROOF_ADMIN_TOKEN` | a long random string: it unlocks `/admin` (health, metrics, feedback) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | optional, from @BotFather |
| `TAVILY_API_KEY` | optional (review-style web checks) |

Then re-run `bash /opt/baitproof/deploy/setup_vm.sh <repo-url> [domain]` (it starts the bot once the token is set), or just `sudo systemctl restart baitproof baitproof-bot`.

## 5. Check it works
```bash
curl -I http://127.0.0.1:8000/                       # 200 on the VM itself
sudo systemctl status baitproof --no-pager            # active (running)
sudo journalctl -u baitproof -n 50 --no-pager         # app output
```
Open the site, check a message (the first one can take up to a minute while the model warms up; the app warms it at start), switch to 简体中文, open `/admin` and paste the admin token. Logs are in `/var/lib/baitproof/logs/events.jsonl` (no message text is ever written there).

## 6. Telegram bot (optional)
In @BotFather: `/newbot`, copy the token into `.env`, then `/setcommands` and paste:
```
start - What I can do
quiz - A quick 5-question scam quiz
challenge - Send your family a "can you spot the scam?" link
history - Your latest checks
score - Your Baitproof score
link - Connect this chat to your Baitproof website profile
unlink - Disconnect
lang - Language: en, zh or zh-Hant
help - Help
```
Test: send the bot a suspicious message, then `/quiz`. Link it to the website: **Records** > *Connect Telegram* shows a one-time code to send as `/link CODE`.

## 7. Update
```bash
cd /opt/baitproof && sudo -u baitproof git pull && sudo systemctl restart baitproof baitproof-bot
```

## What is protected
- `.env` is mode 600 and owned by the service user; the services run with `NoNewPrivileges`, a read-only filesystem except `/var/lib/baitproof`, and a private `/tmp`.
- Public mode (`BAITPROOF_MULTIUSER=1`, set by the unit) gives every visitor an anonymous profile database, so strangers never see each other's records.
- Strict CSP, no CORS, per-IP rate limits on the routes that cost model calls (`BAITPROOF_RATE`, default 30/min) and a login limit on `/admin`.

## Troubleshooting
| Symptom | Look at |
|---|---|
| Site not reachable | security group ports 80/443; `sudo systemctl status caddy`; DNS has propagated |
| Checks say "offline mode" | `NEBIUS_API_KEY` empty or wrong: `cd /opt/baitproof && sudo -u baitproof .venv/bin/python -m scripts.ops.verify_setup` (never prints the key) |
| Share card shows English only | `fc-list :lang=zh` shows no font: `sudo apt-get install fonts-noto-cjk` |
| `/admin` is empty | check `BAITPROOF_ADMIN_TOKEN`; logs exist under `/var/lib/baitproof/logs` |
| Bot silent | `sudo journalctl -u baitproof-bot -n 50`; token and username in `.env`; only one bot process may poll a token |

Cost: each check is well under a cent on Token Factory. `python -m scripts.ops.logs_report` on the VM (with `BAITPROOF_LOG_DIR=/var/lib/baitproof/logs`) shows tokens and spend.
