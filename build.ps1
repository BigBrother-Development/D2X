# Builds dist\DInput-to-XInput.exe (single file, no console window). It bundles the ViGEmBus driver
# installer (shipped inside vgamepad) and the default mappings folder.
# Setup once:  python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location $PSScriptRoot
$py = '.\.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force assets | Out-Null
& $py icon.py assets\icon.ico
$icon = (Resolve-Path 'assets\icon.ico').Path
$maps = (Resolve-Path 'mappings').Path
# PyInstaller logs to stderr, so do not let PowerShell treat that as a failure; check the exit code instead.
& $py -m PyInstaller --noconfirm --onefile --windowed --name DInput-to-XInput --icon $icon `
    --collect-all vgamepad --hidden-import pystray._win32 `
    --add-data "$maps;mappings" --distpath dist --workpath build --specpath build app.py 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Get-Item dist\DInput-to-XInput.exe | Select-Object Name, Length
