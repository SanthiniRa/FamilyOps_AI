#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Docker Compose is not installed." >&2
  echo "Install the Docker Compose plugin or docker-compose, then run: npm run docker" >&2
  exit 1
fi

if [[ ! -f backend/.env ]]; then
  echo "backend/.env is missing; using Docker defaults from docker-compose.yml." >&2
  echo "Copy backend/.env.example to backend/.env if you want to override API keys or local settings." >&2
fi

"${compose_cmd[@]}" up --build
