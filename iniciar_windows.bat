@echo off
cd /d "%~dp0backend"
python -m pip install -q fastapi uvicorn python-multipart pypdf pdf2image pillow openpyxl 2>nul
python main.py
pause
