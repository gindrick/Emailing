# Register Email Assistant Task in Windows Task Scheduler
# Run this script as Administrator

$ErrorActionPreference = "Stop"

# Task configuration
$taskName = "EmailAssistant_PDF_Processor"
$taskDescription = "Processes PDFs from SharePoint and sends emails with customer mapping"
$scriptPath = "C:\jj\emailAssistant\run_email_assistant.ps1"
$workingDir = "C:\jj\emailAssistant"

Write-Host "=========================================="
Write-Host "Registering Task Scheduler for Email Assistant"
Write-Host "=========================================="
Write-Host "Task Name: $taskName"
Write-Host "Script: $scriptPath"
Write-Host ""

# Check admin rights
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script MUST be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click and select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Launcher script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "Admin rights OK" -ForegroundColor Green
Write-Host "Launcher script found" -ForegroundColor Green
Write-Host ""

# Remove existing task (if exists)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task '$taskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Existing task removed" -ForegroundColor Green
}

# Create Action
$action = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $workingDir

# Create Trigger
Write-Host ""
Write-Host "Select trigger schedule:" -ForegroundColor Cyan
Write-Host "1) Manual (only manual start)"
Write-Host "2) Daily at 8:00"
Write-Host "3) Every hour"
Write-Host "4) Every 4 hours"
Write-Host ""
$choice = Read-Host "Select (1-4)"

switch ($choice) {
    "1" {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddYears(10)
        $triggerDescription = "Manual only"
    }
    "2" {
        $trigger = New-ScheduledTaskTrigger -Daily -At "08:00"
        $triggerDescription = "Daily at 8:00"
    }
    "3" {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
        $triggerDescription = "Every hour"
    }
    "4" {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 4) -RepetitionDuration ([TimeSpan]::MaxValue)
        $triggerDescription = "Every 4 hours"
    }
    default {
        Write-Host "Invalid choice, using Manual" -ForegroundColor Yellow
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddYears(10)
        $triggerDescription = "Manual only"
    }
}

# Create Principal (which user account)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

# Create Settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Register task
Write-Host ""
Write-Host "Registering task..." -ForegroundColor Cyan
Register-ScheduledTask `
    -TaskName $taskName `
    -Description $taskDescription `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host ""
Write-Host "=========================================="
Write-Host "SUCCESSFULLY REGISTERED" -ForegroundColor Green
Write-Host "=========================================="
Write-Host ""
Write-Host "Task Name:    $taskName" -ForegroundColor Cyan
Write-Host "Schedule:     $triggerDescription" -ForegroundColor Cyan
Write-Host "Script:       $scriptPath" -ForegroundColor Cyan
Write-Host "Working Dir:  $workingDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "How to run the task:" -ForegroundColor Yellow
Write-Host "  1) Manually in Task Scheduler UI (taskschd.msc)"
Write-Host "  2) PowerShell: Start-ScheduledTask -TaskName '$taskName'"
Write-Host "  3) CMD: schtasks /Run /TN `"$taskName`""
Write-Host ""
Write-Host "How to disable/edit task:" -ForegroundColor Yellow
Write-Host "  - Open Task Scheduler (Win+R -> taskschd.msc)"
Write-Host "  - Find '$taskName' in Task Scheduler Library"
Write-Host "  - Right-click -> Properties to edit"
Write-Host "  - Right-click -> Disable to turn off"
Write-Host ""
Write-Host "Logs location: C:\jj\emailAssistant\logs\" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
