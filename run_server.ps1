param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$EngineDist,

    [Parameter(Mandatory = $true)]
    [string]$GameOutputDir,

    [int]$Port = 1111
)

$ErrorActionPreference = "Stop"
$projectRootFull = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$engineDistFull = [System.IO.Path]::GetFullPath($EngineDist).TrimEnd('\')
$gameOutputFull = [System.IO.Path]::GetFullPath($GameOutputDir).TrimEnd('\')
$serverScript = Join-Path $engineDistFull "sdk\tools\static_http_server.py"
$buildDir = Join-Path $projectRootFull "build"
$pidFile = Join-Path $buildDir "http_server.pid"

if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
    throw "HTTP server helper not found: $serverScript"
}
if (-not (Test-Path -LiteralPath (Join-Path $gameOutputFull "index.html") -PathType Leaf)) {
    throw "Game deployment not found: $gameOutputFull"
}
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

function Stop-OwnedProcessTree {
    param([int]$ProcessId, [string]$Description)

    if ($ProcessId -le 0 -or $ProcessId -eq $PID) {
        return
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }
    $commandLine = [string]$process.CommandLine
    $owned = $commandLine.IndexOf($projectRootFull, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf("static_http_server.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    if (-not $owned) {
        Write-Warning "Ignoring stale PID $ProcessId because it no longer belongs to this project."
        return
    }
    Write-Host "Stopping $Description PID $ProcessId..."
    & taskkill.exe /F /T /PID $ProcessId *> $null
}

if (Test-Path -LiteralPath $pidFile) {
    $trackedPid = 0
    $rawPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ([int]::TryParse($rawPid, [ref]$trackedPid)) {
        Stop-OwnedProcessTree -ProcessId $trackedPid -Description "previous HTTP server"
    }
    Remove-Item -LiteralPath $pidFile -Force
}

foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
    $ownerPid = [int]$listener.OwningProcess
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
    $commandLine = if ($owner) { [string]$owner.CommandLine } else { "" }
    $owned = $commandLine.IndexOf($projectRootFull, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf("static_http_server.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    if (-not $owned) {
        throw "Port $Port is already owned by unrelated PID $ownerPid."
    }
    Stop-OwnedProcessTree -ProcessId $ownerPid -Description "stale HTTP server"
}

$deadline = [DateTime]::UtcNow.AddSeconds(5)
while (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    if ([DateTime]::UtcNow -ge $deadline) {
        throw "Port $Port did not become available."
    }
    Start-Sleep -Milliseconds 100
}

$python = (Get-Command python -ErrorAction Stop).Source
$escapedPython = $python.Replace("'", "''")
$escapedScript = $serverScript.Replace("'", "''")
$escapedOutput = $gameOutputFull.Replace("'", "''")
$serverCommand = "`$Host.UI.RawUI.WindowTitle = 'Game HTTP Server'; & '$escapedPython' '$escapedScript' --root '$escapedOutput' --port $Port --serverless"
$serverProcess = Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $serverCommand
) -WorkingDirectory $projectRootFull -PassThru
Set-Content -LiteralPath $pidFile -Value $serverProcess.Id -Encoding ascii
Write-Host "HTTP server PID: $($serverProcess.Id)"

$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        Start-Process "http://localhost:$Port"
        exit 0
    }
    if ($serverProcess.HasExited) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        throw "HTTP server console exited before port $Port became ready."
    }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)

throw "HTTP server did not become ready on port $Port."
