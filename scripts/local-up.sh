#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

backend_venv="${FAMILYOPS_BACKEND_VENV:-/private/tmp/familyops-ai-backend-venv}"
backend_python="$backend_venv/bin/python"
backend_pip="$backend_venv/bin/pip"
backend_requirements_hash="$backend_venv/.requirements.sha256"

if command -v brew >/dev/null 2>&1 && [[ -d "$(brew --prefix node@20 2>/dev/null)/bin" ]]; then
  export PATH="$(brew --prefix node@20)/bin:$PATH"
fi

if [[ ! -x ./node_modules/.bin/next ]]; then
  npm ci
fi

ensure_backend_venv() {
  local requirements_hash
  requirements_hash="$(shasum -a 256 backend/requirements.txt | awk '{print $1}')"

  if [[ ! -x "$backend_python" ]]; then
    python3.11 -m venv "$backend_venv"
  fi

  if [[ ! -f "$backend_requirements_hash" || "$(cat "$backend_requirements_hash")" != "$requirements_hash" ]]; then
    "$backend_pip" install --upgrade pip
    "$backend_pip" install -r backend/requirements.txt
    printf '%s\n' "$requirements_hash" > "$backend_requirements_hash"
  fi
}

cleanup() {
  if [[ -n "${backend_pid:-}" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi

  if [[ -n "${frontend_pid:-}" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

ensure_backend_venv

export APP_ENV="${APP_ENV:-local}"
export ENVIRONMENT="${ENVIRONMENT:-local}"
export DEBUG="${DEBUG:-false}"
export DATABASE_URL="${DATABASE_URL:-}"
export REDIS_URL="${REDIS_URL:-}"
export ENABLE_SHARED_RESILIENCE_REDIS="${ENABLE_SHARED_RESILIENCE_REDIS:-false}"

echo "Starting backend with virtualenv at $backend_venv"
(cd backend && "$backend_python" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload) &
backend_pid=$!

echo "Starting frontend on http://127.0.0.1:5000"
./node_modules/.bin/next dev -p 5000 -H 127.0.0.1 &
frontend_pid=$!

wait "$backend_pid" "$frontend_pid"
