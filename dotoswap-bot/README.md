# DotoSwap availability monitor

A small, **personal availability notifier** for the DotoSwap marketplace
(Dodentocht swap). It watches the public listing and alerts you the moment a
ticket appears so **you** can go complete the purchase yourself.

## What it does

- Polls the public "available items" endpoint at a **fixed, respectful rate**
  (default: every 30s).
- **Backs off politely** on HTTP 429 (rate limited) — it never tries to route
  around the server's throttling.
- On a hit it alerts you every way at once:
  - **desktop notification + sound**,
  - **opens the swap site** in your browser,
  - **emails your phone** (optional, personal Gmail — see below).
- Offers a **human-confirmed one-click reserve**: it asks `Reserve #… ? [y/N]`
  and only if you type `y` does it call the documented reserve + start-swap
  endpoints **once** and open the checkout voucher for you to pay.
- De-duplicates alerts so you aren't spammed for the same ticket.

## What it deliberately does NOT do

- No browser/User-Agent spoofing to defeat bot detection.
- No high-frequency "sniping" to race other buyers.
- No autonomous lock-acquisition, rebound-exploitation, or auto-payment.
- No evasion of rate limits.
- No use of work/corporate accounts or tampering with their security controls.

**You always confirm the reserve and complete the payment yourself.**

## Setup

```powershell
cd dotoswap-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Email alerts (optional, for phone notifications)

Emails are sent from a **personal Gmail** via SMTP. The password is never
stored in the code — it is read from a local `.env` file you create.

1. Copy the template:

   ```powershell
   Copy-Item .env.example .env
   ```

2. In your Google Account, enable **2-Step Verification**, then create an
   **App Password** (Security → 2-Step Verification → App passwords).
   This is a 16-character password, *not* your normal Gmail password.

3. Put your values in `.env`:

   ```
   DOTOSWAP_SMTP_USER=youraddress@gmail.com
   DOTOSWAP_SMTP_PASSWORD=your-16-char-app-password
   ```

`.env` is git-ignored and stays on your machine. If you don't set it up, email
is simply skipped and the desktop/sound/browser alerts still work.

To disable email entirely, set `EMAIL_ENABLED = False` in `config.py`.

## Run

```powershell
python monitor.py
```

Stop with `Ctrl+C`.

## Test (no network, no real alerts)

```powershell
python test_monitor.py
```

Runs offline unit tests with mocked API responses covering the alert,
de-duplication, 429 backoff, and reserve flows.

## Configure

Edit `config.py`:

- `POLL_INTERVAL_SECONDS` — how often to check (keep it >= 20s).
- `CHECKOUT_URL` — the site opened in your browser on a hit.
- `OPEN_BROWSER_ON_HIT` / `PLAY_SOUND_ON_HIT` — toggle those alerts.
- `BACKOFF_START_SECONDS` / `BACKOFF_MAX_SECONDS` — 429 backoff bounds.
- `ENABLE_ONE_CLICK_RESERVE` — turn the confirm-to-reserve step on/off.
- `EMAIL_ENABLED` / `EMAIL_TO` — email alert toggle and recipient.

## Files

| File | Purpose |
| --- | --- |
| `monitor.py` | Main polling loop, alerts, and reserve flow. |
| `alerts.py` | Desktop notification, sound, browser, and email helpers. |
| `config.py` | All tunable settings. |
| `test_monitor.py` | Offline unit tests. |
| `.env.example` | Template for your email credentials. |

## A note on fair use

This tool is for grabbing **one** ticket for yourself, at human speed, using
the marketplace as intended. Please don't extend it into a sniping/hoarding
bot — that ruins the pool for everyone else waiting for the same ticket. If
DotoSwap offers an official API key or notification feature, prefer that.
