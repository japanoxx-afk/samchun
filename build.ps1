$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$resourceArgument = '/resource:' + $taskRoot + '\dist\runtime\patches\rally.bin,rally.bin'
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo /target:winexe /platform:x86 /out:"$taskRoot\dist\launcher.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $resourceArgument "$taskRoot\src\Launcher.cs" "$taskRoot\src\GamePatches.cs"
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
(Get-FileHash -LiteralPath "$taskRoot\dist\launcher.exe" -Algorithm SHA256).Hash | Set-Content -LiteralPath "$taskRoot\dist\SHA256.txt" -Encoding ASCII
