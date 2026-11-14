[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Project
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath $Project).Path
$flutter = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutter) { throw 'Flutter not found. Dot-source .\Use-AgentKit.ps1 first.' }
if (-not $env:ANDROID_HOME -or -not (Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe'))) {
    throw 'Android SDK is not configured. Run .\Setup-AndroidSDK.ps1 first.'
}

Push-Location $projectPath
try {
    Write-Host "Online warm-up: resolving this project's pub, Gradle, and Maven dependencies."
    & $flutter.Source pub get
    if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed with exit code $LASTEXITCODE" }
    & $flutter.Source build apk --debug
    if ($LASTEXITCODE -ne 0) { throw "First Android build failed with exit code $LASTEXITCODE" }
    Write-Host 'Offline verification using the dependencies cached for this project...'
    & $flutter.Source pub get --offline
    if ($LASTEXITCODE -ne 0) { throw "flutter pub get --offline failed with exit code $LASTEXITCODE" }
    & $flutter.Source analyze
    if ($LASTEXITCODE -ne 0) { throw "flutter analyze failed with exit code $LASTEXITCODE" }
    & $flutter.Source test
    if ($LASTEXITCODE -ne 0) { throw "flutter test failed with exit code $LASTEXITCODE" }
    $gradle = Join-Path $projectPath 'android\gradlew.bat'
    if (-not (Test-Path -LiteralPath $gradle -PathType Leaf)) { throw "Gradle wrapper not found: $gradle" }
    & $gradle --offline -p (Join-Path $projectPath 'android') assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Offline APK build failed with exit code $LASTEXITCODE" }
    Write-Host 'Offline build dependencies are warm on this computer.'
    Write-Host "Project-specific caches live in the user profile; this script does not copy or redistribute them."
}
finally {
    Pop-Location
}
