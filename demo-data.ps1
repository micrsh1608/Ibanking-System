<#
.SYNOPSIS
Reset, seed or inspect only the local ibanking-demo Docker databases.
.EXAMPLE
.\demo-data.ps1 -Reset
.EXAMPLE
.\demo-data.ps1 -Seed
.EXAMPLE
.\demo-data.ps1 -NormalizeTuition
.EXAMPLE
.\demo-data.ps1 -NormalizeAccounts
.EXAMPLE
.\demo-data.ps1 -CreateTestAccount -Email 'your-second-address@example.org'
.EXAMPLE
.\demo-data.ps1 -AddTuition -Mssv SV2026002 -StudentName 'Nguyen Van An' -Semester TEST-HK1 -Amount 1500000.00
#>
[CmdletBinding(DefaultParameterSetName='Status')]
param(
    [Parameter(Mandatory,ParameterSetName='Reset')][switch]$Reset,
    [Parameter(Mandatory,ParameterSetName='Seed')][switch]$Seed,
    [Parameter(Mandatory,ParameterSetName='Normalize')][switch]$NormalizeTuition,
    [Parameter(Mandatory,ParameterSetName='NormalizeAccounts')][switch]$NormalizeAccounts,
    [Parameter(Mandatory,ParameterSetName='Account')][switch]$CreateTestAccount,
    [Parameter(ParameterSetName='Account')][string]$Username='huy2',
    [Parameter(ParameterSetName='Account')][string]$Email='',
    [Parameter(Mandatory,ParameterSetName='Tuition')][switch]$AddTuition,
    [Parameter(Mandatory,ParameterSetName='Tuition')][string]$Mssv,
    [Parameter(Mandatory,ParameterSetName='Tuition')][string]$StudentName,
    [Parameter(Mandatory,ParameterSetName='Tuition')][string]$Semester,
    [Parameter(Mandatory,ParameterSetName='Tuition')][string]$Amount
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$composeArgs=@('compose','--project-directory',$PSScriptRoot,'-p','ibanking-demo',
    '--file',(Join-Path $PSScriptRoot 'compose.yaml'),'--env-file',(Join-Path $PSScriptRoot 'infra/env/docker.env'))
try {
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration. Run start.ps1 -Check first.' }
    $sqlEndpoint=(& docker @composeArgs port sqlserver 1433 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $sqlEndpoint -ne '127.0.0.1:14330') { throw 'Refusing operation: expected local SQL endpoint 127.0.0.1:14330. Start the Docker project first.' }
    & docker @composeArgs build db-init
    if ($LASTEXITCODE -ne 0) { throw 'Cannot build the demo administration image.' }
    if ($Reset) {
        Write-Host 'Deleting all data in account_db, payment_db, tuition_db; recreating empty business tables.'
        & docker @composeArgs stop account payment tuition
        if ($LASTEXITCODE -ne 0) { throw 'Cannot stop services; reset was not started.' }
        $adminArgs=@('reset','--confirm-local-reset','ibanking-demo')
    } elseif ($NormalizeTuition -or $NormalizeAccounts) {
        Write-Host 'Backing up affected databases and rebuilding IDs together with their references.'
        & docker @composeArgs stop account payment tuition
        if ($LASTEXITCODE -ne 0) { throw 'Cannot stop services; normalization was not started.' }
        $normalizationAction=if ($NormalizeAccounts) { 'normalize-accounts' } else { 'normalize-tuition' }
        $adminArgs=@($normalizationAction,'--confirm-local-rewrite','ibanking-demo')
    } elseif ($CreateTestAccount) {
        $adminArgs=@('create-test-account','--username',$Username)
        if ($Email) { $adminArgs+=@('--email',$Email) }
    } elseif ($Seed) { $adminArgs=@('seed')
    } elseif ($AddTuition) { $adminArgs=@('add-tuition','--mssv',$Mssv,'--student-name',$StudentName,'--semester',$Semester,'--amount',$Amount)
    } else { $adminArgs=@('status') }
    if ($NormalizeTuition -or $NormalizeAccounts) {
        $outputLines=& docker @composeArgs run --rm --no-deps db-init python -m infra.docker.demo_admin @adminArgs
        if ($LASTEXITCODE -ne 0) { throw 'Normalization failed; services remain stopped for inspection. Database writes are transactional.' }
        $report=($outputLines -join "`n") | ConvertFrom-Json
        $backupDirectory=Join-Path $PSScriptRoot 'artifacts/db-backups'
        [IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
        foreach ($backup in $report.backups.PSObject.Properties) {
            & docker @composeArgs cp ('sqlserver:'+$backup.Value) $backupDirectory
            if ($LASTEXITCODE -ne 0) { throw 'Normalization completed, but copying a backup failed. The original backup remains in the SQL Server volume.' }
        }
        $reportName=if ($NormalizeAccounts) { 'account-normalization.json' } else { 'tuition-normalization.json' }
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot ('artifacts/'+$reportName)),
            ($outputLines -join "`n"),(New-Object Text.UTF8Encoding($false)))
        if ($NormalizeAccounts) {
            $report.users | Select-Object id,username | Format-Table -AutoSize | Out-Host
            $report.accounts | Select-Object id,user_id,account_number,balance | Format-Table -AutoSize | Out-Host
            Write-Host 'Remapped users must sign in again. Existing balances and payment outcomes were preserved.'
        } else {
            $report.students | Select-Object id,mssv,full_name | Format-Table -AutoSize | Out-Host
            Write-Host ('Invoices: '+$report.invoice_count)
        }
        Write-Host ('Backups: artifacts/db-backups; mapping: artifacts/'+$reportName)
    } else {
        & docker @composeArgs run --rm --no-deps db-init python -m infra.docker.demo_admin @adminArgs
        if ($LASTEXITCODE -ne 0) { throw 'Data operation failed. If resetting, services remain stopped for inspection.' }
    }
    if ($Reset -or $Seed -or $NormalizeTuition -or $NormalizeAccounts) {
        & docker @composeArgs up --detach --no-deps --no-build --wait --wait-timeout 120 account payment tuition
        if ($LASTEXITCODE -ne 0) { throw 'Data operation finished, but an API did not become healthy.' }
    }
    Write-Host 'Done. UI: http://127.0.0.1:8001/ui/'
} catch {
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
    exit 1
}
