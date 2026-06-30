#!/bin/bash
# Double-click this file in Finder to launch the EDL -> SubCap GUI.
# It runs the project's virtual-environment Python so dependencies are available.

cd "$(dirname "$0")" || exit 1

if [ ! -x "./.venv/bin/python" ]; then
  echo "Could not find ./.venv/bin/python in $(pwd)."
  echo "Set up the environment first:  uv sync"
  read -r -p "Press Return to close…" _
  exit 1
fi

exec ./.venv/bin/python gui.py
