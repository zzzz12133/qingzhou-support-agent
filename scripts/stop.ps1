[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $Root ".run"

Write-Host "停止晴舟客服 Agent ..." -ForegroundColor Yellow

$targets = @(
    @{ Name = "Spring Boot"; File = "backend.pid"; Process = "java" },
    @{ Name = "Python Agent"; File = "agent.pid"; Process = "python" }
)

foreach ($target in $targets) {
    $pidFile = Join-Path $runDir $target.File
    if (-not (Test-Path $pidFile)) {
        Write-Host "$($target.Name): 没有 PID 文件，跳过。"
        continue
    }
    $processId = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $processId) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        continue
    }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Host "$($target.Name): 进程已不存在。"
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        continue
    }
    if ($process.ProcessName -notlike "*$($target.Process)*") {
        Write-Host "$($target.Name): PID $processId 现在是 $($process.ProcessName)，为避免误杀已跳过。" -ForegroundColor DarkYellow
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        continue
    }
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Write-Host "$($target.Name): 已停止 (PID $processId)。"
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500
foreach ($port in 8001, 8088) {
    $line = netstat -ano | Select-String ":$port\s+.*LISTENING" | Select-Object -First 1
    if ($line) {
        Write-Host "提示：端口 $port 仍有进程监听，可能是你另外启动的实例。" -ForegroundColor DarkYellow
    }
}
