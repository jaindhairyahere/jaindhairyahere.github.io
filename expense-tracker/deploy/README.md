# Deploy pipeline — dev here, run on the ngrok device

This machine is the **dev/AI-coding ground**. Code is pushed to GitHub
(`jaindhairyahere.github.io`, `expense-tracker/`). A second device where **ngrok
is allowed** runs a worker that auto-pulls `main` and redeploys on every commit.

```
[ dev machine ] --git push--> [ GitHub main ] <--poll-- [ ngrok laptop: worker.sh ]
                                                              |  venv + gunicorn restart
                                                              v
                                                    [ app @ 127.0.0.1:8000 ] <- ngrok -> friends
```

Because the **ngrok reserved domain lives on the allowed device**, the public
URL is stable and Google OAuth keeps working across restarts.

---

## One-time setup on the ngrok laptop (Linux/macOS)

Prereqs: `git`, `python3` (3.12+), and `ngrok` (permitted on this laptop).

1. **Clone the repo** (public, no auth needed):
   ```bash
   git clone https://github.com/jaindhairyahere/jaindhairyahere.github.io.git ~/jaindhairyahere.github.io
   ```

2. **Create `expense-tracker/backend/.env`** (never committed):
   ```ini
   DJANGO_SECRET_KEY=<python3 -c "import secrets;print(secrets.token_urlsafe(64))">
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.ngrok-free.dev
   DJANGO_CSRF_TRUSTED_ORIGINS=https://yarn-stoning-stinky.ngrok-free.dev
   DJANGO_SECURE_PROXY=True
   FIELD_ENCRYPTION_KEY=<python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
   GOOGLE_OAUTH_CLIENT_ID=<your id>
   GOOGLE_OAUTH_CLIENT_SECRET=<your secret>
   # DATABASE_URL omitted -> SQLite (fine for a friends trial). For Postgres,
   # set DATABASE_URL=postgres://user:pass@localhost:5432/expense
   ```
   > `DJANGO_SECURE_PROXY=True` lets Django trust ngrok's HTTPS so secure cookies
   > work. Optionally add `DJANGO_SUPERUSER_USERNAME/_EMAIL/_PASSWORD` for an admin.

3. **Register the Google redirect URI** (once) in Google Cloud Console →
   Credentials → your OAuth client → Authorized redirect URIs:
   ```
   https://yarn-stoning-stinky.ngrok-free.dev/accounts/google/login/callback/
   ```

4. **Start ngrok** with your reserved domain (points at gunicorn's port):
   ```bash
   ngrok http --domain=yarn-stoning-stinky.ngrok-free.dev 8000
   ```

5. **Start the deploy worker** (another shell). It does the first deploy, then
   redeploys on every push to `main`:
   ```bash
   chmod +x ~/jaindhairyahere.github.io/expense-tracker/deploy/worker.sh
   REPO_DIR=~/jaindhairyahere.github.io ~/jaindhairyahere.github.io/expense-tracker/deploy/worker.sh
   ```

The worker: `git reset --hard origin/main` → create/refresh venv → `pip install`
→ `migrate` → `collectstatic` → restart gunicorn (daemonized; PID in
`backend/gunicorn.pid`, logs in `backend/logs/`). Static is served by WhiteNoise.
Friends visit `https://yarn-stoning-stinky.ngrok-free.dev`.

---

## Daily loop

- **You (dev machine):** code with the AI → commit → `git push origin main`.
- **Worker (ngrok laptop):** detects the commit within ~30s → venv install →
  migrate → collectstatic → gunicorn restart → live.

## Notes
- The worker uses `git reset --hard origin/main` — the laptop is a pure mirror of
  `main`; don't keep local edits there (the untracked `.env` is safe).
- SQLite (default) is fine for a small friends trial (WAL is enabled). Switch
  `DATABASE_URL` to Postgres if you outgrow it.
- Keep the worker and ngrok alive across reboots with `systemd` user services,
  `tmux`/`screen`, or `pm2`.
- gunicorn is Unix-only — this path assumes the laptop is Linux/macOS.
- The `docker-compose.yml` in the repo is an alternative container deploy; it is
  not used by this venv+gunicorn worker.
