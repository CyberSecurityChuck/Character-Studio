param([string]$Backup)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\Setup.ps1 first.' }
Push-Location $projectDir
try {
    $configText = & $pythonExe -B -c 'from backend.configuration import load_settings; print(load_settings().model_dump_json())'
    if ($LASTEXITCODE -ne 0) { throw 'Invalid studio configuration. Nothing was changed.' }
    $config = $configText | ConvertFrom-Json
    # Restoring replaces the data folder, so the studio must not be running.
    $running = $false
    try { $health = Invoke-RestMethod "http://127.0.0.1:$($config.port)/api/health" -TimeoutSec 2; $running = $health.application -eq 'character-studio' } catch { }
    $pidFile = Join-Path $config.data_dir 'server-process.json'
    if (Test-Path -LiteralPath $pidFile) {
        $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        if (Get-Process -Id $record.pid -ErrorAction SilentlyContinue) { $running = $true }
    }
    if ($running) { throw 'Character Studio is running. Double-click Stop-Studio.cmd first, then try again. Nothing was changed.' }
    Write-Output 'Character Studio - restore a backup'
    Write-Output "Data folder: $($config.data_dir)"
    Write-Output ''
    if ($Backup) { & $pythonExe -B -m backend.backup restore $Backup } else { & $pythonExe -B -m backend.backup restore }
    if ($LASTEXITCODE -ne 0) { exit 1 }
} finally { Pop-Location }
