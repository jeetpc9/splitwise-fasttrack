#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# On Apple Silicon, build the venv with the native arm64 Python slice (not Rosetta).
run_python() {
  if [[ "$(uname -m)" == "arm64" ]]; then
    /usr/bin/arch -arm64 python3 "$@"
  else
    python3 "$@"
  fi
}

echo "Setting up Splitwise FastTrack …"
if [[ "$(uname -m)" == "arm64" ]]; then
  echo "  Architecture: Apple Silicon (arm64)"
else
  echo "  Architecture: $(uname -m)"
fi

run_python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
run_python -m pip install --upgrade pip
run_python -m pip install -e .

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — add your SPLITWISE_API_KEY before importing."
fi

echo ""
echo "Setup complete."
echo "  Launch GUI:  make gui"
echo "  One-click:   make app   (creates Splitwise FastTrack.app)"
echo "  Or:          source .venv/bin/activate && splitwise-bulk-gui"
