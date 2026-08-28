#Requires -Version 5.1
<#
.SYNOPSIS
    One-command local setup + launch for the SYZY stack (backend + web frontend).

.DESCRIPTION
    Provisions and starts everything needed to run SYZY locally:

      1. Checks prerequisites (docker, python, node/npm)
      2. Ensures the backend .env exists and has the local-first flags set
      3. Starts the Docker daemon if it is down, then waits for it
      4. Brings up Postgres + Redis and waits for them to actually accept connections
      5. Installs backend (pip) and web (npm) dependencies
      6. Applies Alembic migrations
      7. Verifies with the backend unit suite + a TypeScript check
      8. Launches uvicorn, the Celery worker, Celery beat, and next dev in
         separate windows, then health-checks them

    Every phase is idempotent -- re-running is safe. Already-listening ports are
    skipped rather than spawning a window that dies on a bind error.

.PARAMETER SkipTests
    Skip the backend unit suite and the TypeScript check.

.PARAMETER FullTest
    Additionally run the Playwright e2e suite after the stack is up (~2 min).

.PARAMETER NoLaunch
    Provision only. Do not spawn the four stack windows.

.EXAMPLE
    .\setup-local.ps1
    .\setup-local.ps1 -NoLaunch
    .\setup-local.ps1 -FullTest
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$FullTest,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
$Backend = Join-Path $Root 'backend'
$Web     = Join-Path $Root 'web'

$ApiPort = 8000
$WebPort = 3000

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

$script:StepNum = 0
# Base is 8 phases. -NoLaunch drops both the launch and health-check phases.
$script:TotalSteps = 8
if ($NoLaunch)  { $script:TotalSteps = $script:TotalSteps - 2 }
if ($SkipTests) { $script:TotalSteps = $script:TotalSteps - 1 }

$script:Warnings = @()

function Write-Step {
    param([string]$Message)
    $script:StepNum++
    Write-Host ''
    Write-Host ("[{0}/{1}] {2}" -f $script:StepNum, $script:TotalSteps, $Message) -ForegroundColor Cyan
}

function Write-Ok   { param([string]$m) Write-Host "        $m" -ForegroundColor Green }
function Write-Note { param([string]$m) Write-Host "        $m" -ForegroundColor DarkGray }

function Write-Warn {
    param([string]$m)
    Write-Host "        WARN  $m" -ForegroundColor Yellow
    $script:Warnings += $m
}

function Stop-WithError {
    param([string]$Message, [string]$Hint)
    Write-Host ''
    Write-Host "FAILED: $Message" -ForegroundColor Red
    if ($Hint) { Write-Host "        $Hint" -ForegroundColor Yellow }
    exit 1
}

# Run a native command in a directory, streaming its output, and fail on a
# nonzero exit code. PowerShell does not throw on native failures, so the
# $LASTEXITCODE check has to be explicit.
function Invoke-Native {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [string]$InDir,
        [string]$ErrorMessage,
        [string]$Hint
    )
    Push-Location $InDir
    try {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) {
            Stop-WithError "$ErrorMessage (exit $LASTEXITCODE)" $Hint
        }
    }
    finally { Pop-Location }
}

# Poll a condition until it returns true or the timeout expires.
function Wait-Until {
    param(
        [scriptblock]$Condition,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalSeconds = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds $IntervalSeconds
    }
    return $false
}

# Run a native command silently and report whether it succeeded. Native stderr
# under ErrorActionPreference = 'Stop' raises a terminating NativeCommandError in
# PS 5.1, so probes have to relax it locally.
function Test-NativeOk {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments > $null 2> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
    finally { $ErrorActionPreference = $previous }
}

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $conn)
}

function Test-Url {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    }
    catch { return $false }
}

function Start-StackWindow {
    param([string]$Title, [string]$WorkDir, [string]$Command)
    $inner = "`$Host.UI.RawUI.WindowTitle = '$Title'; " +
             "Set-Location '$WorkDir'; " +
             "Write-Host '=== $Title ===' -ForegroundColor Cyan; " +
             $Command
    Start-Process powershell -ArgumentList '-NoExit', '-NoProfile', '-Command', $inner | Out-Null
}

Write-Host ''
Write-Host 'SYZY local setup' -ForegroundColor White
Write-Host "Workspace: $Root" -ForegroundColor DarkGray

if (-not (Test-Path $Backend)) { Stop-WithError "backend not found at $Backend" }
if (-not (Test-Path $Web))     { Stop-WithError "web app not found at $Web" }

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------

Write-Step 'Checking prerequisites'

$missing = @()
foreach ($cmd in 'docker', 'python', 'node', 'npm') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { $missing += $cmd }
}
if ($missing.Count -gt 0) {
    Stop-WithError ("not on PATH: " + ($missing -join ', ')) 'Install the missing tools, then re-run.'
}

$pyVersion   = (& python --version)
$nodeVersion = (& node --version)
Write-Ok "$pyVersion / node $nodeVersion / docker present"

# Backend .env: create from the example if absent, then confirm the local-first
# flags. A .env pointing at remote Supabase is the classic silent failure -- the
# app runs, it just talks to the wrong database.
$envPath    = Join-Path $Backend '.env'
$envExample = Join-Path $Backend '.env.example'

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $envExample)) { Stop-WithError "no .env and no .env.example in $Backend" }
    Copy-Item $envExample $envPath
    Write-Ok 'created .env from .env.example'
}

$envText  = Get-Content $envPath -Raw
$expected = [ordered]@{
    'ENV'                       = 'local'
    'USE_LOCAL_DATABASE_IN_DEV' = 'true'
    'USE_LOCAL_REDIS_IN_DEV'    = 'true'
    'ALLOW_DEV_AUTH'            = 'true'
}
foreach ($key in $expected.Keys) {
    $match = [regex]::Match($envText, "(?m)^\s*$key\s*=\s*(.*?)\s*$")
    if (-not $match.Success) {
        Write-Warn "$key is not set in .env (expected $($expected[$key]))"
    }
    elseif ($match.Groups[1].Value -ne $expected[$key]) {
        Write-Warn "$key=$($match.Groups[1].Value) in .env, expected $($expected[$key])"
    }
}
if ($script:Warnings.Count -eq 0) { Write-Ok '.env local-first flags look right' }

# ---------------------------------------------------------------------------
# 2. Docker daemon
# ---------------------------------------------------------------------------

Write-Step 'Checking the Docker daemon'

function Test-DockerUp {
    return (Test-NativeOk 'docker' @('info', '--format', '{{.ServerVersion}}'))
}

if (Test-DockerUp) {
    Write-Ok 'daemon already running'
}
else {
    Write-Note 'daemon is down, starting Docker Desktop...'
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Docker\Docker\Docker Desktop.exe')
    )
    $exe = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $exe) {
        Stop-WithError 'Docker Desktop executable not found' 'Start Docker Desktop manually, then re-run.'
    }
    Start-Process $exe | Out-Null
    Write-Note 'waiting for the daemon (up to 120s)...'
    if (-not (Wait-Until { Test-DockerUp } 120 3)) {
        Stop-WithError 'Docker daemon did not come up within 120s' 'Check Docker Desktop, then re-run.'
    }
    Write-Ok 'daemon is up'
}

# ---------------------------------------------------------------------------
# 3. Postgres + Redis
# ---------------------------------------------------------------------------

Write-Step 'Starting Postgres + Redis'

Invoke-Native 'docker' @('compose', 'up', '-d', 'db', 'redis') $Backend 'docker compose up failed'

# `up -d` returns as soon as the containers start, which is well before Postgres
# accepts connections. Without this wait, `alembic upgrade head` fails on a cold
# boot but succeeds on a re-run -- the confusing kind of flake.
Push-Location $Backend
try {
    Write-Note 'waiting for Postgres to accept connections...'
    $pgReady = Wait-Until {
        Test-NativeOk 'docker' @('compose', 'exec', '-T', 'db', 'pg_isready', '-U', 'app', '-d', 'app')
    } 90 2
    if (-not $pgReady) { Stop-WithError 'Postgres did not become ready within 90s' 'Check: docker compose logs db' }
    Write-Ok 'Postgres accepting connections on 5432'

    Write-Note 'waiting for Redis...'
    $redisReady = Wait-Until {
        Test-NativeOk 'docker' @('compose', 'exec', '-T', 'redis', 'redis-cli', 'ping')
    } 60 2
    if (-not $redisReady) { Stop-WithError 'Redis did not become ready within 60s' 'Check: docker compose logs redis' }
    Write-Ok 'Redis responding on 6379'
}
finally { Pop-Location }

# ---------------------------------------------------------------------------
# 4. Dependencies
# ---------------------------------------------------------------------------

Write-Step 'Installing dependencies'

Write-Note 'pip install -r requirements.txt'
Invoke-Native 'python' @('-m', 'pip', 'install', '-q', '-r', 'requirements.txt') $Backend 'pip install failed'
Write-Ok 'backend dependencies installed'

Write-Note 'npm install'
Invoke-Native 'npm' @('install', '--no-fund', '--no-audit') $Web 'npm install failed'
Write-Ok 'web dependencies installed'

# ---------------------------------------------------------------------------
# 5. Migrations
# ---------------------------------------------------------------------------

Write-Step 'Applying database migrations'
Invoke-Native 'alembic' @('upgrade', 'head') $Backend 'alembic upgrade head failed' 'Check: docker compose logs db'
Write-Ok 'database at head'

# ---------------------------------------------------------------------------
# 6. Verification
# ---------------------------------------------------------------------------

if (-not $SkipTests) {
    Write-Step 'Verifying'

    # unittest writes its summary to stderr. In PS 5.1 an inline `2> file`
    # redirect still wraps native stderr in an ErrorRecord, which is fatal under
    # ErrorActionPreference = 'Stop'. Start-Process redirects at the OS level and
    # sidesteps that entirely.
    $testLog    = Join-Path $env:TEMP 'syzy_unittest.err.log'
    $testOutLog = Join-Path $env:TEMP 'syzy_unittest.out.log'

    $proc = Start-Process -FilePath 'python' `
        -ArgumentList '-m', 'unittest', 'discover', '-s', 'tests' `
        -WorkingDirectory $Backend -NoNewWindow -Wait -PassThru `
        -RedirectStandardError $testLog -RedirectStandardOutput $testOutLog
    $testExit = $proc.ExitCode

    $testOut = ''
    if (Test-Path $testLog) { $testOut = Get-Content $testLog -Raw }

    $ranMatch     = [regex]::Match($testOut, 'Ran (\d+) tests?')
    $skippedMatch = [regex]::Match($testOut, 'skipped=(\d+)')
    $ranCount     = 0
    $skipCount    = 0
    if ($ranMatch.Success)     { $ranCount  = [int]$ranMatch.Groups[1].Value }
    if ($skippedMatch.Success) { $skipCount = [int]$skippedMatch.Groups[1].Value }

    if ($testExit -ne 0) {
        Write-Host $testOut
        Stop-WithError 'backend unit tests failed' 'Fix the failures, or re-run with -SkipTests to bypass.'
    }

    # Postgres is up by this point, so a nonzero skip count means the db-backed
    # tests could not reach it -- a green run that verified less than it looks.
    if ($skipCount -gt 0) {
        Write-Warn "$ranCount tests passed but $skipCount skipped -- db-backed tests could not reach Postgres"
    }
    else {
        Write-Ok "$ranCount backend tests passed, 0 skipped"
    }

    Write-Note 'npx tsc --noEmit'
    Invoke-Native 'npx' @('tsc', '--noEmit') $Web 'TypeScript check failed'
    Write-Ok 'TypeScript clean'
}

# ---------------------------------------------------------------------------
# 7. Launch
# ---------------------------------------------------------------------------

if ($NoLaunch) {
    Write-Host ''
    Write-Host 'Provisioning complete (-NoLaunch).' -ForegroundColor Green
    Write-Host ''
    Write-Host 'To run the stack, open four terminals:' -ForegroundColor White
    Write-Host "  cd `"$Backend`"; uvicorn app.main:app --reload"
    Write-Host "  cd `"$Backend`"; celery -A app.workers.celery_app.celery worker --loglevel=INFO"
    Write-Host "  cd `"$Backend`"; celery -A app.workers.celery_app.celery beat --loglevel=INFO"
    Write-Host "  cd `"$Web`"; npm run dev"
    Write-Host ''
    exit 0
}

Write-Step 'Launching the stack'

$launched = @()

if (Test-PortListening $ApiPort) {
    Write-Warn "port $ApiPort already in use -- not starting uvicorn"
}
else {
    Start-StackWindow 'SYZY api' $Backend 'uvicorn app.main:app --reload'
    $launched += "api (port $ApiPort)"
}

# The worker only consumes tasks; beat is what enqueues the periodic reminder
# sweep and the daily share-link cleanup. Both are needed for the scheduled
# path to work at all.
#
# Neither binds a port, so unlike the api and web processes they can't be
# detected by a port check -- a naive re-run silently stacks up duplicates. A
# second beat is the harmful one: two schedulers both enqueue the periodic
# sweep. Skip both if any celery process is already alive.
$celeryRunning = @(Get-Process celery -ErrorAction SilentlyContinue)
if ($celeryRunning.Count -gt 0) {
    Write-Warn "$($celeryRunning.Count) celery process(es) already running -- not starting worker or beat"
}
else {
    Start-StackWindow 'SYZY worker' $Backend 'celery -A app.workers.celery_app.celery worker --loglevel=INFO'
    $launched += 'celery worker'

    Start-StackWindow 'SYZY beat' $Backend 'celery -A app.workers.celery_app.celery beat --loglevel=INFO'
    $launched += 'celery beat'
}

if (Test-PortListening $WebPort) {
    Write-Warn "port $WebPort already in use -- not starting next dev"
}
else {
    Start-StackWindow 'SYZY web' $Web 'npm run dev'
    $launched += "web (port $WebPort)"
}

foreach ($item in $launched) { Write-Ok "started $item" }

# ---------------------------------------------------------------------------
# 8. Health checks
# ---------------------------------------------------------------------------

Write-Step 'Waiting for health checks'

$apiUrl = "http://127.0.0.1:$ApiPort/health"
$webUrl = "http://localhost:$WebPort"

Write-Note "polling $apiUrl"
if (Wait-Until { Test-Url $apiUrl } 90 2) { Write-Ok 'api healthy' }
else { Write-Warn "api did not respond at $apiUrl -- check the 'SYZY api' window" }

Write-Note "polling $webUrl (first compile can take ~30s)"
if (Wait-Until { Test-Url $webUrl } 120 3) { Write-Ok 'web app responding' }
else { Write-Warn "web app did not respond at $webUrl -- check the 'SYZY web' window" }

# ---------------------------------------------------------------------------
# Optional: full e2e
# ---------------------------------------------------------------------------

if ($FullTest) {
    Write-Host ''
    Write-Host 'Running the Playwright suite (~2 min)...' -ForegroundColor Cyan
    Write-Note 'Playwright boots its own dev server on port 3100'
    Push-Location $Web
    try {
        npx playwright test
        if ($LASTEXITCODE -ne 0) { Write-Warn 'Playwright suite reported failures' }
        else { Write-Ok 'Playwright suite passed' }
    }
    finally { Pop-Location }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host ''
Write-Host ('-' * 60) -ForegroundColor DarkGray
Write-Host 'Stack is up.' -ForegroundColor Green
Write-Host ''
Write-Host "  Web app     $webUrl"
Write-Host "  API         http://127.0.0.1:$ApiPort"
Write-Host "  API health  $apiUrl"
Write-Host "  Outbox      $(Join-Path $Backend 'dev_outbox')"
Write-Host ''
Write-Host "  Smoke test  cd `"$Backend`"; python scripts/test_reminder_flow.py"
Write-Host "  E2E suite   cd `"$Web`"; npm run test:e2e"
Write-Host ''
Write-Host '  Stop        close the SYZY api / worker / beat / web windows'
Write-Host "              docker compose -f `"$(Join-Path $Backend 'docker-compose.yml')`" stop"

if ($script:Warnings.Count -gt 0) {
    Write-Host ''
    Write-Host "$($script:Warnings.Count) warning(s):" -ForegroundColor Yellow
    foreach ($w in $script:Warnings) { Write-Host "  - $w" -ForegroundColor Yellow }
}

Write-Host ''
