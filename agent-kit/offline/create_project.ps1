[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9_]{1,49}$')]
    [string] $ProjectName,

    [Parameter(Mandatory = $true)]
    [string] $Destination,

    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$')]
    [string] $Organization = 'com.example'
)

$ErrorActionPreference = 'Stop'

$kitRoot = $PSScriptRoot
$packagedFlutter = Join-Path $kitRoot 'toolchain\flutter\bin\flutter.bat'
if (-not (Test-Path -LiteralPath $packagedFlutter -PathType Leaf)) {
    $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    $repositoryFlutter = Join-Path $repositoryRoot 'toolchain\flutter\bin\flutter.bat'
    if (Test-Path -LiteralPath $repositoryFlutter -PathType Leaf) {
        $kitRoot = $repositoryRoot
        $packagedFlutter = $repositoryFlutter
    }
}
$flutter = if (Test-Path -LiteralPath $packagedFlutter -PathType Leaf) {
    [pscustomobject]@{ Source = $packagedFlutter }
} else {
    Get-Command flutter -ErrorAction SilentlyContinue
}
if (-not $flutter) {
    throw 'Flutter SDK was not found. Extract the full offline kit and dot-source Use-AgentKit.ps1 first.'
}

$target = [System.IO.Path]::GetFullPath($Destination)
$parent = [System.IO.Path]::GetDirectoryName($target)
$driveRoot = [System.IO.Path]::GetPathRoot($target)
if (-not $parent -or $target.TrimEnd('\') -eq $driveRoot.TrimEnd('\')) {
    throw 'Destination must be a project folder, not a drive root.'
}
if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
    throw "Destination parent does not exist: $parent"
}
if (Test-Path -LiteralPath $target) {
    throw "Refusing to overwrite an existing destination: $target"
}

$template = Join-Path $PSScriptRoot 'template'
if (-not (Test-Path -LiteralPath (Join-Path $template 'pubspec.yaml') -PathType Leaf)) {
    throw "Offline template files are missing: $template"
}

Write-Host "Creating Android Flutter scaffolding offline at: $target"
& $flutter.Source create --no-pub --platforms=android --org $Organization --project-name $ProjectName $target
if ($LASTEXITCODE -ne 0) {
    throw "flutter create failed with exit code $LASTEXITCODE. Any partially generated files are left at: $target"
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$templatePubspec = Get-Content -LiteralPath (Join-Path $template 'pubspec.yaml') -Raw
$templatePubspec = $templatePubspec.Replace('__PROJECT_NAME__', $ProjectName)
[System.IO.File]::WriteAllText((Join-Path $target 'pubspec.yaml'), $templatePubspec, $utf8NoBom)
$templateLock = Join-Path $template 'pubspec.lock'
if (Test-Path -LiteralPath $templateLock -PathType Leaf) {
    Copy-Item -LiteralPath $templateLock -Destination (Join-Path $target 'pubspec.lock') -Force
}

$templateLib = Join-Path $template 'lib'
Copy-Item -Path (Join-Path $templateLib '*') -Destination (Join-Path $target 'lib') -Recurse -Force
$templateTests = Join-Path $template 'test'
Copy-Item -Path (Join-Path $templateTests '*') -Destination (Join-Path $target 'test') -Recurse -Force
$templateReadme = Get-Content -LiteralPath (Join-Path $template 'README.md') -Raw
$templateReadme = $templateReadme.Replace('__PROJECT_NAME__', $ProjectName)
[System.IO.File]::WriteAllText((Join-Path $target 'README.md'), $templateReadme, $utf8NoBom)
Copy-Item -LiteralPath (Join-Path $template 'analysis_options.yaml') -Destination (Join-Path $target 'analysis_options.yaml') -Force

$testFile = Join-Path $target 'test\widget_test.dart'
$testSource = Get-Content -LiteralPath $testFile -Raw
$testSource = $testSource.Replace('__PROJECT_NAME__', $ProjectName)
[System.IO.File]::WriteAllText($testFile, $testSource, $utf8NoBom)

Push-Location $target
try {
    & $flutter.Source pub get --offline
    if ($LASTEXITCODE -ne 0) {
        throw "flutter pub get --offline failed with exit code $LASTEXITCODE. The project source remains at: $target"
    }
}
finally {
    Pop-Location
}

Write-Host "Project created: $target"
Write-Host 'Next: flutter analyze; flutter test'
