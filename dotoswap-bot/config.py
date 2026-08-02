"""
Configuration for the DotoSwap availability monitor.

This tool is a *personal availability notifier*. It polls the public
marketplace listing at a fixed, respectful rate and alerts you when a
ticket appears so you can complete the purchase yourself, manually.

It deliberately does NOT:
  - evade rate limiting (it backs off politely on HTTP 429),
  - disguise itself as a browser to defeat bot detection,
  - out-poll or race other buyers.
"""

import os

try:
    # Optional: load a local .env so secrets stay out of the code.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Base URL of the marketplace API.
BASE_URL = (
    "https://swapbff20250715042304-dvcbfgdjfkcbakaz."
    "westeurope-01.azurewebsites.net/api"
)

# Path to the public "available items" endpoint.
AVAILABLE_ITEMS_PATH = "/Marktplaats/getBeschikbareMarktplaatsItems"

# How often to poll, in seconds. Keep this respectful (>= 20s).
POLL_INTERVAL_SECONDS = 30

# HTTP request timeout, in seconds.
REQUEST_TIMEOUT_SECONDS = 15

# Honest, identifiable User-Agent. We are not pretending to be a browser.
USER_AGENT = "dotoswap-availability-notifier/1.0 (personal use)"

# When a 429 (rate limited) is received, wait this long before retrying,
# then keep doubling up to the max. This RESPECTS the server's throttling.
BACKOFF_START_SECONDS = 60
BACKOFF_MAX_SECONDS = 15 * 60  # 15 minutes

# Base URL to open in your browser when a ticket is found. The bot appends
# nothing automatic here beyond opening the site so YOU can complete checkout.
CHECKOUT_URL = "https://swap.dodentocht.be/SwapMarktplaats"

# If True, automatically open the checkout site in your default browser
# the first time a ticket is detected.
OPEN_BROWSER_ON_HIT = True

# If True, play a sound when a ticket is detected (Windows uses winsound).
PLAY_SOUND_ON_HIT = True

# --- Human-confirmed one-click reserve ---------------------------------------
# When True, on a hit the monitor ASKS you to confirm. Only if you type "y"
# does it call the documented reserve + start-swap endpoints ONCE and open the
# voucher URL for you to pay. This is a manual convenience triggered by a human
# key-press. It is NOT an autonomous racing/sniping loop and it does not evade
# rate limits or spoof a browser.
ENABLE_ONE_CLICK_RESERVE = True

# Documented endpoints (from the official swagger) used only for the single,
# human-confirmed reserve action above.
RESERVE_PATH = "/Marktplaats/reserveerTicket"
START_SWAP_PATH = "/Marktplaats/startSwapVanMarktplaats"

# --- Email alert (personal Gmail via SMTP) -----------------------------------
# Sends a plain notification email when a ticket is found, so your phone pings.
# This uses your PERSONAL Gmail only. The password is NEVER stored here — it is
# read from the environment / a local .env file that you fill in yourself.
#
# Gmail requires an APP PASSWORD (not your normal password):
#   Google Account -> Security -> 2-Step Verification -> App passwords.
# Put it in .env as DOTOSWAP_SMTP_PASSWORD (see .env.example).
EMAIL_ENABLED = False
EMAIL_TO = "jaindhairyabookings@gmail.com"
EMAIL_FROM = os.environ.get("DOTOSWAP_SMTP_USER", "jaindhairyabookings@gmail.com")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit TLS (SSL)
SMTP_PASSWORD = os.environ.get("DOTOSWAP_SMTP_PASSWORD", "")
