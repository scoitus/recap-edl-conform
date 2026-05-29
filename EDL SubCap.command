#!/bin/bash
# Double-click this file in Finder to launch the EDL -> SubCap GUI.
# It finds a python3 that has tkinter, then runs gui.py from this folder.

cd "$(dirname "$0")" || exit 1

PY=""
for cand in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)"; do
  if [ -n "$cand" ] && [ -x "$cand" ] && "$cand" -c "import tkinter" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Could not find a python3 with tkinter installed."
  echo "On macOS with Homebrew, install it with:"
  echo "    brew install python-tk"
  echo
  read -r -p "Press Return to close this window. "
  exit 1
fi

"$PY" gui.py
