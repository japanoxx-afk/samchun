param([string]$OutputDirectory = 'dist', [string]$ServerExecutable = 'dist\server\samchun-server.exe')
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$outputPath = Join-Path $taskRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path "$outputPath" | Out-Null
$serverPath = Join-Path $taskRoot $ServerExecutable
if (!(Test-Path -LiteralPath $serverPath)) { throw 'Build the server first or provide -ServerExecutable.' }
$serverResource = '/resource:' + $serverPath + ',samchun-server.exe'
$resourceArgument = '/resource:' + $taskRoot + '\assets\rally.bin,rally.bin'
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:winexe /platform:x86 /out:"$outputPath\launcher.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll $resourceArgument ("/resource:" + $taskRoot + "\assets\selection.bin,selection.bin") ("/resource:" + $taskRoot + "\PATCH_NOTES.txt,PATCH_NOTES.txt") $serverResource "$taskRoot\src\Launcher.cs" "$taskRoot\src\EditorLaunch.cs" "$taskRoot\src\GamePatches.cs" "$taskRoot\src\OnlineUpdate.cs" "$taskRoot\src\NetworkPatch.cs" "$taskRoot\src\CompatPatch.cs"
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
(Get-FileHash -LiteralPath "$outputPath\launcher.exe" -Algorithm SHA256).Hash | Set-Content -LiteralPath "$outputPath\SHA256.txt" -Encoding ASCII
