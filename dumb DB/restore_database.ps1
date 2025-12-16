# Script for restoring PostgreSQL database from backup
# Settings loaded from settings.txt

param(
    [string]$TargetHost = "",
    [string]$Database = "",
    [string]$Port = "",
    [string]$Username = "",
    [string]$BackupFile = "",
    [switch]$CreateDatabase,
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
if ([string]::IsNullOrEmpty($TargetHost)) { $TargetHost = $settings["DB_HOST22"] }
if ([string]::IsNullOrEmpty($Database)) { $Database = $settings["DB_NAME"] }
if ([string]::IsNullOrEmpty($Port)) { $Port = $settings["DB_PORT"] }
if ([string]::IsNullOrEmpty($Username)) { $Username = $settings["DB_USER"] }
$Password = $settings["DB_PASSWORD"]

# Find PostgreSQL bin directory
$pgBinPath = "C:\Program Files\PostgreSQL\17\bin"
if (-not (Test-Path "$pgBinPath\psql.exe")) {
    # Try to find in common locations
    $pgPaths = @(
        "C:\Program Files\PostgreSQL\17\bin",
        "C:\Program Files\PostgreSQL\16\bin",
        "C:\Program Files\PostgreSQL\15\bin",
        "C:\Program Files\PostgreSQL\14\bin"
    )
    foreach ($path in $pgPaths) {
        if (Test-Path "$path\psql.exe") {
            $pgBinPath = $path
            break
        }
    }
}

$psqlExe = "$pgBinPath\psql.exe"
if (-not (Test-Path $psqlExe)) {
    Write-Host "Error: psql.exe not found!" -ForegroundColor Red
    Write-Host "Please install PostgreSQL or add it to PATH" -ForegroundColor Yellow
    exit 1
}

# Check backup file
if ([string]::IsNullOrEmpty($BackupFile)) {
    # Find latest backup file in backups directory
    $BackupPath = ".\backups"
    if (Test-Path $BackupPath) {
        $latestBackup = Get-ChildItem -Path $BackupPath -Filter "equipment_backup_*.sql" | 
                        Sort-Object LastWriteTime -Descending | 
                        Select-Object -First 1
        if ($latestBackup) {
            $BackupFile = $latestBackup.FullName
            Write-Host "Found latest backup: $BackupFile" -ForegroundColor Yellow
        }
    }
    
    if ([string]::IsNullOrEmpty($BackupFile)) {
        Write-Host "Error: Backup file not specified and not found!" -ForegroundColor Red
        Write-Host "Usage: .\restore_database.ps1 -BackupFile 'path\to\file.sql'" -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Test-Path $BackupFile)) {
    Write-Host "Error: Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

Write-Host "Starting database restoration..." -ForegroundColor Yellow
Write-Host "Server: $TargetHost" -ForegroundColor Cyan
Write-Host "Database: $Database" -ForegroundColor Cyan
Write-Host "Backup file: $BackupFile" -ForegroundColor Cyan

# Set password environment variable
$env:PGPASSWORD = $Password

# Create database by default if not specified otherwise
if (-not $PSBoundParameters.ContainsKey('CreateDatabase')) {
    $CreateDatabase = $true
}

try {
    Write-Host ""
    Write-Host "Restoring from SQL file..." -ForegroundColor Cyan
    
    # Create database if needed
    if ($CreateDatabase) {
        Write-Host "Checking if database exists..." -ForegroundColor Yellow
        $dbExists = & $psqlExe -h $TargetHost -p $Port -U $Username -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$Database'"
        
        if ($dbExists -ne "1") {
            Write-Host "Creating database $Database..." -ForegroundColor Yellow
            & $psqlExe -h $TargetHost -p $Port -U $Username -d postgres -c "CREATE DATABASE $Database;"
            
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Error creating database!" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "Database already exists. Existing objects will be removed (--clean)." -ForegroundColor Yellow
        }
    }
    
    # Restore from SQL file
    # Use direct psql call with file for better performance
    & $psqlExe -h $TargetHost -p $Port -U $Username -d $Database -f $BackupFile
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Database restored successfully!" -ForegroundColor Green
        Write-Host "Checking tables..." -ForegroundColor Yellow
        
        # Check table count
        $tableCount = & $psqlExe -h $TargetHost -p $Port -U $Username -d $Database -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
        Write-Host "Number of tables in database: $tableCount" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Error restoring database!" -ForegroundColor Red
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
