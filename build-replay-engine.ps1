param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
 New-Item -ItemType Directory -Force -Path dist/replay | Out-Null
 & 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:winexe /platform:x86 /out:dist/replay/samchun-replay-controls.exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll ("/resource:" + $PSScriptRoot + "\assets\unit-names.tsv,unit-names.tsv") "$PSScriptRoot\src\ReplayControls.cs" "$PSScriptRoot\src\LiveObserver.cs" "$PSScriptRoot\src\ObserverPlayerData.cs" "$PSScriptRoot\src\ObserverHud.cs"
 if ($LASTEXITCODE -ne 0) { throw 'Replay controls build failed' }
 & $Python -m PyInstaller --noconfirm --onefile --windowed --name samchun-replay-engine-1.3.57 --distpath dist/replay --workpath verification/pyinstaller --specpath verification/pyinstaller --add-binary "${PSScriptRoot}/dist/replay/samchun-replay-controls.exe:." --add-data "${PSScriptRoot}/assets/dgvoodoo:hardware-video" --copy-metadata pefile --copy-metadata psutil --add-data "${PSScriptRoot}/licenses/replay-THIRD-PARTY.txt:licenses" tools/replay_engine.py
 if ($LASTEXITCODE -ne 0) { throw 'Replay engine build failed' }
} finally { Pop-Location }





