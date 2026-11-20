# Publish the cleaned Harness Pocket source tree to GitHub.
#
#   Usage (from anywhere):
#     powershell -ExecutionPolicy Bypass -File build-scripts\push.ps1
#
# The token is read with Read-Host -AsSecureString: it never appears in the
# console history, in a file, or in the transcript this repo produces.

param(
    [string]$Owner = "13331271",
    [string]$Repo = "harness-pocket",
    [switch]$Private
)

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\Admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "Pushing to github.com/$Owner/$Repo" -ForegroundColor Cyan
$secure = Read-Host -Prompt "Paste a fine-grained PAT (Contents: Read and write)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:GITHUB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$args = @(
    (Join-Path $PSScriptRoot "push_to_github.py"),
    "--owner", $Owner,
    "--repo", $Repo
)
if ($Private) { $args += "--private" }

& $python @args
$code = $LASTEXITCODE
Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue
if ($code -ne 0) {
    Write-Host "Push failed with exit code $code" -ForegroundColor Red
    exit $code
}
Write-Host "Done: https://github.com/$Owner/$Repo" -ForegroundColor Green
