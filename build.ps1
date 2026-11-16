# Builds dist\8BitDo-XInput-Bridge.exe (single file, includes the ViGEmBus installer and mapping.json).
# Setup once:  python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location $PSScriptRoot
$map = (Resolve-Path 'mapping.json').Path
# PyInstaller logs to stderr, so do not let PowerShell treat that as a failure; check the exit code instead.
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --console --name 8BitDo-XInput-Bridge --collect-all vgamepad --add-data "$map;." --distpath dist --workpath build --specpath build bridge.py 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Get-Item dist\8BitDo-XInput-Bridge.exe | Select-Object Name, Length
