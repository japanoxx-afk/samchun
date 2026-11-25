param([string]$OutputDirectory = 'dist', [string]$ServerExecutable = 'dist\server\samchun-server.exe')
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$outputPath = Join-Path $taskRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path "$outputPath" | Out-Null
$serverPath = Join-Path $taskRoot $ServerExecutable
if (!(Test-Path -LiteralPath $serverPath)) { throw 'Build the server first or provide -ServerExecutable.' }
$serverResource = '/resource:' + $serverPath + ',samchun-server.exe'
$resourceArgument = '/resource:' + $taskRoot + '\assets\rally.bin,rally.bin'
$replayEngine = Join-Path $taskRoot 'dist\replay\samchun-replay-engine-1.3.57.exe'
if (!(Test-Path -LiteralPath $replayEngine)) { throw 'Build tools/replay_engine.py with PyInstaller before building the launcher.' }
$replayResource = '/resource:' + $replayEngine + ',samchun-replay-engine.exe'
# RTS ARENA upload key (same value as the rtsarena stack's ARENA_UPLOAD_TOKEN). Never committed:
# taken from $env:ARENA_UPLOAD_TOKEN or the git-ignored file arena-token.txt next to this script.
$arenaToken = $env:ARENA_UPLOAD_TOKEN
$arenaTokenFile = Join-Path $taskRoot 'arena-token.txt'
if (!$arenaToken -and (Test-Path -LiteralPath $arenaTokenFile)) { $arenaToken = (Get-Content -LiteralPath $arenaTokenFile -Raw).Trim() }
if (!$arenaToken) { Write-Warning 'ARENA_UPLOAD_TOKEN / arena-token.txt not found: replay upload will be rejected (401) by the site.' }
$secretDir = Join-Path $taskRoot 'verification\build-secret'
New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
$secretFile = Join-Path $secretDir 'ArenaSecret.cs'
$escaped = ($arenaToken -replace '\\','\\' -replace '"','\"')
Set-Content -LiteralPath $secretFile -Encoding UTF8 -Value ('static class ArenaSecret { internal const string Token = "' + $escaped + '"; }')
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:winexe /platform:x86 /out:"$outputPath\launcher.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.IO.Compression.dll ("/resource:" + $taskRoot + "\licenses\replay-THIRD-PARTY.txt,replay-THIRD-PARTY.txt") $replayResource $resourceArgument ("/resource:" + $taskRoot + "\assets\selection.bin,selection.bin") ("/resource:" + $taskRoot + "\PATCH_NOTES.txt,PATCH_NOTES.txt") ("/resource:" + $taskRoot + "\assets\editor-upgrade.bin,editor-upgrade.bin") ("/resource:" + $taskRoot + "\assets\replay-test.screplay,replay-test.screplay") ("/resource:" + $taskRoot + "\assets\cnc-ddraw.dll,graphics.ddraw.dll") ("/resource:" + $taskRoot + "\assets\cnc-ddraw.ini,graphics.ddraw.ini") ("/resource:" + $taskRoot + "\licenses\cnc-ddraw-LICENSE.txt,graphics.cnc-ddraw-LICENSE.txt") $serverResource "$taskRoot\src\Launcher.cs" "$taskRoot\src\LauncherDiagnostics.cs" "$taskRoot\src\ReplayWindow.cs" "$taskRoot\src\ReplayEngine.cs" "$taskRoot\src\GraphicsRuntime.cs" "$taskRoot\src\VideoMode.cs" "$taskRoot\src\EditorLaunch.cs" "$taskRoot\src\EditorUpgrade.cs" "$taskRoot\src\GamePatches.cs" "$taskRoot\src\OnlineUpdate.cs" "$taskRoot\src\NetworkPatch.cs" "$taskRoot\src\CompatPatch.cs" "$taskRoot\src\ArenaUpload.cs" $secretFile
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
(Get-FileHash -LiteralPath "$outputPath\launcher.exe" -Algorithm SHA256).Hash | Set-Content -LiteralPath "$outputPath\SHA256.txt" -Encoding ASCII
