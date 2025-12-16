# Функция для загрузки настроек из файла settings.txt
function Load-Settings {
    param(
        [string]$SettingsFile = "settings.txt"
    )
    
    $settings = @{}
    
    if (-not (Test-Path $SettingsFile)) {
        Write-Host "Файл настроек не найден: $SettingsFile" -ForegroundColor Red
        return $null
    }
    
    Get-Content $SettingsFile | ForEach-Object {
        $line = $_.Trim()
        # Пропускаем пустые строки и комментарии
        if ($line -and -not $line.StartsWith("#")) {
            if ($line -match "^([^=]+)=(.*)$") {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                $settings[$key] = $value
            }
        }
    }
    
    return $settings
}

