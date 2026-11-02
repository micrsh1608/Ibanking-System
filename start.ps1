<#
.SYNOPSIS
Start the complete iBanking Docker demo from one terminal.
.EXAMPLE
.\start.ps1
.EXAMPLE
.\start.ps1 -Detached
.EXAMPLE
.\start.ps1 -Check
#>
[CmdletBinding()]
param(
    [switch]$Detached,
    [switch]$Check
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-DemoSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

function Get-DockerEngineType {
    try {
        $result = & docker info --format '{{.OSType}}' 2>$null
        if ($LASTEXITCODE -eq 0) { return $result }
    }
    catch { }
    return ''
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI was not found. Install Docker Desktop with Linux containers first.'
    }

    & docker compose version --short
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is not available.' }

    $engineType = Get-DockerEngineType
    if (-not $engineType) {
        Write-Host 'Starting Docker Desktop...'
        & docker desktop start --timeout 120
        if ($LASTEXITCODE -ne 0) { throw 'Cannot start Docker Desktop. Open Docker Desktop and retry.' }
        $engineType = Get-DockerEngineType
        if (-not $engineType) { throw 'Docker Engine is not accessible.' }
    }
    if ($engineType -ne 'linux') {
        throw 'Switch Docker Desktop to Linux containers, then retry.'
    }

    $configPath = Join-Path $PSScriptRoot 'infra/env/docker.env'
    if (-not (Test-Path -LiteralPath $configPath)) {
        $content = @(
            '# Local Docker demo only; keep this file private.'
            ('MSSQL_SA_PASSWORD=Demo_A1!' + (New-DemoSecret))
            ('JWT_SECRET_KEY=' + (New-DemoSecret))
            ('INTERNAL_API_KEY=' + (New-DemoSecret))
        ) -join "`n"
        $stream = [IO.File]::Open($configPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
        $writer = New-Object IO.StreamWriter($stream, (New-Object Text.UTF8Encoding($false)))
        try { $writer.Write($content + "`n") }
        finally { $writer.Dispose() }
        Write-Host 'Created private Docker demo configuration.'
    }

    $composeArgs = @(
        'compose', '--project-directory', $PSScriptRoot,
        '--file', (Join-Path $PSScriptRoot 'compose.yaml'),
        '--env-file', $configPath
    )
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Docker Compose configuration.' }
    if ($Check) {
        Write-Host 'Docker Engine and Compose configuration are ready.'
        exit 0
    }

    Write-Host ''
    Write-Host 'iBanking: http://127.0.0.1:8001/ui/'
    Write-Host 'API docs: http://127.0.0.1:8001/docs | :8002/docs | :8003/docs'
    Write-Host 'Mailpit:  http://127.0.0.1:8025'
    Write-Host 'The first build can take several minutes.'
    Write-Host ''

    if ($Detached) {
        & docker @composeArgs up --build --wait --wait-timeout 300
        if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Review the Docker output above.' }
        Write-Host 'All services are ready. Stop with: docker compose --env-file infra/env/docker.env stop'
    }
    else {
        Write-Host 'Logs appear below. Press Ctrl+C to stop the demo.'
        try {
            & docker @composeArgs up --build --abort-on-container-failure --menu=false
            if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Review the Docker output above.' }
        }
        finally {
            & docker @composeArgs stop
        }
    }
}
catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
