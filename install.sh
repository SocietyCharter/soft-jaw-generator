#!/bin/bash
# Soft Jaw Generator — installer
# Creates a venv and installs all dependencies.
# Blender must be installed separately (https://blender.org).

set -e

PYTHON=${PYTHON:-python3}
VENV_DIR="$(dirname "$0")/venv"

echo "=== Soft Jaw Generator — Install ==="

# Check Python
if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ and retry."
    exit 1
fi

PY_VER=$("$PYTHON" -c "import sys; print('%d.%d' % sys.version_info[:2])")
echo "Python: $PY_VER"

# Create venv
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtualenv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "Virtualenv already exists at $VENV_DIR"
fi

# Install deps
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$(dirname "$0")/requirements.txt"

# Check Blender
if command -v blender &>/dev/null; then
    BLENDER_VER=$(blender --version 2>&1 | head -1)
    echo "Blender: $BLENDER_VER"
else
    echo ""
    echo "WARNING: Blender not found in PATH."
    echo "  Preview rendering requires Blender. Download from https://blender.org"
    echo "  Install it and ensure 'blender' is on your PATH."
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "To run the GUI:"
echo "  source venv/bin/activate"
echo "  python3 soft_jaw_gui.py"
echo ""
echo "To run CLI:"
echo "  source venv/bin/activate"
echo "  python3 soft_jaw_gen_v2.py --input part.step --output-dir ./output"
