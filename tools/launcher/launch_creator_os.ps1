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
$BackendHealthUrl = "http://127.0.0.1:$BackendPort/api/v1/content-studio/context"
$FrontendHealthUrl = "http://127.0.0.1:$FrontendPort/"
$FrontendUrl = "http://127.0.0.1:$FrontendPort/"
$BackendCommand = "python.exe"
$BackendArguments = @("-m", "uvicorn", "app.fanvue_callback_server:app", "--port", "$BackendPort")
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
$WorkerSupervisorModule = "tools.launcher.worker_supervisor"
$DesktopShortcutHelper = Join-Path $PSScriptRoot "create_desktop_shortcut.ps1"

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
        $properties = @($payload.PSObject.Properties.Name)
        return $payload.success -eq $true -and
            $properties -contains "creatorProfileExists" -and
            $properties -contains "activeReferenceExists" -and
            $properties -contains "activeReferenceAssetId"
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
        throw "Port $Port is occupied by another application or an unhealthy process; it is not a valid Creator_OS $Name service. The process was not stopped."
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
    return @(Get-ListeningProcessIds -Port $Port)
}

function Invoke-WorkerSupervisor {
    param([Parameter(Mandatory)][ValidateSet("start-enabled", "stop-managed")][string]$Action)

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "Python is required for worker supervision."
    }
    $output = & $python.Source -m $WorkerSupervisorModule $Action 2>&1
    $output | Tee-Object -FilePath $LauncherLog -Append | ForEach-Object { Write-Host $_ }
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

try {
    Write-Host "Starting Creator_OS..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    Add-Content -Path $LauncherLog -Value "[$([DateTime]::UtcNow.ToString('o'))] Creator_OS restart requested."

    try {
        & $DesktopShortcutHelper -ProjectRoot $ProjectRoot
    }
    catch {
        Write-Host "Desktop shortcut could not be created: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    Invoke-WorkerSupervisor -Action "stop-managed"

    $previousFrontendIds = @(Stop-CreatorService `
        -Name "React" `
        -ServiceType "Frontend" `
        -Port $FrontendPort `
        -HealthUrl $FrontendHealthUrl `
        -TimeoutSeconds $ProcessStopTimeoutSeconds)

    $previousBackendIds = @(Stop-CreatorService `
        -Name "Backend" `
        -ServiceType "Backend" `
        -Port $BackendPort `
        -HealthUrl $BackendHealthUrl `
        -TimeoutSeconds $ProcessStopTimeoutSeconds)

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

    Wait-ForFastApiHeartbeat -TimeoutSeconds $BackendStartupTimeoutSeconds
    Invoke-WorkerSupervisor -Action "start-enabled"

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

    Write-Host "Opening browser..."
    Start-Process $FrontendUrl
    Write-Host "Done." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Creator_OS failed to start: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Launcher logs are stored in '$LogDirectory'." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
