#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

cat <<EOF

Installed.

Run GUI:
  source "$VENV_DIR/bin/activate"
  python "$ROOT_DIR/soft_jaw_gui_opengl.py"

Run CLI:
  source "$VENV_DIR/bin/activate"
  python "$ROOT_DIR/soft_jaw_gen_v3.py" --input /path/to/part.step --output-dir ./output
EOF
