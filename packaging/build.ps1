param(
    [string]$Python = "python",
    [string]$ArtifactDirectory
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$distDirectory = Join-Path $projectRoot "dist"
$workDirectory = Join-Path $projectRoot "build\pyinstaller"
$appDirectory = Join-Path $distDirectory "Telovie"

if (-not $ArtifactDirectory) {
    $ArtifactDirectory = Join-Path $projectRoot "artifacts"
}
$ArtifactDirectory = [System.IO.Path]::GetFullPath($ArtifactDirectory)
$versionMatch = Select-String `
    -Path (Join-Path $projectRoot "telovie\__init__.py") `
    -Pattern '^__version__\s*=\s*"([^"]+)"$'
if (-not $versionMatch) {
    throw "Could not read the application version from telovie\__init__.py."
}
$version = $versionMatch.Matches[0].Groups[1].Value
$archivePath = Join-Path $ArtifactDirectory "Telovie-v$version-windows-x64.zip"

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python command '$Python' was not found. Install Python and project dependencies first."
}
& $Python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is unavailable. Install packaging\requirements-build.txt first."
}

New-Item -ItemType Directory -Force -Path $ArtifactDirectory | Out-Null
if (Test-Path -LiteralPath $appDirectory) {
    Remove-Item -LiteralPath $appDirectory -Recurse -Force
}
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

Push-Location $projectRoot
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $distDirectory `
        --workpath $workDirectory `
        (Join-Path $PSScriptRoot "telovie.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$executablePath = Join-Path $appDirectory "Telovie.exe"
if (-not (Test-Path -LiteralPath $executablePath)) {
    throw "The build did not produce $executablePath."
}
$ffmpegPlugin = Get-ChildItem -LiteralPath $appDirectory -Recurse -Filter "ffmpegmediaplugin.dll" |
    Select-Object -First 1
if (-not $ffmpegPlugin) {
    throw "The Qt FFmpeg multimedia plugin was not bundled."
}

$archivePath = Join-Path $ArtifactDirectory "Telovie-v$version-windows-x64.zip"
Compress-Archive -Path $appDirectory -DestinationPath $archivePath

$smokeDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $smokeDirectory | Out-Null
Expand-Archive -LiteralPath $archivePath -DestinationPath $smokeDirectory
$originalEnvironment = @{
    LOCALAPPDATA = $env:LOCALAPPDATA
    APPDATA = $env:APPDATA
    USERPROFILE = $env:USERPROFILE
    QT_QPA_PLATFORM = $env:QT_QPA_PLATFORM
    PATH = $env:PATH
    PYTHONHOME = $env:PYTHONHOME
    PYTHONPATH = $env:PYTHONPATH
    TELOVIE_DATA_DIR = $env:TELOVIE_DATA_DIR
    TELOVIE_LIBRARY_DIR = $env:TELOVIE_LIBRARY_DIR
}
$process = $null
try {
    $env:LOCALAPPDATA = Join-Path $smokeDirectory "LocalAppData"
    $env:APPDATA = Join-Path $smokeDirectory "AppData"
    $env:USERPROFILE = Join-Path $smokeDirectory "Profile"
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    $env:TELOVIE_DATA_DIR = Join-Path $smokeDirectory "Data"
    $env:TELOVIE_LIBRARY_DIR = Join-Path $smokeDirectory "Library"
    New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA, $env:APPDATA, $env:USERPROFILE |
        Out-Null

    $archivedExecutable = Join-Path $smokeDirectory "Telovie\Telovie.exe"
    $process = Start-Process -FilePath $archivedExecutable -PassThru
    Start-Sleep -Seconds 8
    $process.Refresh()
    if ($process.HasExited) {
        throw "The packaged app exited during the clean-profile startup smoke test (exit code $($process.ExitCode))."
    }
}
finally {
    if ($process) {
        $process.Refresh()
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
    foreach ($name in $originalEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
    }
    Remove-Item -LiteralPath $smokeDirectory -Recurse -Force
}

Write-Host "Built and smoke-tested Telovie $version."
Write-Host "Executable: $executablePath"
Write-Host "Download:   $archivePath"
