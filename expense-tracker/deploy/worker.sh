#!/usr/bin/env bash
#
# Continuous-deploy worker for the ngrok device (venv + gunicorn, no Docker).
# Polls origin/<branch>; on a new commit it hard-resets, installs deps,
# migrates, collects static, and restarts gunicorn. Run once and leave running.
#
# Usage:
#   REPO_DIR=~/jaindhairyahere.github.io ./expense-tracker/deploy/worker.sh
#
# Env vars (all optional):
#   REPO_DIR  path to the cloned repo   (default: ~/jaindhairyahere.github.io)
#   BRANCH    branch to track           (default: main)
#   INTERVAL  poll seconds              (default: 30)
#   BIND      gunicorn bind address     (default: 127.0.0.1:8000)
#   WORKERS   gunicorn worker count     (default: 3)
#   PYTHON    python interpreter        (default: python3)
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/jaindhairyahere.github.io}"
BRANCH="${BRANCH:-main}"
INTERVAL="${INTERVAL:-30}"
BIND="${BIND:-127.0.0.1:8000}"
WORKERS="${WORKERS:-3}"
PYTHON="${PYTHON:-python3}"

BACKEND_DIR="$REPO_DIR/expense-tracker/backend"
VENV="$BACKEND_DIR/.venv"
PIDFILE="$BACKEND_DIR/gunicorn.pid"
LOG_DIR="$BACKEND_DIR/logs"

log() { echo "[$(date '+%F %T')] $*"; }

restart_gunicorn() {
  mkdir -p "$LOG_DIR"
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    log "Stopping gunicorn ($(cat "$PIDFILE"))"
    kill -TERM "$(cat "$PIDFILE")" || true
    sleep 2
  fi
  log "Starting gunicorn on $BIND"
  "$VENV/bin/gunicorn" config.wsgi:application \
    --chdir "$BACKEND_DIR" \
    --bind "$BIND" \
    --workers "$WORKERS" \
    --timeout 60 \
    --pid "$PIDFILE" \
    --daemon \
    --access-logfile "$LOG_DIR/access.log" \
    --error-logfile "$LOG_DIR/error.log"
}

deploy() {
  cd "$BACKEND_DIR"
  log "Deploying $(git -C "$REPO_DIR" rev-parse --short HEAD) ..."
  [ -d "$VENV" ] || { log "Creating venv"; "$PYTHON" -m venv "$VENV"; }
  "$VENV/bin/pip" install --quiet --upgrade pip wheel
  "$VENV/bin/pip" install --quiet -r requirements.txt
  "$VENV/bin/python" manage.py migrate --noinput
  DJANGO_DEBUG=False "$VENV/bin/python" manage.py collectstatic --noinput
  restart_gunicorn
  log "Deploy complete."
}

cd "$REPO_DIR"
log "Initial sync of origin/$BRANCH"
git fetch --quiet origin "$BRANCH"
git reset --hard "origin/$BRANCH"
deploy

log "Watching origin/$BRANCH every ${INTERVAL}s (Ctrl-C to stop)..."
while true; do
  if ! git fetch --quiet origin "$BRANCH"; then
    log "git fetch failed; will retry."
    sleep "$INTERVAL"; continue
  fi
  local_sha="$(git rev-parse HEAD)"
  remote_sha="$(git rev-parse "origin/$BRANCH")"
  if [ "$local_sha" != "$remote_sha" ]; then
    log "New commit detected: $remote_sha"
    git reset --hard "origin/$BRANCH"
    deploy
  fi
  sleep "$INTERVAL"
done
