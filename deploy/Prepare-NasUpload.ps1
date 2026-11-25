# Builds deploy\upload\samchun-live\ : exactly the files to upload to File Station game-servers/samchun-live/.
# The upload folder never contains data/ - uploading it can never overwrite accounts or match records on the NAS.
# Usage (PowerShell, in the repository):  .\deploy\Prepare-NasUpload.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $here 'upload\samchun-live'

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force (Join-Path $out 'app') | Out-Null
Copy-Item (Join-Path $repo 'server\compat_server.py') (Join-Path $out 'app\compat_server.py')
Copy-Item (Join-Path $here 'compose.yaml') (Join-Path $out 'compose.yaml')
Copy-Item (Join-Path $here 'NAS_DEPLOY.md') (Join-Path $out 'NAS_DEPLOY.md')

$version = (Select-String -Path (Join-Path $repo 'server\compat_server.py') -Pattern "^SERVER_VERSION = '([^']+)'").Matches[0].Groups[1].Value
$commit = (git -C $repo rev-parse --short HEAD) 2>$null
Set-Content -Path (Join-Path $out 'app\DEPLOYED_VERSION.txt') -Encoding ascii -Value @(
    "server_version=$version",
    "git_commit=$commit",
    "prepared=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
)
Write-Host "Upload folder ready: $out" -ForegroundColor Green
Write-Host "server $version (commit $commit)"
Get-ChildItem -Recurse $out | Where-Object { -not $_.PSIsContainer } |
    ForEach-Object { '  ' + $_.FullName.Substring($out.Length + 1) + "  ($($_.Length) bytes)" }
