#!/bin/bash
# SignalDesk – Ein-Klick-Start für macOS (Doppelklick im Finder).
# Beim ersten Mal: Rechtsklick → „Öffnen“, da die Datei nicht von Apple signiert ist.
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done

if [ -z "$PY" ]; then
  echo
  echo "Für SignalDesk wird Python 3.10 oder neuer benötigt."
  echo "Die Download-Seite wird geöffnet. Nach der Installation diese Datei erneut doppelklicken."
  open "https://www.python.org/downloads/macos/"
  read -r -p "Enter drücken zum Schließen …"
  exit 1
fi

"$PY" -m sales_tool.bootstrap "$@"
rc=$?
if [ $rc -ne 0 ]; then
  echo
  read -r -p "SignalDesk wurde mit einem Fehler beendet (Code $rc). Enter drücken zum Schließen …"
fi
exit $rc
