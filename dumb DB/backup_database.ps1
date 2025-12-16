# Script for creating PostgreSQL database backup
# Settings loaded from settings.txt

param(
    [string]$SourceHost = "",
    [string]$Database = "",
    [string]$Port = "",
    [string]$Username = "",
    [string]$BackupPath = ".\backups",
    [string]$BackupFile = "",
    [string]$SettingsFile = "settings.txt"
)

# Load settings from file
. .\load_settings.ps1
$settings = Load-Settings -SettingsFile $SettingsFile

if ($null -eq $settings) {
    Write-Host "Error loading settings!" -ForegroundColor Red
    exit 1
}

# Use settings from file if parameters not specified
if ([string]::IsNullOrEmpty($SourceHost)) { $SourceHost = $settings["DB_HOST139"] }
if ([string]::IsNullOrEmpty($Database)) { $Database = $settings["DB_NAME"] }
if ([string]::IsNullOrEmpty($Port)) { $Port = $settings["DB_PORT"] }
if ([string]::IsNullOrEmpty($Username)) { $Username = $settings["DB_USER"] }
$Password = $settings["DB_PASSWORD"]

# Create backup directory if it doesn't exist
if (-not (Test-Path $BackupPath)) {
    New-Item -ItemType Directory -Path $BackupPath | Out-Null
    Write-Host "Created backup directory: $BackupPath" -ForegroundColor Green
}

# Generate filename with timestamp if not specified
if ([string]::IsNullOrEmpty($BackupFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $BackupFile = "$BackupPath\equipment_backup_$timestamp.sql"
}

Write-Host "Starting backup creation..." -ForegroundColor Yellow
Write-Host "Server: $SourceHost" -ForegroundColor Cyan
Write-Host "Database: $Database" -ForegroundColor Cyan
Write-Host "Backup file: $BackupFile" -ForegroundColor Cyan

# Set password environment variable
$env:PGPASSWORD = $Password

# Find PostgreSQL bin directory
$pgBinPath = "C:\Program Files\PostgreSQL\17\bin"
if (-not (Test-Path "$pgBinPath\pg_dump.exe")) {
    # Try to find in common locations
    $pgPaths = @(
        "C:\Program Files\PostgreSQL\17\bin",
        "C:\Program Files\PostgreSQL\16\bin",
        "C:\Program Files\PostgreSQL\15\bin",
        "C:\Program Files\PostgreSQL\14\bin"
    )
    foreach ($path in $pgPaths) {
        if (Test-Path "$path\pg_dump.exe") {
            $pgBinPath = $path
            break
        }
    }
}

$pgDumpExe = "$pgBinPath\pg_dump.exe"
if (-not (Test-Path $pgDumpExe)) {
    Write-Host "Error: pg_dump.exe not found!" -ForegroundColor Red
    Write-Host "Please install PostgreSQL or add it to PATH" -ForegroundColor Yellow
    exit 1
}

try {
    # Create backup using pg_dump
    # Use plain SQL format for universality
    $pgDumpArgs = @(
        "-h", $SourceHost,
        "-p", $Port,
        "-U", $Username,
        "-d", $Database,
        "-F", "p",
        "-f", $BackupFile,
        "-v",
        "--clean",
        "--if-exists"
    )
    
    & $pgDumpExe $pgDumpArgs
    
    if ($LASTEXITCODE -eq 0) {
        $fileSize = (Get-Item $BackupFile).Length / 1MB
        Write-Host ""
        Write-Host "Backup created successfully!" -ForegroundColor Green
        Write-Host "File size: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Green
        Write-Host "Path: $BackupFile" -ForegroundColor Green
        return $BackupFile
    } else {
        Write-Host ""
        Write-Host "Error creating backup!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
} finally {
    # Clear environment variable
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
