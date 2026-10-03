param([string]$Python = 'python', [string]$OutputDirectory = 'dist\server')
$ErrorActionPreference = 'Stop'
# Build dependency: python -m pip install pyinstaller==6.22.3
& $Python -m PyInstaller --noconfirm --onefile --name samchun-server --distpath (Join-Path $PSScriptRoot $OutputDirectory) --workpath "$PSScriptRoot\verification\pyinstaller" --specpath "$PSScriptRoot\verification" "$PSScriptRoot\server\compat_server.py"
if ($LASTEXITCODE -ne 0) { throw 'Server build failed' }
