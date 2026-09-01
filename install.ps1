# ==============================================================================
# Buddy - Single Command Windows One-Liner Installer
# Usage:
#   irm https://raw.githubusercontent.com/shuaiyuancn/buddy/master/install.ps1 | iex
# ==============================================================================

[CmdletBinding()]
param (
    [string]$Repo = "shuaiyuancn/buddy",
    [string]$InstallDir = "$env:LOCALAPPDATA\Buddy",
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "            Buddy - AI Audio Assistant Installer        " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Fetch Latest Release Information from GitHub
Write-Host "[1/5] Fetching latest release info from $Repo..." -ForegroundColor Yellow
$Headers = @{
    "User-Agent" = "Buddy-Installer"
    "Accept"     = "application/vnd.github.v3+json"
}

try {
    $ReleaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
    $Release = Invoke-RestMethod -Uri $ReleaseUrl -Headers $Headers -UseBasicParsing
} catch {
    # Fallback to general releases list if /latest is not tagged yet
    try {
        $ReleasesUrl = "https://api.github.com/repos/$Repo/releases"
        $AllReleases = Invoke-RestMethod -Uri $ReleasesUrl -Headers $Headers -UseBasicParsing
        if ($AllReleases.Count -gt 0) {
            $Release = $AllReleases[0]
        } else {
            throw "No releases found in repository $Repo"
        }
    } catch {
        Write-Error "Failed to retrieve release metadata for $($Repo): $_"
        exit 1
    }
}

$Tag = $Release.tag_name
Write-Host "      Found latest version: $Tag" -ForegroundColor Green

# 2. Locate Buddy.exe in release assets
$ExeAsset = $Release.assets | Where-Object { $_.name -like "*Buddy.exe*" -or $_.name -like "*.exe" } | Select-Object -First 1

if (-not $ExeAsset) {
    Write-Error "No .exe asset found in release $($Tag) for $($Repo)!"
    exit 1
}

$DownloadUrl = $ExeAsset.browser_download_url
$TargetExe = Join-Path $InstallDir "Buddy.exe"

# 3. Terminate running instance & prepare directory
Write-Host "[2/5] Preparing installation directory ($InstallDir)..." -ForegroundColor Yellow
$RunningBuddy = Get-Process -Name "Buddy" -ErrorAction SilentlyContinue
if ($RunningBuddy) {
    Write-Host "      Stopping active Buddy instance..." -ForegroundColor Yellow
    $RunningBuddy | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# 4. Download latest executable
Write-Host "[3/5] Downloading Buddy.exe ($([math]::round($ExeAsset.size / 1MB, 2)) MB)..." -ForegroundColor Yellow
try {
    # Use WebClient for high download speed without PowerShell progress bar overhead
    $WebClient = New-Object System.Net.WebClient
    $WebClient.Headers.Add("User-Agent", "Buddy-Installer")
    $WebClient.DownloadFile($DownloadUrl, $TargetExe)
    Write-Host "      Downloaded successfully to $TargetExe" -ForegroundColor Green
} catch {
    Write-Error "Download failed: $_"
    exit 1
}

# 5. Create Start Menu Shortcut & update User PATH
Write-Host "[4/5] Creating Start Menu shortcut and registering PATH..." -ForegroundColor Yellow
try {
    $StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $ShortcutPath = Join-Path $StartMenuDir "Buddy.lnk"
    
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetExe
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "Buddy - Background Audio Transcriber & Daily Executive Summarizer"
    $Shortcut.Save()
    Write-Host "      Created shortcut: $ShortcutPath" -ForegroundColor Green
} catch {
    Write-Warning "Could not create Start Menu shortcut: $_"
}

# Add InstallDir to User PATH if missing
try {
    $UserPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
    if ($UserPath -notlike "*$InstallDir*") {
        $NewPath = "$UserPath;$InstallDir"
        [Environment]::SetEnvironmentVariable("Path", $NewPath, [EnvironmentVariableTarget]::User)
        $env:Path = "$env:Path;$InstallDir"
        Write-Host "      Added $InstallDir to User PATH" -ForegroundColor Green
    }
} catch {
    Write-Warning "Could not update User PATH: $_"
}

# 6. Ensure default configuration template exists
$UserBuddyConfigDir = Join-Path $env:USERPROFILE ".buddy"
$ConfigFile = Join-Path $UserBuddyConfigDir "config.json"
if (-not (Test-Path $UserBuddyConfigDir)) {
    New-Item -ItemType Directory -Path $UserBuddyConfigDir -Force | Out-Null
}
if (-not (Test-Path $ConfigFile)) {
    $DefaultConfig = @{
        "GEMINI_API_KEY"              = ""
        "STT_PROVIDER"                = "gemini"
        "GCP_PROJECT_ID"              = ""
        "GCP_REGION"                  = "us"
        "GCP_SERVICE_ACCOUNT_KEY_PATH" = ""
        "GCP_LANGUAGES"               = @("zh-CN", "en-US")
        "GITHUB_REPO"                 = $Repo
        "AUTO_UPDATE"                 = $true
        "UPDATE_CHECK_INTERVAL_HOURS" = 1
    } | ConvertTo-Json -Depth 4
    Set-Content -Path $ConfigFile -Value $DefaultConfig -Encoding UTF8
    Write-Host "      Created default config template at $ConfigFile" -ForegroundColor Green
}

Write-Host "[5/5] Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Buddy is installed at: $TargetExe" -ForegroundColor White
Write-Host " Configuration file at: $ConfigFile" -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $NoLaunch) {
    Write-Host "Launching Buddy..." -ForegroundColor Green
    Start-Process -FilePath $TargetExe -WorkingDirectory $InstallDir
}
