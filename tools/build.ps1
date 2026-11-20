param(
    [string]$Tasks = ":app:compileReleaseKotlin",
    [switch]$Full
)

# Build environment for the Harness Pocket Android app.
# Everything stays inside the project tree: no global JDK/SDK/Gradle state.

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$root = Join-Path $proj "app-source"
$tc = Join-Path $proj "toolchain"

$env:JAVA_HOME = Join-Path $tc "jdk-full\jdk-21.0.13.0.2+1"
$env:ANDROID_HOME = Join-Path $tc "android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:GRADLE_USER_HOME = Join-Path $tc "gradle-user"
$env:ANDROID_USER_HOME = Join-Path $tc "android-user"
$env:TEMP = Join-Path $tc "build-temp"
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

$env:JAVA_TOOL_OPTIONS = "-Duser.home=$tc\java-home -Djava.io.tmpdir=$tc\build-temp"

$gradle = Join-Path $tc "gradle\gradle-8.9\bin\gradle.bat"
$runtimeZip = Join-Path $proj "runtime-derived\pocket-runtime-arm64-v8a.zip"

$args = @(
    "-p", $root,
    "-Pabi=arm64-v8a",
    "-Ppackage=full",
    "-PruntimeZip=$runtimeZip",
    "-PruntimeVersion=2026.11.18-pocket-951b1843",
    "-PruntimeSha256=3d5d93bdb88dfe35809918a5d4a2a9c5b783b86313493ea20fb1a0927bf45e89",
    "-PruntimeSize=137195053",
    "-PruntimeUnpacked=438441738",
    "-PruntimeBuiltAt=1794973473",
    "-PupdateRepo=13331271/harness-pocket",
    "--no-daemon",
    "--console=plain"
) + ($Tasks -split " ")

$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $gradle @args 2>&1 | ForEach-Object { $_ }
$code = $LASTEXITCODE
$sw.Stop()
Write-Output ""
Write-Output ("EXIT={0} ELAPSED={1:n1}s" -f $code, $sw.Elapsed.TotalSeconds)
exit $code
