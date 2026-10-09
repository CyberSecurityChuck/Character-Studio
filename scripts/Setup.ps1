$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
Push-Location $projectDir
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv before running setup. See README.md.' }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 24 LTS before running setup.' }
    uv sync --locked --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency setup failed.' }
    npm.cmd ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency setup failed.' }
    npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    Write-Output 'Setup complete. Open Start-Studio.cmd.'
} finally { Pop-Location }
