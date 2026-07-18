# SplitCash — Shared Expenses + Credit-Card Cashback

A Splitwise-style expense tracker with a novel **credit-card cashback** feature:
record that an expense was paid on a friend's cashback card and the app
automatically reduces what you owe them by the cashback they earn.

- **Backend:** Django 5 + Django REST Framework (mobile-ready JSON API)
- **Frontend:** Bootstrap 5 + React (served same-origin, no build step)
- **DB:** SQLite (dev) or PostgreSQL (prod) — switch with one env var
- **Auth:** Google sign-in only (django-allauth), session cookies + CSRF

---

## Features

| Area | What you get |
|------|--------------|
| Groups | Regular groups + **friend** groups (unique 2-person, non-leavable) |
| Members | Registered users **or** name-only placeholders (link to a Google account later) |
| Expenses | Multiple payers + multiple splitters, per-expense currency, comments |
| Currency | INR / USD / EUR with near-live daily FX (Frankfurter, cached) |
| Debt simplify | Greedy min-cash-flow, per-group toggle + per-expense override |
| **Cashback** | Cards + cashback programs with day/week/month/year/lifetime + count caps |
| Cashback tools | "Check transaction" preview & "best card" suggestion |
| Settlements | Record payments; balances update instantly |
| Feature flags | Everything free by default; gate any capability server-side |

Every capability is behind a server-side flag in `settings.FEATURE_FLAGS`
(all `True` by default) so you can restrict features for a public deploy.

---

## Quick start (dev)

```powershell
cd expense-tracker\backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Create .env from the template and generate real keys:
Copy-Item .env.example .env
# then set DJANGO_SECRET_KEY and FIELD_ENCRYPTION_KEY (see .env.example comments)

.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/ and sign in with Google.

> Tip: to explore the UI without Google, create a superuser
> (`manage.py createsuperuser`), log in at `/admin/`, then open `/`.

Run the test suite (covers cashback caps, the "owe 90 not 100" rule,
multi-currency, min-cash-flow, settlements):

```powershell
.\.venv\Scripts\python.exe manage.py test apps.expenses
```

---

## Google OAuth setup

1. Google Cloud Console → **APIs & Services → Credentials → Create OAuth client ID → Web application**.
2. Authorized redirect URI:
   - Dev: `http://127.0.0.1:8000/accounts/google/login/callback/`
   - ngrok: `https://<your-host>.ngrok-free.app/accounts/google/login/callback/`
3. Put the client id/secret in `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```
   (No DB `SocialApp` row needed — credentials are read from env.)

---

## Production / ngrok deploy (Docker)

Requires Docker. The app is published to **loopback only**; ngrok tunnels to it.

```bash
cd expense-tracker
# backend/.env must contain real DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY,
# Google creds, and your ngrok host in DJANGO_ALLOWED_HOSTS /
# DJANGO_CSRF_TRUSTED_ORIGINS.
POSTGRES_PASSWORD=$(openssl rand -hex 16) docker compose up --build -d

# In another shell, expose it (add ngrok Google-OAuth gate / IP allowlist):
ngrok http 127.0.0.1:8000
```

Container hardening baked into `docker-compose.yml`: non-root user,
`cap_drop: ALL`, `no-new-privileges`, read-only root FS + tmpfs, pids/mem
limits, DB on an internal network with a named volume.

### Security notes
- **No full card numbers** are ever stored. Optional last-4 / expiry are
  **encrypted at rest** (Fernet) and never returned by the API.
- `DEBUG=False` in prod enables secure cookies, HSTS, and nosniff.
- Set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` to your ngrok host.
- Keep the ngrok URL private and enable ngrok's Google OAuth gate / IP allowlist.

---

## How cashback affects who-owes-whom

You spend **₹100** on Ritik's card (10% cashback, Swiggy). The whole amount is
your consumption:

- Ritik fronts ₹100 and keeps ₹10 cashback → his net outlay is ₹90.
- Your share is reduced by the cashback you generated → **you owe ₹90, not ₹100.**

Formula: each splitter owes `share − cashback × share / total`; the card owner
(who must be a payer) is credited the cashback. Every expense stays balanced.

---

## API surface (base `/api/v1/`)

`auth/csrf` · `auth/me` · `auth/logout` · `features` · `currencies` ·
`fx/convert` · `groups` (+`friend`, `members`, `simplify`) · `members` ·
`expenses` (+`comments`) · `comments` · `cards` · `cashback-programs` ·
`cashback` (check) · `cashback/best-card` · `settlements` · `balances`
