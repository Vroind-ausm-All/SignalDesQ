#!/usr/bin/env bash
# SignalDesk – Start für Linux: ./start.sh  (richtet beim ersten Mal alles ein und öffnet den Browser)
cd "$(dirname "$0")" || exit 1
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    exec "$candidate" -m sales_tool.bootstrap "$@"
  fi
done
echo "Für SignalDesk wird Python 3.10 oder neuer benötigt (z. B. sudo apt install python3 python3-venv)." >&2
exit 1
