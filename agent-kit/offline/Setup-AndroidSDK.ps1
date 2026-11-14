[CmdletBinding()]
param(
    [string] $SdkRoot = (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
)

$ErrorActionPreference = 'Stop'
$version = '11076708'
$url = "https://dl.google.com/android/repository/commandlinetools-win-${version}_latest.zip"
$expectedSha256 = '4d6931209eebb1bfb7c7e8b240a6a3cb3ab24479ea294f3539429574b1eec862'
$cache = Join-Path $env:LOCALAPPDATA "FlutterWay\cache\commandlinetools-${version}.zip"
$sdkManager = Join-Path $SdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'

New-Item -ItemType Directory -Force -Path $SdkRoot, (Split-Path -Parent $cache) | Out-Null
if (-not (Test-Path -LiteralPath $sdkManager -PathType Leaf)) {
    if (-not (Test-Path -LiteralPath $cache -PathType Leaf) -or
        (Get-FileHash -LiteralPath $cache -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha256) {
        Write-Host 'Downloading Android command-line tools from Google (verified by SHA-256)...'
        Invoke-WebRequest -Uri $url -OutFile $cache
    }
    $actualSha256 = (Get-FileHash -LiteralPath $cache -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $expectedSha256) {
        Remove-Item -LiteralPath $cache -Force
        throw "SHA-256 mismatch for Android command-line tools. Expected $expectedSha256, got $actualSha256"
    }

    $stage = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    try {
        Expand-Archive -LiteralPath $cache -DestinationPath $stage
        $source = Join-Path $stage 'cmdline-tools'
        if (-not (Test-Path -LiteralPath (Join-Path $source 'bin\sdkmanager.bat'))) {
            throw 'Downloaded archive did not contain the expected sdkmanager.'
        }
        $latest = Join-Path $SdkRoot 'cmdline-tools\latest'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $latest) | Out-Null
        if (Test-Path -LiteralPath $latest) {
            throw "An incomplete cmdline-tools folder already exists at $latest. Inspect it and move it aside before retrying."
        }
        Move-Item -LiteralPath $source -Destination $latest
    }
    finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
}

$env:ANDROID_HOME = [System.IO.Path]::GetFullPath($SdkRoot)
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$platformTools = Join-Path $env:ANDROID_HOME 'platform-tools'
$pathEntries = @($env:PATH -split ';' | Where-Object { $_ })
if (-not ($pathEntries | Where-Object { $_.TrimEnd('\') -ieq $platformTools.TrimEnd('\') })) {
    $env:PATH = "$platformTools;$env:PATH"
}
Write-Host 'Android SDK licenses must be reviewed and accepted by the person using this computer.'
Write-Host 'The following command is interactive; answer prompts yourself:'
& $sdkManager "--sdk_root=$SdkRoot" --licenses
if ($LASTEXITCODE -ne 0) { throw "sdkmanager --licenses failed with exit code $LASTEXITCODE" }

Write-Host 'Installing Android platform-tools, Android 36 platform, and build-tools 36.0.0...'
& $sdkManager "--sdk_root=$SdkRoot" 'platform-tools' 'platforms;android-36' 'build-tools;36.0.0'
if ($LASTEXITCODE -ne 0) { throw "sdkmanager package installation failed with exit code $LASTEXITCODE" }

[Environment]::SetEnvironmentVariable('ANDROID_HOME', $env:ANDROID_HOME, 'User')
[Environment]::SetEnvironmentVariable('ANDROID_SDK_ROOT', $env:ANDROID_SDK_ROOT, 'User')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$userPathEntries = @($userPath -split ';' | Where-Object { $_ })
if (-not ($userPathEntries | Where-Object { $_.TrimEnd('\') -ieq $platformTools.TrimEnd('\') })) {
    [Environment]::SetEnvironmentVariable('Path', (@($userPathEntries + $platformTools) -join ';'), 'User')
}
Write-Host "Android SDK installed at $SdkRoot"
Write-Host 'Keep this SDK on this computer. It is not part of the shareable kit.'
