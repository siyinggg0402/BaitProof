# Deploying Baitproof on a Nebius VM

About 20 minutes. You need: a Nebius account with a VM, your Token Factory API key, and (optional) a domain and a Telegram bot token.
Inference stays on Nebius Token Factory; the VM only runs the web app (and the bot).

## 0. Put the code where the VM can fetch it
The VM clones your repository, so it has to be reachable: a **public** GitHub repo, or a private one with a deploy key. On your own machine, check `git status` shows no `.env` (it is git-ignored), commit what you want to ship, then push it yourself: `git push -u origin main`. Never commit `.env` or a key.

## 1. Create the VM
- Ubuntu 22.04 or 24.04, 2 vCPU / 4 GB RAM is plenty (the model runs on Token Factory, not on the VM). A public IP.
- Security group: allow **22** (SSH), **80** and **443** (web).

## 2. Domain (optional, recommended)
Create an `A` record for your domain pointing at the VM's public IP. With a domain, Caddy gets an HTTPS certificate automatically. Without one the app is served over plain HTTP on the IP, which is fine for a quick demo (but Telegram deep links and `https` cookies are nicer with a domain). **The installable app and the Android Share option need HTTPS**: browsers only run the service worker on HTTPS or `localhost`, so on a bare IP the site works but has no Install button and does not appear in the Share sheet.

## 3. Install
```bash
ssh ubuntu@<vm-ip>
git clone <your-public-repo-url> baitproof && cd baitproof
bash deploy/setup_vm.sh <your-public-repo-url> [your.domain.com]
```
The script installs Python, Caddy, `fonts-noto-cjk` and `fonts-noto-core` (so the share card can draw Chinese and Tamil), puts the app in `/opt/baitproof`, creates a locked-down `baitproof` user, installs two systemd services (`baitproof`, and `baitproof-bot` once a Telegram token exists) and starts Caddy. It is safe to re-run.

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

Optional: voice notes (Telegram) and QR codes in screenshots need two extra packages. On the VM: `sudo -u baitproof /opt/baitproof/.venv/bin/pip install -r /opt/baitproof/requirements-extras.txt`. The first voice note downloads a ~145 MB speech model (once; set `BAITPROOF_STT=0` to skip voice entirely). Screenshots work without any extra package, using the vision model on Token Factory.

The public phishing list (about 11 MB, from Phishing.Database) downloads by itself shortly after the app starts and then daily, into `/var/lib/baitproof/cache`. To have it at once: `sudo -u baitproof env BAITPROOF_CACHE_DIR=/var/lib/baitproof/cache /opt/baitproof/.venv/bin/python -m scripts.ops.refresh_blocklist`. Set `BAITPROOF_BLOCKLIST=0` to turn it off.

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
lang - Language: en, ms, ta, zh or zh-Hant
help - Help
```
The bot speaks as Finn, the website's mascot. Give it his face too: `/setuserpic` in @BotFather, then send `web/static/img/finn-avatar.png` (or set the name, description and picture through the Bot API's `setMyName`, `setMyDescription` and `setMyProfilePhoto`).
Test: send the bot a suspicious message, then `/quiz`. Link it to the website: on **Records** or **My profile**, tap *Open Telegram to connect* and press Start in Telegram (needs `TELEGRAM_BOT_USERNAME` in `.env`); the one-time code is under *Show a code instead* and can be sent as `/link CODE`.

## 7. Update
```bash
cd /opt/baitproof && sudo -u baitproof git pull && sudo systemctl restart baitproof baitproof-bot
```

## Keeping it running for a couple of months
- **HTTPS without buying a domain:** a free name such as `yourname.duckdns.org` (duckdns.org, sign in, pick a name, point it at the server's IP) is enough: pass it to `setup_vm.sh` as the domain and Caddy gets the certificate by itself (ports 80 and 443 must be open). HTTPS is what makes the app installable and the Share option work.
- **Nightly upkeep** (`/etc/cron.d/baitproof`, written by the setup script, UTC): 03:15 removal of empty visitor profiles, 03:30 a backup of all data that is left to `/var/lib/baitproof/backups` (the newest 7 are kept). Without that, every cookie-less page view (link previews, crawlers, uptime pings) leaves a ~130 KB file. It never touches an account, a friend, a family group, a Telegram chat, a game run or anyone with a check or practice history (`scripts/ops/prune_profiles.py`). The log is `/var/lib/baitproof/logs/maintenance.log`.
- **Copy a backup to your own machine now and then**, because the backups sit on the same server: `mkdir -p ~/baitproof-backups && scp 'ubuntu@<ip>:/var/lib/baitproof/backups/*' ~/baitproof-backups/`. They hold sign-in key hashes: keep them private, never in the repository.
- **Watch it:** monitor `https://<domain>/static/img/icon-192.png` (a page URL would create a profile on every ping, and the manifest refuses HEAD requests). `/admin` shows estimated model spend; lower `BAITPROOF_RATE` (per visitor, per minute) in `.env` if you worry about strangers using up credit, and keep an eye on the credit in the Nebius console.
- **Look after the server:** `df -h /var/lib/baitproof` for disk, `sudo apt-get update && sudo apt-get -y upgrade` once a month, and after a reboot check `sudo systemctl status baitproof baitproof-bot caddy` (all three start by themselves).
- **At the end**, take a last backup, then delete the server so it stops costing money.

## What is protected
- `.env` is mode 600 and owned by the service user; the services run with `NoNewPrivileges`, a read-only filesystem except `/var/lib/baitproof`, and a private `/tmp`.
- Public mode (`BAITPROOF_MULTIUSER=1`, set by the unit) gives every visitor an anonymous profile database, so strangers never see each other's records. Profiles can become accounts (a nickname, an avatar and a sign-in key kept only as a hash) so friends can compare Scam Road distances; the sign-in form shares the `/admin` login rate limit, and the profile id (the session cookie) is never shown to anyone. Set `BAITPROOF_URL` so invite links carry your public address. **Notifications are optional**: `pip install -r requirements-extras.txt`, then once on the VM `sudo -u baitproof /opt/baitproof/.venv/bin/python -m scripts.ops.make_vapid` (writes `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY` into `.env` and never prints the private key), set `VAPID_SUBJECT` to a mailto: or https: address you control, and restart. Until both keys exist the site shows nothing about notifications. They need HTTPS.
- Strict CSP, no CORS, per-IP rate limits on the routes that cost model calls (`BAITPROOF_RATE`, default 30/min) and a login limit on `/admin`.

## Troubleshooting
| Symptom | Look at |
|---|---|
| Site not reachable | security group ports 80/443; `sudo systemctl status caddy`; DNS has propagated |
| Checks say "offline mode" | `NEBIUS_API_KEY` empty or wrong: `cd /opt/baitproof && sudo -u baitproof .venv/bin/python -m scripts.ops.verify_setup` (never prints the key) |
| The browser offers no "Install app", or Baitproof is missing from the Android Share sheet | The site is on plain HTTP. Use a domain so Caddy serves HTTPS; then open the site once in Chrome and install it from the browser menu ("Install app" or "Add to Home Screen") |
| Share card shows English only | Chinese: `fc-list :lang=zh` shows no font: `sudo apt-get install fonts-noto-cjk`. Tamil: needs `fonts-noto-core` and a Pillow with text shaping (raqm: `python -c "from PIL import features; print(features.check('raqm'))"` should say True); without them the card is drawn in English, never with broken letters |
| `/admin` is empty | check `BAITPROOF_ADMIN_TOKEN`; logs exist under `/var/lib/baitproof/logs` |
| Cannot SSH in from your network (port 22 blocked by a proxy or VPN) | Use the cloud console's browser terminal (Google: Compute Engine > VM instances > SSH). Run the same commands there; its menu (gear) has **Upload file** for the `.env` |
| Bot silent | `sudo journalctl -u baitproof-bot -n 50`; token and username in `.env`; only one bot process may poll a token |

Cost: each check is well under a cent on Token Factory. `/admin` shows tokens, estimated spend, latency and gate behaviour.
