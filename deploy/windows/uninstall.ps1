<#
.SYNOPSIS
RetailAI Agent Windows Service Uninstaller.

.DESCRIPTION
This script safely stops and removes the RetailAI Agent Windows Services.
#>

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..") | Select-Object -ExpandProperty Path
$NssmExe = Join-Path $ProjectRoot "tools\nssm\win64\nssm.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " RetailAI Agent Uninstaller" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Remove-Svc {
    param([string]$ServiceName)
    
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "Stopping $ServiceName..." -ForegroundColor Yellow
        Stop-Service -Name $ServiceName -Force
        
        Write-Host "Removing $ServiceName..." -ForegroundColor Yellow
        if (Test-Path $NssmExe) {
            & $NssmExe remove $ServiceName confirm
        } else {
            sc.exe delete $ServiceName
        }
        Write-Host "$ServiceName removed successfully.`n" -ForegroundColor Green
    } else {
        Write-Host "Service $ServiceName not found. Skipping.`n" -ForegroundColor Gray
    }
}

Remove-Svc -ServiceName "RetailAI_Frontend"
Remove-Svc -ServiceName "RetailAI_Backend"
Remove-Svc -ServiceName "RetailAI_MediaMTX"

Write-Host "Uninstallation Complete." -ForegroundColor Green
Write-Host "Note: Project files, database, and virtual environments were NOT deleted." -ForegroundColor Gray
