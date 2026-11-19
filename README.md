# Smart WFH & Leave Tracker

Windows desktop app (Python 3.12, CustomTkinter, SQLite). It reminds you at 11:00 AM
(and 3:00 PM if still unselected) to choose **WFH** or **LEAVE**, stores the choice in
SQLite, and for WFH only, opens a **draft** in classic Outlook. **It never sends email.**

## Security rule
The app never calls Outlook's send method. It creates, saves and displays a draft; you click Send.
Enforced by `tests/test_email.py` (static source audit + mock whose send method fails the test).
Manual audit (PowerShell, from project root):

    Get-ChildItem -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\tests\\|\\.venv\\|\\dist\\|\\build\\' } |
      Select-String -Pattern '\.\s*Send\s*\(|SendAndSave|SendMail|smtplib'
    # expected: no output

## Setup and run (PowerShell)
    # 1. Install Python 3.12+ from python.org (tick "Add python.exe to PATH")
    python --version
    # 2. Virtual environment
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    # 3. Dependencies
    pip install -r requirements.txt
    # 4. Run (no terminal needed later; this is for first run)
    python main.py
    # 5. Tests (use mocks, never touch real Outlook)
    python -m pytest -v

## Build the EXE and installer
    .\build.ps1                                   # -> dist\SmartWFHTracker.exe (runs tests first)
    # Installer: install Inno Setup 6, then
    & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer.iss   # -> Output\SmartWFHTracker_Setup.exe

## Windows startup
Enabled by default and toggled in Settings. It writes one value under
`HKCU\...\CurrentVersion\Run` (no admin rights). Check or remove manually:

    Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name SmartWFHTracker
    Remove-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name SmartWFHTracker

## Data, backups, uninstall
* Database: `%LOCALAPPDATA%\SmartWFHTracker\attendance.db`, logs in `logs\app.log`.
* Backups: automatic once a day plus "Backup now"; last 10 kept. Change the folder in Settings
  (default `%LOCALAPPDATA%\SmartWFHTracker\backups`). A corrupt database is set aside and
  restored from the newest healthy backup.
* Uninstall: Settings > Apps > Smart WFH & Leave Tracker (removes the startup entry; your data is kept).
  To delete data too: `Remove-Item -Recurse "$env:LOCALAPPDATA\SmartWFHTracker"`.

## Outlook on the web / PWA (default mode)
Settings > Outlook type: `web` (default) or `classic`. Web mode opens a pre-filled compose window at
`https://outlook.cloud.microsoft/mail/deeplink/compose` in your default browser, using the account you are
signed in with. Nothing is stored or sent; you click Send. Notes:
* The link cannot choose or verify the sender account, and the app cannot confirm the draft exists
  in Outlook, only that the browser opened. Use **Reopen compose** if the fields come up empty
  (Outlook on the web sometimes skips pre-filling right after a sign-in).
* To open it in the installed PWA instead of a tab, set Edge/Chrome link-capturing for that site
  (Edge: Settings > Apps > "Open links in installed app").

## Requirements (classic mode only)
Classic Outlook (COM) signed in with the sender account in Settings. "New Outlook" has no COM support;
if Outlook is missing the attendance is still saved, and "Retry draft" works later.
