#!/bin/bash
cd "$(dirname "$0")/backend"
PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10; do
  if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then echo 'Python3 nao encontrado'; exit 1; fi
$PYTHON -m pip install -q --break-system-packages fastapi uvicorn python-multipart pypdf pdf2image pillow openpyxl 2>/dev/null || $PYTHON -m pip install -q --user fastapi uvicorn python-multipart pypdf pdf2image pillow openpyxl 2>/dev/null || true
$PYTHON main.py
