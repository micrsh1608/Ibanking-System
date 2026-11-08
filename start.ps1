<#
.SYNOPSIS
Start the complete iBanking Docker demo from one terminal.
.EXAMPLE
.\start.ps1
.EXAMPLE
.\start.ps1 -Detached
.EXAMPLE
.\start.ps1 -Check
.EXAMPLE
.\start.ps1 -PrepareDemo -Detached
.EXAMPLE
.\start.ps1 -Rebuild -Detached
#>
[CmdletBinding()]
param(
    [switch]$Detached,
    [switch]$Check,
    [switch]$SeedDemo,
    [switch]$PrepareDemo,
    [switch]$Rebuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$savedDemoSeedMode = [Environment]::GetEnvironmentVariable('IBANKING_SEED_DEMO', 'Process')

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

function Test-LocalApplicationImage {
    # Compare the files actually copied by our Dockerfile, not their timestamps.
    # Private env files and generated Python caches never enter this manifest.
    $manifest = @{}
    $sourceFiles = @(Get-Item -LiteralPath (Join-Path $PSScriptRoot 'requirements.txt'))
    foreach ($directory in @('services', 'shared', 'frontend', 'infra')) {
        $sourceFiles += @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $directory) -File -Recurse -Force)
    }
    foreach ($file in $sourceFiles) {
        $relative = $file.FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/')
        if ($relative -match '(^|/)__pycache__/|\.py[cod]$|\.log$|(^|/)\.env($|\.)|^infra/env/[^/]+\.env$') { continue }
        $hasher = [Security.Cryptography.SHA256]::Create()
        $stream = [IO.File]::OpenRead($file.FullName)
        try { $manifest[$relative] = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
    }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($manifest | ConvertTo-Json -Compress)))
    $probe = @'
import base64, hashlib, json
from pathlib import Path
expected = json.loads(base64.b64decode('__MANIFEST__'))
root = Path('/workspace')
files = [root / 'requirements.txt']
for directory in ('services', 'shared', 'frontend', 'infra'):
    files.extend(path for path in (root / directory).rglob('*') if path.is_file())
actual = {}
for path in files:
    relative = path.relative_to(root)
    if ('__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo', '.pyd', '.log')
        or path.name == '.env' or path.name.startswith('.env.')
        or (relative.parent.as_posix() == 'infra/env' and path.suffix == '.env')):
        continue
    actual[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
raise SystemExit(0 if actual == expected else 3)
'@
    # No application entrypoint, network, env secrets or database volumes.
    $probe.Replace('__MANIFEST__', $encoded) | & docker run --rm -i --network none --pull never --entrypoint python ibanking-api:local -
    if ($LASTEXITCODE -eq 0) { return $true }
    if ($LASTEXITCODE -eq 3) { return $false }
    throw 'Cannot verify the local application image. Review the Docker output above.'
}

function Initialize-DemoCatalog {
    param([string[]]$ComposeArguments)
    $endpoint=(& docker @ComposeArguments port sqlserver 1433 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $endpoint -ne '127.0.0.1:14330') {
        throw 'Expected the main SQL endpoint 127.0.0.1:14330; catalog preparation was not executed.'
    }
    $outputLines=& docker @ComposeArguments exec -T --env IBANKING_DEMO_CATALOG_TARGET=ibanking-demo account python -m infra.docker.demo_catalog
    $helperExit=$LASTEXITCODE
    $catalog=($outputLines -join "`n") | ConvertFrom-Json
    if ($helperExit -ne 0 -or $catalog.status -ne 'PREPARED') {
        if ($null -ne $catalog.PSObject.Properties['error']) { throw $catalog.error }
        throw 'The demo catalog was not prepared; existing data was not reset.'
    }
    $artifactDirectory=Join-Path $PSScriptRoot 'artifacts'
    [IO.Directory]::CreateDirectory($artifactDirectory) | Out-Null
    $encoding=New-Object Text.UTF8Encoding($false)
    $accountIds=@();$studentCodes=@()
    foreach ($user in $catalog.users) {
        if ($user.username -notmatch '^demo(0[1-9]|10)$' -or [string]$user.account_id -notmatch '^[1-9][0-9]*$') { throw 'Invalid catalog account metadata.' }
        $accountIds+=[string]$user.account_id
    }
    foreach ($student in $catalog.students) {
        if ($student.mssv -notmatch '^SV202610(0[1-9]|1[0-2])$') { throw 'Invalid catalog student metadata.' }
        $studentCodes+="'"+$student.mssv+"'"
    }
    if ($accountIds.Count -ne 10 -or @($accountIds | Select-Object -Unique).Count -ne 10) { throw 'The catalog must identify ten distinct demo accounts.' }
    [IO.File]::WriteAllText((Join-Path $artifactDirectory 'demo-accounts.json'),($outputLines -join "`n"),$encoding)
    $accountList=$accountIds -join ','
    $studentList=$studentCodes -join ','
    $sql=@"
-- MAIN project: SSMS 127.0.0.1,14330, SQL login sa, password from infra/env/docker.env.
-- Read-only: execute before and after the Web demo. This script never resets data.
SELECT u.username,a.id AS account_id,a.balance,a.status,u.email,u.email_verified_at,u.email_channel
FROM account_db.dbo.accounts a JOIN account_db.dbo.users u ON u.id=a.user_id
WHERE a.id IN ($accountList) ORDER BY u.username;

SELECT payment_id,transaction_code,account_id,mssv,total_amount,status,phase,error_message
FROM payment_db.dbo.payments WHERE account_id IN ($accountList) ORDER BY created_at;

SELECT account_id,payment_id,entry_type,amount
FROM account_db.dbo.account_entries WHERE account_id IN ($accountList) ORDER BY id;

SELECT id AS student_id,mssv,full_name FROM tuition_db.dbo.students ORDER BY id;

SELECT s.id AS student_id,s.mssv,s.full_name,i.id AS invoice_id,i.semester,i.amount_due,i.status,i.paid_payment_id
FROM tuition_db.dbo.tuition_invoices i JOIN tuition_db.dbo.students s ON s.id=i.student_id
WHERE s.mssv IN ($studentList) ORDER BY s.id,i.id;

-- Expected: no duplicate money operations for the same payment and type.
SELECT payment_id,entry_type,COUNT(*) AS entry_count FROM account_db.dbo.account_entries
WHERE account_id IN ($accountList) GROUP BY payment_id,entry_type HAVING COUNT(*)>1;
"@
    [IO.File]::WriteAllText((Join-Path $artifactDirectory 'demo-inspect.sql'),$sql,$encoding)
    Write-Host 'MAIN WEB: http://127.0.0.1:8001/ui/     EMAIL: real SMTP to each verified user address'
    Write-Host 'New-account password: Demo_123!  (existing passwords and balances are preserved)'
    $catalog.users | Select-Object username,balance,email,email_channel,email_verified,verification | Format-Table -AutoSize | Out-Host
    if ($catalog.manual_verification_required -gt 0) {
        Write-Host 'Enter and verify each payer real email in Personal information before paying. No profile or verification was changed by preparation.'
    }
    $catalog.students | Select-Object id,mssv,student_name,unpaid_total | Format-Table -AutoSize | Out-Host
    Write-Host 'Every payer must verify their own real email in Personal information; SMTP login/sender is not the recipient.'
    Write-Host 'Create a second payer: demo-data.ps1 -CreateTestAccount -Email your-real-address; login huy2 / HuyDemo_123! and verify its email.'
    Write-Host 'Balance race: demo02 / SV20261003 and SV20261004, 7M each; fresh 10M account ends at 3M after one succeeds.'
    Write-Host 'Same tuition: demo03 and demo04 / SV20261005 (2M+3M); only one payer succeeds.'
    Write-Host 'Additional unpaid tuition: SV20261001 (2.5M) and SV20261002 (3.5M).'
    Write-Host 'Those expected balances apply to untouched fixtures; current balances/debt are printed above.'
    Write-Host 'Catalog: artifacts/demo-accounts.json  |  Read-only SQL: artifacts/demo-inspect.sql'
    Write-Host 'No payment was executed and no existing money, profile, password, paid invoice or history was reset.'
}

try {
    $env:IBANKING_SEED_DEMO = if ($SeedDemo) { 'true' } else { 'false' }
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

    # Build before touching running services. A failed build must not stop SQL.
    $localImage = & docker image ls --quiet ibanking-api:local
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local Docker images.' }
    $needsBuild = $Rebuild -or -not $localImage
    if (-not $needsBuild) { $needsBuild = -not (Test-LocalApplicationImage) }
    if ($needsBuild) {
        Write-Host 'Building the application image (first run, source changed, or -Rebuild)...'
        & docker @composeArgs build account
        if ($LASTEXITCODE -ne 0) {
            throw 'Image build failed, possibly due to Internet/DNS. Existing services and data were left in place. Restore the connection and retry.'
        }
    }
    else {
        Write-Host 'Source matches the local image; reusing it without a registry request.'
    }

    # Only missing infrastructure images require a download. Never pull cached tags.
    foreach ($image in @('mcr.microsoft.com/mssql/server:2022-latest')) {
        $localInfrastructureImage = & docker image ls --quiet $image
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local Docker images.' }
        if (-not $localInfrastructureImage) {
            & docker pull $image
            if ($LASTEXITCODE -ne 0) { throw ('Cannot download missing image: ' + $image + '. Check the Internet/DNS connection and retry.') }
        }
    }

    Write-Host ''
    Write-Host 'iBanking: http://127.0.0.1:8001/ui/'
    Write-Host 'API docs: http://127.0.0.1:8001/docs | :8002/docs | :8003/docs'
    Write-Host 'Email: real SMTP; recipients use their verified profile email.'
    Write-Host ''

    & docker @composeArgs up --no-build --pull never --wait --wait-timeout 300
    if ($LASTEXITCODE -ne 0) {
        throw 'Startup failed. Existing containers were kept for diagnosis. Check: docker compose --env-file infra/env/docker.env ps -a'
    }
    if ($PrepareDemo) { Initialize-DemoCatalog -ComposeArguments $composeArgs }
    if ($Detached) {
        Write-Host 'All services are ready. Stop with: docker compose --env-file infra/env/docker.env stop'
    }
    else {
        Write-Host 'Logs appear below. Press Ctrl+C to stop the demo.'
        try {
            & docker @composeArgs logs --follow --tail 80
            if ($LASTEXITCODE -ne 0) { throw 'Cannot follow container logs. Review the Docker output above.' }
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
finally {
    [Environment]::SetEnvironmentVariable('IBANKING_SEED_DEMO', $savedDemoSeedMode, 'Process')
}
