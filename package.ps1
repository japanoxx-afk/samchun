param([string]$Version = '1.3.0-test.1', [string]$SourceDirectory = 'dist')
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$source = Join-Path $taskRoot $SourceDirectory
$stage = Join-Path $taskRoot ('releases\package-' + $Version)
$zip = Join-Path $taskRoot ('releases\samchun-' + $Version + '.zip')
if ((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $zip)) { throw 'Package already exists. Use a fresh version.' }
foreach ($required in @('launcher.exe','SHA256.txt','server\samchun-server.exe','runtime\cnc-ddraw\ddraw.dll')) {
 if (!(Test-Path -LiteralPath (Join-Path $source $required))) { throw "Missing package input: $required" }
}
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath "$source\launcher.exe","$source\SHA256.txt","$taskRoot\README.md","$taskRoot\RELEASE_NOTES.md" -Destination $stage
Copy-Item -LiteralPath "$taskRoot\licenses" -Destination $stage -Recurse
New-Item -ItemType Directory -Path "$stage\runtime","$stage\server" | Out-Null
Copy-Item -LiteralPath "$source\runtime\cnc-ddraw" -Destination "$stage\runtime" -Recurse
Copy-Item -LiteralPath "$source\server\samchun-server.exe" -Destination "$stage\server"
$checksums = @('launcher.exe','server\samchun-server.exe') | ForEach-Object { (Get-FileHash -LiteralPath (Join-Path $stage $_) -Algorithm SHA256).Hash + '  ' + $_ }
$checksums | Set-Content -LiteralPath "$stage\PACKAGE-SHA256.txt" -Encoding ASCII
Compress-Archive -Path "$stage\*" -DestinationPath $zip
Get-FileHash -LiteralPath $zip -Algorithm SHA256
