$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
Push-Location $projectDir
try {
    $configText = & $pythonExe -B -c 'from backend.configuration import load_settings; print(load_settings().model_dump_json())'
    if ($LASTEXITCODE -ne 0) { throw 'Invalid studio configuration.' }
    $config = $configText | ConvertFrom-Json
    $pidFile = Join-Path $config.data_dir 'server-process.json'
    if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No launcher-managed studio process recorded.'; return }
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($process) {
        if ($process.Path -ne $record.executable -or $process.StartTime.ToUniversalTime().ToString('o') -ne $record.started_utc) {
            throw 'Process identity changed. Refusing to stop an unrelated process.'
        }
        Stop-Process -Id $process.Id
        $process.WaitForExit(5000) | Out-Null
    }
    Remove-Item -LiteralPath $pidFile
    Write-Output 'Character Studio stopped. Saved preferences remain on disk.'
} finally { Pop-Location }
