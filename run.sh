#!/usr/bin/env bash
# YC Launch Monitor — convenience launcher
#   ./run.sh --once          run a single monitoring pass (dry-run unless webhook set)
#   ./run.sh --loop          run forever at the configured interval
#   ./run.sh --dry-run       print alerts to console instead of Slack
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python -m yc_monitor.main "$@"
