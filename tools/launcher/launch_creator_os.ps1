[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$SuccessMark = [char]0x2713

# Centralized launcher configuration.
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$BackendPort = 8001
$FrontendPort = 5174
$BackendHealthUrl = "http://127.0.0.1:$BackendPort/openapi.json"
$FrontendHealthUrl = "http://127.0.0.1:$FrontendPort/"
$FrontendUrl = "http://127.0.0.1:$FrontendPort/"
$BackendCommand = "python.exe"
$BackendArguments = @("-m", "uvicorn", "app.fanvue_callback_server:app", "--app-dir", $ProjectRoot, "--port", "$BackendPort")
$FrontendCommand = "npm.cmd"
$FrontendArguments = @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort")
$ProcessStopTimeoutSeconds = 20
$BackendStartupTimeoutSeconds = 60
$FrontendStartupTimeoutSeconds = 90

$LogDirectory = Join-Path $ProjectRoot "logs\runtime"
$BackendOutputLog = Join-Path $LogDirectory "fastapi.log"
$BackendErrorLog = Join-Path $LogDirectory "fastapi_error.log"
$FrontendOutputLog = Join-Path $LogDirectory "react.log"
$FrontendErrorLog = Join-Path $LogDirectory "react_error.log"
$LauncherLog = Join-Path $LogDirectory "launcher.log"
$LauncherFailureLog = Join-Path $LogDirectory "launcher_failure.txt"
$ServiceStatePath = Join-Path $LogDirectory "launcher_services.json"
$Session5CertificationConfigPath = Join-Path $ProjectRoot ".env.session5.local"
$WorkerSupervisorModule = "tools.launcher.worker_supervisor"
$DesktopShortcutHelper = Join-Path $PSScriptRoot "create_desktop_shortcut.ps1"
$script:CurrentStep = "initialization"

# Optional, local-only Session 5 certification environment. The marker file is
# gitignored and deliberately contains only non-secret mode/database-name
# settings. Each test connection reuses the local DATABASE_URL credentials while
# replacing only its database name; durable purpose markers plus the existing
# test-database guard remain authoritative and fail closed.
if (Test-Path -LiteralPath $Session5CertificationConfigPath) {
    $session5Config = @{}
    foreach ($line in Get-Content -LiteralPath $Session5CertificationConfigPath) {
        if ($line -match '^\s*(?<name>[A-Z0-9_]+)\s*=\s*(?<value>.*?)\s*$') {
            $session5Config[$Matches.name] = $Matches.value.Trim('"').Trim("'")
        }
    }
    if ($session5Config["CREATOR_OS_CERTIFICATION_SCENARIO_MODE"] -match '^(?i:true)$') {
        $session5Databases = @{
            "SESSION5_SCENARIO_LAB_DATABASE_URL" = [string]$session5Config["CREATOR_OS_SCENARIO_LAB_DATABASE_NAME"]
            "SESSION5_INTEGRATION_DATABASE_URL" = [string]$session5Config["CREATOR_OS_INTEGRATION_TEST_DATABASE_NAME"]
            "SESSION5_RECOVERY_DATABASE_URL" = [string]$session5Config["CREATOR_OS_RECOVERY_TEST_DATABASE_NAME"]
        }
        $databaseLine = Get-Content -LiteralPath (Join-Path $ProjectRoot ".env") |
            Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } |
            Select-Object -Last 1
        if ([string]::IsNullOrWhiteSpace($databaseLine)) {
            throw "DATABASE_URL is required to derive the local Session 5 test connection."
        }
        $productionDatabaseUrl = (($databaseLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
        foreach ($entry in $session5Databases.GetEnumerator()) {
            $testDatabaseName = $entry.Value
            if ($testDatabaseName -notmatch '^(?i:[a-z0-9_]*test[a-z0-9_]*)$') {
                throw "Every Session 5 database name must be explicitly test-scoped."
            }
            if ($productionDatabaseUrl -match '(?<prefix>[?&]dbname=)[^&]*') {
                $testDatabaseUrl = [regex]::Replace(
                    $productionDatabaseUrl, '(?<prefix>[?&]dbname=)[^&]*',
                    "`${prefix}$testDatabaseName", 1
                )
            } else {
                $testDatabaseUrl = [regex]::Replace(
                    $productionDatabaseUrl, '/[^/?]+(?<query>\?.*)?$',
                    "/$testDatabaseName`${query}"
                )
            }
            if ($testDatabaseUrl -eq $productionDatabaseUrl) {
                throw "Session 5 database derivation must differ from production."
            }
            [Environment]::SetEnvironmentVariable($entry.Key, $testDatabaseUrl, "Process")
        }
        [Environment]::SetEnvironmentVariable("CREATOR_OS_CERTIFICATION_SCENARIO_MODE", "true", "Process")
    }
}

# This launcher is the canonical local-development entry point. Direct
# production/runtime module launches remain non-reloading by default.
$DevAutoReloadSwitch = "CREATOR_OS_DEV_AUTO_RELOAD"
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($DevAutoReloadSwitch))) {
    [Environment]::SetEnvironmentVariable($DevAutoReloadSwitch, "true", "Process")
}
$DevAutoReloadEnabled = [Environment]::GetEnvironmentVariable($DevAutoReloadSwitch) -match '^(?i:1|true|yes|on)$'
if ($DevAutoReloadEnabled) {
    $BackendArguments += @("--reload", "--reload-dir", (Join-Path $ProjectRoot "app"), "--reload-delay", "1")
}

# Core Business Asset analysis is part of the Creator_OS application lifecycle,
# not optional automation. Explicit user environment values still win.
foreach ($workerSwitch in @(
    "CREATOR_OS_LAUNCH_BACKGROUND_OPERATIONS",
    "CREATOR_OS_LAUNCH_ANALYSIS_ORCHESTRATOR",
    "CREATOR_OS_LAUNCH_NUDENET_ANALYSIS",
    "CREATOR_OS_LAUNCH_VISION_ANALYSIS",
    "CREATOR_OS_LAUNCH_GROK_ANALYSIS",
    "CREATOR_OS_LAUNCH_CONTENT_INTELLIGENCE_MERGE",
    "CREATOR_OS_LAUNCH_PHOTOSHOOT_ANALYSIS",
    "CREATOR_OS_LAUNCH_PHOTOSHOOT_AUTO_RUN",
    "CREATOR_OS_LAUNCH_X_COMPETITOR_REFRESH"
)) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($workerSwitch))) {
        [Environment]::SetEnvironmentVariable($workerSwitch, "true", "Process")
    }
}

function Write-LauncherEvent {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet("INFO", "ERROR")][string]$Level = "INFO"
    )
    $line = "[$([DateTime]::UtcNow.ToString('o'))] [$Level] [$($script:CurrentStep)] $Message"
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Set-LauncherStep {
    param([Parameter(Mandatory)][string]$Name)
    $script:CurrentStep = $Name
    Write-LauncherEvent -Message "Starting step."
}

function Format-LaunchCommand {
    param([string]$Command, [string[]]$Arguments)
    return "$Command $($Arguments -join ' ')"
}

function Save-ServiceState {
    param([string]$Name, [int[]]$ProcessIds, [string]$CommandLine)
    $state = @{}
    if (Test-Path -LiteralPath $ServiceStatePath) {
        try {
            $savedState = Get-Content -LiteralPath $ServiceStatePath -Raw | ConvertFrom-Json
            foreach ($property in $savedState.PSObject.Properties) {
                $state[$property.Name] = $property.Value
            }
        } catch { $state = @{} }
    }
    $state[$Name] = @{
        processIds = @($ProcessIds)
        command = $CommandLine
        projectRoot = $ProjectRoot
        recordedAt = [DateTime]::UtcNow.ToString("o")
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ServiceStatePath -Encoding UTF8
}

function Test-CreatorOsProcess {
    param(
        [Parameter(Mandatory)][int[]]$ProcessIds,
        [Parameter(Mandatory)][ValidateSet("Backend", "Frontend")][string]$ServiceType
    )
    $savedIds = @()
    if (Test-Path -LiteralPath $ServiceStatePath) {
        try {
            $state = Get-Content -LiteralPath $ServiceStatePath -Raw | ConvertFrom-Json
            $saved = $state.PSObject.Properties[$ServiceType].Value
            if ($saved.projectRoot -eq $ProjectRoot) { $savedIds = @($saved.processIds) }
        } catch {}
    }
    foreach ($processId in $ProcessIds) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($null -eq $process) { return $false }
        $commandLine = [string]$process.CommandLine
        if ($ServiceType -eq "Backend") {
            $signatureMatches = $commandLine -match 'uvicorn\s+app\.fanvue_callback_server:app' -and
                $commandLine -match "--port\s+$BackendPort" -and
                ($commandLine -match [regex]::Escape($ProjectRoot) -or $savedIds -contains $processId)
        } else {
            $signatureMatches = $commandLine -match 'vite' -and
                $commandLine -match "--port\s+$FrontendPort" -and
                $commandLine -match [regex]::Escape($FrontendRoot)
        }
        if (-not $signatureMatches) { return $false }
    }
    return $ProcessIds.Count -gt 0
}

function Test-CreatorOsReady {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][ValidateSet("Backend", "Frontend")][string]$ServiceType
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            return $false
        }
        if ($ServiceType -eq "Frontend") {
            return $response.Content -match '<title>Creator_OS</title>' -and
                $response.Content -match 'Creator_OS React interface foundation'
        }

        $payload = $response.Content | ConvertFrom-Json
        $paths = @($payload.paths.PSObject.Properties.Name)
        return $payload.info.title -eq "FastAPI" -and
            $paths -contains "/api/v1/content-studio/context" -and
            $paths -contains "/api/v1/operations/workers"
    }
    catch {
        return $false
    }
}

function Test-PortListening {
    param([Parameter(Mandatory)][int]$Port)

    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][ValidateSet("Backend", "Frontend")][string]$ServiceType,
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][int]$TimeoutSeconds,
        [System.Diagnostics.Process]$Process
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-CreatorOsReady -Url $Url -ServiceType $ServiceType) {
            return $true
        }
        if ($null -ne $Process -and $Process.HasExited) {
            throw "$Name exited before it became ready (exit code $($Process.ExitCode))."
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-ListeningProcessIds {
    param([Parameter(Mandatory)][int]$Port)

    return @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Get-ProcessTreeIds {
    param([Parameter(Mandatory)][int[]]$RootProcessIds)

    $processes = @(Get-CimInstance Win32_Process)
    $selected = [System.Collections.Generic.HashSet[int]]::new()
    $pending = [System.Collections.Generic.Queue[int]]::new()
    foreach ($processId in $RootProcessIds) {
        if ($selected.Add($processId)) {
            $pending.Enqueue($processId)
        }
    }
    while ($pending.Count -gt 0) {
        $parentId = $pending.Dequeue()
        foreach ($child in $processes | Where-Object { $_.ParentProcessId -eq $parentId }) {
            if ($selected.Add([int]$child.ProcessId)) {
                $pending.Enqueue([int]$child.ProcessId)
            }
        }
    }
    return @($selected)
}

function Stop-CreatorService {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][ValidateSet("Backend", "Frontend")][string]$ServiceType,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$HealthUrl,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    $listenerIds = @(Get-ListeningProcessIds -Port $Port)
    if ($listenerIds.Count -eq 0) {
        Write-Host "$Name is not running."
        return @()
    }
    if (-not (Test-CreatorOsReady -Url $HealthUrl -ServiceType $ServiceType)) {
        if (-not (Test-CreatorOsProcess -ProcessIds $listenerIds -ServiceType $ServiceType)) {
            throw "Port $Port is occupied by another application or an unverified process; it is not a valid Creator_OS $Name service. The process was not stopped."
        }
        Write-LauncherEvent -Message "$Name health check failed, but listener PID(s) $($listenerIds -join ', ') match the recorded $ProjectRoot Creator_OS command. Recovering by restarting only those processes."
    }

    Write-Host "Stopping $Name..."
    $processTreeIds = @(Get-ProcessTreeIds -RootProcessIds $listenerIds)
    foreach ($processId in $processTreeIds | Sort-Object -Descending) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $remainingProcesses = @(
            $processTreeIds | Where-Object {
                $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue)
            }
        )
        if ($remainingProcesses.Count -eq 0 -and -not (Test-PortListening -Port $Port)) {
            Write-Host "$SuccessMark $Name stopped" -ForegroundColor Green
            return $listenerIds
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$Name did not fully stop within $TimeoutSeconds seconds."
}

function Start-CreatorService {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][ValidateSet("Backend", "Frontend")][string]$ServiceType,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$HealthUrl,
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][int]$StartupTimeoutSeconds,
        [Parameter(Mandatory)][string]$OutputLog,
        [Parameter(Mandatory)][string]$ErrorLog
    )

    if (Test-PortListening -Port $Port) {
        throw "Port $Port is still occupied after the Creator_OS restart stop phase. No duplicate process was started."
    }

    $resolvedCommand = Get-Command $Command -ErrorAction SilentlyContinue
    if ($null -eq $resolvedCommand) {
        throw "Required command '$Command' was not found. Install the project prerequisites and try again."
    }

    $commandDisplay = Format-LaunchCommand -Command $resolvedCommand.Source -Arguments $Arguments
    Write-LauncherEvent -Message "Command: $commandDisplay; working directory: $WorkingDirectory"
    Write-Host "Starting $Name..."
    $process = Start-Process `
        -FilePath $resolvedCommand.Source `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -PassThru

    if (-not (Wait-ForHttp -Name $Name -ServiceType $ServiceType -Url $HealthUrl -TimeoutSeconds $StartupTimeoutSeconds -Process $process)) {
        throw "$Name did not respond within $StartupTimeoutSeconds seconds. Review '$ErrorLog'."
    }
    Write-Host "$SuccessMark $Name running" -ForegroundColor Green
    $listenerIds = @(Get-ListeningProcessIds -Port $Port)
    Save-ServiceState -Name $ServiceType -ProcessIds $listenerIds -CommandLine $commandDisplay
    return $listenerIds
}

function Invoke-WorkerSupervisor {
    param([Parameter(Mandatory)][ValidateSet("start-enabled", "stop-managed", "monitor-telegram")][string]$Action)

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "Python is required for worker supervision."
    }
    $commandDisplay = "$($python.Source) -m $WorkerSupervisorModule $Action"
    Write-LauncherEvent -Message "Command: $commandDisplay; working directory: $ProjectRoot"
    if ($Action -eq "monitor-telegram") {
        Start-Process -FilePath $python.Source -ArgumentList @("-m", $WorkerSupervisorModule, $Action) `
            -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $LogDirectory "telegram_supervisor.log") `
            -RedirectStandardError (Join-Path $LogDirectory "telegram_supervisor_error.log") | Out-Null
        return
    }
    $output = & $python.Source -m $WorkerSupervisorModule $Action 2>&1
    $output | ForEach-Object { Write-LauncherEvent -Message ([string]$_) }
    if ($LASTEXITCODE -ne 0) {
        throw "Worker supervision action '$Action' failed. Review '$LauncherLog'."
    }
}

function Wait-ForFastApiHeartbeat {
    param([int]$TimeoutSeconds = 60)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/v1/operations/workers" -TimeoutSec 3
            $fastApi = @($response.items | Where-Object { $_.name -eq "FastAPI" }) | Select-Object -First 1
            if ($null -ne $fastApi -and $fastApi.heartbeatAvailable -eq $true -and
                $fastApi.heartbeatStatus -in @("healthy", "idle")) {
                Write-Host "$SuccessMark FastAPI heartbeat healthy" -ForegroundColor Green
                return
            }
        }
        catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "FastAPI HTTP became ready but its persisted heartbeat did not become healthy within $TimeoutSeconds seconds."
}

$launcherMutex = [Threading.Mutex]::new($false, "Global\Creator_OS_React_Launcher")
$mutexAcquired = $false
try {
    $mutexAcquired = $launcherMutex.WaitOne(1000)
    if (-not $mutexAcquired) {
        throw "Another Creator_OS launch is already in progress. Wait for it to finish before launching again."
    }
    Write-Host "Starting Creator_OS..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    Remove-Item -LiteralPath $LauncherFailureLog -Force -ErrorAction SilentlyContinue
    Write-LauncherEvent -Message "Creator_OS restart requested from $ProjectRoot."
    Write-LauncherEvent -Message "Development auto-reload enabled=$DevAutoReloadEnabled switch=$DevAutoReloadSwitch"

    Set-LauncherStep -Name "desktop-shortcut"
    try {
        & $DesktopShortcutHelper -ProjectRoot $ProjectRoot
    }
    catch {
        Write-Host "Desktop shortcut could not be created: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    Set-LauncherStep -Name "stop-workers"
    Invoke-WorkerSupervisor -Action "stop-managed"

    Set-LauncherStep -Name "stop-frontend"
    $previousFrontendIds = @(Stop-CreatorService `
        -Name "React" `
        -ServiceType "Frontend" `
        -Port $FrontendPort `
        -HealthUrl $FrontendHealthUrl `
        -TimeoutSeconds $ProcessStopTimeoutSeconds)

    Set-LauncherStep -Name "stop-backend"
    $previousBackendIds = @(Stop-CreatorService `
        -Name "Backend" `
        -ServiceType "Backend" `
        -Port $BackendPort `
        -HealthUrl $BackendHealthUrl `
        -TimeoutSeconds $ProcessStopTimeoutSeconds)

    Set-LauncherStep -Name "start-backend"
    $backendIds = @(Start-CreatorService `
        -Name "Backend" `
        -ServiceType "Backend" `
        -Port $BackendPort `
        -HealthUrl $BackendHealthUrl `
        -Command $BackendCommand `
        -Arguments $BackendArguments `
        -WorkingDirectory $ProjectRoot `
        -StartupTimeoutSeconds $BackendStartupTimeoutSeconds `
        -OutputLog $BackendOutputLog `
        -ErrorLog $BackendErrorLog)
    if ($previousBackendIds.Count -gt 0 -and @($backendIds | Where-Object { $previousBackendIds -contains $_ }).Count -gt 0) {
        throw "Backend restart reused a previous listener PID unexpectedly."
    }

    Set-LauncherStep -Name "backend-heartbeat"
    Wait-ForFastApiHeartbeat -TimeoutSeconds $BackendStartupTimeoutSeconds
    Set-LauncherStep -Name "start-workers"
    Invoke-WorkerSupervisor -Action "start-enabled"
    Invoke-WorkerSupervisor -Action "monitor-telegram"

    Set-LauncherStep -Name "start-frontend"
    $frontendIds = @(Start-CreatorService `
        -Name "React" `
        -ServiceType "Frontend" `
        -Port $FrontendPort `
        -HealthUrl $FrontendHealthUrl `
        -Command $FrontendCommand `
        -Arguments $FrontendArguments `
        -WorkingDirectory $FrontendRoot `
        -StartupTimeoutSeconds $FrontendStartupTimeoutSeconds `
        -OutputLog $FrontendOutputLog `
        -ErrorLog $FrontendErrorLog)
    if ($previousFrontendIds.Count -gt 0 -and @($frontendIds | Where-Object { $previousFrontendIds -contains $_ }).Count -gt 0) {
        throw "React restart reused a previous listener PID unexpectedly."
    }

    Set-LauncherStep -Name "open-browser"
    Write-LauncherEvent -Message "Command: Start-Process $FrontendUrl"
    Start-Process $FrontendUrl
    Write-LauncherEvent -Message "Creator_OS launch completed successfully."
    Write-Host "Done." -ForegroundColor Green
    exit 0
}
catch {
    $failure = "Creator_OS failed during '$($script:CurrentStep)': $($_.Exception.Message)`r`n$($_.ScriptStackTrace)"
    try {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        Write-LauncherEvent -Message $failure -Level "ERROR"
        Set-Content -LiteralPath $LauncherFailureLog -Value $failure -Encoding UTF8
    } catch {}
    Write-Host ""
    Write-Host $failure -ForegroundColor Red
    Write-Host "Launcher logs are stored in '$LogDirectory'." -ForegroundColor Yellow
    exit 1
}
finally {
    if ($mutexAcquired) { $launcherMutex.ReleaseMutex() }
    $launcherMutex.Dispose()
}
