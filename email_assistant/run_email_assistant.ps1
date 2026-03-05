# Email Assistant - Automated PDF Processing and Sending
# Spusti celou aplikaci s logovanim

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = $scriptDir
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $projectRoot "logs"
$logFile = Join-Path $logDir "run_$timestamp.log"

# Vytvor log slozku
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message)
    $timeStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timeStamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $logFile -Value $logMessage
}

Write-Log "=========================================="
Write-Log "Email Assistant START"
Write-Log "=========================================="
Write-Log "Project root: $projectRoot"
Write-Log "Log file: $logFile"

try {
    # Kontrola .env
    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path $envFile)) {
        Write-Log "ERROR: .env soubor nenalezen: $envFile"
        exit 1
    }
    Write-Log "Config file: $envFile"

    # Kontrola Python virtualenv (preferuj lokalni .venv v projektu)
    $pythonCandidates = @(
        (Join-Path $projectRoot ".venv\Scripts\python.exe"),
        "C:\jj\.venv\Scripts\python.exe"
    )
    $pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $pythonExe) {
        Write-Log "ERROR: Python virtualenv nenalezen. Zkousene cesty: $($pythonCandidates -join ', ')"
        exit 1
    }
    Write-Log "Python executable: $pythonExe"

    # Kontrola main.py
    $mainScript = Join-Path $projectRoot "main.py"
    if (-not (Test-Path $mainScript)) {
        Write-Log "ERROR: main.py nenalezen: $mainScript"
        exit 1
    }
    Write-Log "Main script: $mainScript"

    # Spust aplikaci
    Write-Log "Spoustim email processing..."
    Push-Location $projectRoot
    try {
        $output = & $pythonExe $mainScript 2>&1
        $exitCode = $LASTEXITCODE
        
        # Zapis vystup do logu
        $output | ForEach-Object { Write-Log $_ }
        
        if ($exitCode -eq 0) {
            Write-Log "Email processing USPESNE dokoncen (exit code: $exitCode)"
        } else {
            Write-Log "Email processing skoncil s chybou (exit code: $exitCode)"
        }
        
        Write-Log "=========================================="
        Write-Log "Email Assistant END"
        Write-Log "=========================================="
        
        Pop-Location
        exit $exitCode
    }
    catch {
        Pop-Location
        throw
    }
}
catch {
    Write-Log "FATAL ERROR: $($_.Exception.Message)"
    Write-Log "StackTrace: $($_.ScriptStackTrace)"
    Write-Log "=========================================="
    Write-Log "Email Assistant FAILED"
    Write-Log "=========================================="
    exit 1
}
