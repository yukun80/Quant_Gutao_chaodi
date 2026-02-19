#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env not found; copy .env.example and set JQ_USERNAME/JQ_PASSWORD first"
  exit 2
fi

export PYTHONPATH="$ROOT_DIR"

DATE_ARG="${1:-2025-01-10}"
CODE_ARG="${2:-600000}"

python -m src.backtest_cli \
  --source joinquant \
  --date "$DATE_ARG" \
  --code "$CODE_ARG"
