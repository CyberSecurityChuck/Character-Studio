param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\Setup.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'frontend\dist\index.html'))) {
    throw 'Build the frontend first: npm --prefix frontend run build'
}
Push-Location $projectDir
try {
    $configText = & $pythonExe -B -c 'from backend.configuration import load_settings; print(load_settings().model_dump_json())'
    if ($LASTEXITCODE -ne 0) { throw 'Invalid studio configuration. No server was started.' }
    $config = $configText | ConvertFrom-Json
    $baseUrl = "http://127.0.0.1:$($config.port)"
    $health = $null
    try { $health = Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 2 } catch { }
    if ($health -and $health.application -ne 'character-studio') { throw 'The configured port is in use by another service.' }
    if ($health) {
        $existing = Invoke-RestMethod "$baseUrl/api/bootstrap" -TimeoutSec 2
        if ($existing.data_directory -ne $config.data_dir) { throw 'A studio with a different data directory is already using this port. Stop it or select another port.' }
    }
    if (-not $health) {
        # Validate and prepare external storage through the same backend configuration rules.
        & $pythonExe -B -c 'from backend.configuration import load_settings, initialize_storage; initialize_storage(load_settings())'
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the external data directory.' }
        $process = Start-Process -FilePath $pythonExe -ArgumentList '-B', '-m', 'backend' -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $config.data_dir 'server.stdout.log') -RedirectStandardError (Join-Path $config.data_dir 'server.stderr.log')
        $ready = $false
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 250
            $process.Refresh()
            if ($process.HasExited) { throw "Studio startup failed. Check server.stderr.log in $($config.data_dir)." }
            try {
                $health = Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 1
                if ($health.application -eq 'character-studio') { $ready = $true; break }
            } catch { }
        }
        if (-not $ready) { throw 'Studio startup timed out. Inspect the server logs before retrying.' }
        @{ pid = $process.Id; started_utc = $process.StartTime.ToUniversalTime().ToString('o'); executable = $pythonExe } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $config.data_dir 'server-process.json') -Encoding UTF8
    }
    Write-Output "Character Studio: $baseUrl"
    if (-not $NoBrowser) { Start-Process $baseUrl }
} finally { Pop-Location }
