# Russian iPerf3 SpeedTest — PowerShell One-Liner Runner
[CmdletBinding()]
param(
    [switch]$Fast,
    [switch]$Help,
    [int]$Duration = 0,
    [int]$Streams = 0,
    [string[]]$City = @(),
    [string]$Export = "",
    [switch]$Json
)

$Host.UI.RawUI.WindowTitle = "Russian iPerf3 SpeedTest"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[!] Python не найден в системе." -ForegroundColor Red
    Write-Host "Установите Python с официального сайта: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Check and auto-install rich
& python -c "import rich" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Установка необходимой библиотеки 'rich'..." -ForegroundColor Cyan
    & python -m pip install rich --quiet --no-warn-script-location
}

# Download latest speedtest.py to temp
$tempScript = Join-Path $env:TEMP "speedtest_iperf3.py"
$rawUrl = "https://raw.githubusercontent.com/Kukuryzen666/russian-iperf3-servers-win/main/speedtest.py"

try {
    Invoke-RestMethod -Uri $rawUrl -OutFile $tempScript
} catch {
    Write-Host "[!] Не удалось скачать speedtest.py из репозитория." -ForegroundColor Red
    exit 1
}

$pyArgs = @($tempScript)
if ($Fast) { $pyArgs += "-f" }
if ($Help) { $pyArgs += "-h" }
if ($Duration -gt 0) { $pyArgs += @("-t", "$Duration") }
if ($Streams -gt 0) { $pyArgs += @("-P", "$Streams") }
if ($City.Count -gt 0) { $pyArgs += @("-c") + $City }
if ($Export) { $pyArgs += @("-e", "$Export") }
if ($Json) { $pyArgs += "--json" }

& python @pyArgs
Remove-Item -Path $tempScript -ErrorAction SilentlyContinue
