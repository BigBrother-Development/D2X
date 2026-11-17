# Builds dist\D2X.exe (single file, no console window). It bundles the ViGEmBus driver
# installer (shipped inside vgamepad), the HidHide installer (downloaded into vendor\) and the default mappings.
# Setup once:  python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location $PSScriptRoot
$py = '.\.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force assets | Out-Null
& $py icon.py assets\icon.ico
# HidHide installer (MIT, signed by Nefarius), bundled so the "hide controller" option can install the driver.
$hhName = 'HidHide_1.5.230_x64.exe'
$hhSha = 'F4BBBCB82E6258641B887C74BC81C4C5F66E4AA811808DFC304347687B7605F6'
New-Item -ItemType Directory -Force vendor | Out-Null
if (-not (Test-Path "vendor\$hhName")) {
    Invoke-WebRequest "https://github.com/nefarius/HidHide/releases/download/v1.5.230.0/$hhName" -OutFile "vendor\$hhName"
}
if ((Get-FileHash "vendor\$hhName" -Algorithm SHA256).Hash -ne $hhSha) { throw "vendor\$hhName does not match the expected SHA-256" }
$vendor = (Resolve-Path 'vendor').Path
$icon = (Resolve-Path 'assets\icon.ico').Path
$maps = (Resolve-Path 'mappings').Path
# PyInstaller logs to stderr, so do not let PowerShell treat that as a failure; check the exit code instead.
& $py -m PyInstaller --noconfirm --onefile --windowed --name D2X --icon $icon `
    --collect-all vgamepad --hidden-import pystray._win32 `
    --add-data "$maps;mappings" --add-data "$vendor;vendor" --distpath dist --workpath build --specpath build app.py 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Get-Item dist\D2X.exe | Select-Object Name, Length
