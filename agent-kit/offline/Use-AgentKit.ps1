# Dot-source this script to use the kit's portable Flutter/Dart and JDK in the current PowerShell session.
$kitRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $kitRoot 'toolchain\flutter\bin\flutter.bat'))) {
    $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    if (Test-Path -LiteralPath (Join-Path $repoRoot 'toolchain\flutter\bin\flutter.bat')) {
        $kitRoot = $repoRoot
    }
}

$flutterBin = Join-Path $kitRoot 'toolchain\flutter\bin'
$jdkHome = Join-Path $kitRoot 'toolchain\jdk'
$pubCache = Join-Path $kitRoot 'toolchain\pub-cache'
if (-not (Test-Path -LiteralPath (Join-Path $flutterBin 'flutter.bat') -PathType Leaf)) {
    throw "Flutter SDK files are missing under: $kitRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $jdkHome 'bin\java.exe') -PathType Leaf)) {
    throw "Temurin JDK files are missing under: $kitRoot"
}

$env:FLUTTER_ROOT = Join-Path $kitRoot 'toolchain\flutter'
$env:JAVA_HOME = $jdkHome
$env:PUB_CACHE = $pubCache
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
$env:PATH = "$flutterBin;$($jdkHome)\bin;$env:PATH"
Write-Host "FlutterWay Agent Kit environment enabled for this PowerShell session."
Write-Host "Flutter: $env:FLUTTER_ROOT"
Write-Host "Java:    $env:JAVA_HOME"
Write-Host "Pub cache: $env:PUB_CACHE"
Write-Host 'Android SDK is not bundled. Run .\Setup-AndroidSDK.ps1 while online; review licenses yourself.'
