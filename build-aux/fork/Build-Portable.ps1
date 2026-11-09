# Run from a recursive checkout of this fork on Windows x64.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
function Invoke-Checked([string]$program, [string[]]$arguments) {
    & $program @arguments
    if ($LASTEXITCODE -ne 0) { throw "$program exited with $LASTEXITCODE" }
}

Push-Location $root
try {
    $pin = Invoke-Checked git @('rev-parse', 'HEAD:plugins/obs-browser')
    $actual = Invoke-Checked git @('-C', 'plugins/obs-browser', 'rev-parse', 'HEAD')
    if ($pin -ne $actual) { throw 'Run git submodule update --init --recursive before building.' }

    Invoke-Checked cmake @('--preset', 'windows-x64')
    Invoke-Checked cmake @('--build', '--preset', 'windows-x64', '--config', 'Release', '--parallel')

    # Stage into a fresh directory so a previous portable profile cannot enter the archive.
    $stage = (New-Item -ItemType Directory -Path "build_x64/portable-$([guid]::NewGuid())").FullName
    try {
        Invoke-Checked cmake @('--install', 'build_x64', '--config', 'Release', '--prefix', $stage)
        foreach ($file in @('bin/64bit/obs64.exe', 'bin/64bit/obs.dll', 'core/obs-browser/obs-browser.dll', 'core/obs-browser/obs-browser-page.exe')) {
            if (!(Test-Path -LiteralPath (Join-Path $stage $file) -PathType Leaf)) { throw "Missing $file" }
        }
        if (!(Get-ChildItem -LiteralPath $stage -Recurse -Filter 'libcef.dll' -File)) { throw 'Missing libcef.dll' }

        Get-ChildItem -LiteralPath $stage -Recurse -Filter '*.pdb' -File | Remove-Item
        New-Item -ItemType File -Path "$stage/portable_mode.txt", "$stage/disable_updater.txt" | Out-Null
        Copy-Item -LiteralPath "$root/COPYING" -Destination "$stage/COPYING"
        $sha = Invoke-Checked git @('rev-parse', 'HEAD')
        @("OBS Studio https://github.com/Huihuing/obs-studio/tree/$sha",
          "obs-browser https://github.com/Huihuing/obs-browser/tree/$pin") | Set-Content "$stage/FORK-SOURCE.txt"
        $archive = "$root/build_x64/obs-fork-windows-x64-$($sha.Substring(0, 9)).zip"
        Push-Location $stage
        try { Invoke-Checked cmake @('-E', 'tar', 'cf', $archive, '--format=zip', '.') }
        finally { Pop-Location }
        Write-Host "Portable ZIP: $archive"
    } finally { Remove-Item -Recurse -Force -LiteralPath $stage }
} finally { Pop-Location }
