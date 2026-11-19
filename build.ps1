# Builds dist\SmartWFHTracker.exe (run from the project root, venv activated).
$ErrorActionPreference = "Stop"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed - build aborted." }
pyinstaller --noconfirm --clean --onefile --windowed --name SmartWFHTracker `
  --collect-all customtkinter --collect-data tzdata `
  --hidden-import win32com.client --hidden-import pythoncom --hidden-import win32timezone `
  --hidden-import pystray._win32 `
  --add-data "database\schema.sql;database" --add-data "assets;assets" `
  main.py
Write-Host "Built: dist\SmartWFHTracker.exe"
