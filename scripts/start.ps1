[CmdletBinding()]
param(
    [int]$BackendPort = 8088,
    [int]$AgentPort = 8001,
    [switch]$NoBrowser,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Read-DotEnv {
    $envFile = Join-Path $Root ".env"
    if (-not (Test-Path $envFile)) { return }
    Get-Content $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
        $name, $value = $line -split "=", 2
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Get-PortOwner {
    param([int]$Port)
    $line = netstat -ano | Select-String ":$Port\s+.*LISTENING" | Select-Object -First 1
    if (-not $line) { return $null }
    return [int](($line.ToString() -split "\s+")[-1])
}

function Wait-Http {
    param([string]$Url, [int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $Url -TimeoutSec 2
        } catch {
            Start-Sleep -Milliseconds 600
        }
    }
    return $null
}

function Find-Maven {
    $command = Get-Command mvn.cmd -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $command = Get-Command mvn -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @()
    foreach ($base in @($env:MAVEN_HOME, $env:M2_HOME)) {
        if ($base) { $candidates += (Join-Path $base "bin\mvn.cmd") }
    }
    $candidates += "D:\apache-maven-3.9.6\bin\mvn.cmd"
    $candidates += "C:\Program Files\apache-maven-3.9.6\bin\mvn.cmd"
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    $roots = @("D:\", "C:\")
    foreach ($root in $roots) {
        $found = Get-ChildItem -Path $root -Directory -Filter "apache-maven-*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($found) {
            $candidate = Join-Path $found.FullName "bin\mvn.cmd"
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

function Show-LogTail {
    param([string]$Path)
    if (Test-Path $Path) {
        Write-Host "--- $Path ---" -ForegroundColor DarkYellow
        Get-Content $Path -Tail 30 -Encoding UTF8
    }
}

Read-DotEnv
$runDir = Join-Path $Root ".run"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

Write-Host ""
Write-Host "晴舟客服 Agent" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor DarkGreen

# 如果服务已经在跑，直接打开，不重复启动。
$existingHealth = $null
if (Get-PortOwner $BackendPort) {
    try {
        $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 2
    } catch {
        $existingHealth = $null
    }
    if ($existingHealth -and $existingHealth.agent.status -eq "up") {
        Write-Host "服务已经在运行：http://127.0.0.1:$BackendPort" -ForegroundColor Yellow
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$BackendPort" }
        exit 0
    }
    throw "端口 $BackendPort 已被其他进程占用，请先运行 .\stop.bat 或换端口。"
}
if (Get-PortOwner $AgentPort) {
    throw "端口 $AgentPort 已被其他进程占用，请先运行 .\stop.bat 或换端口。"
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $venvPython) { $python = $venvPython }
if (-not $python) { throw "找不到 Python，请先安装 Python 3.11+ 并勾选 Add to PATH。" }

& $python -c "import fastapi, uvicorn, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "检测到 Python 依赖缺失，正在安装 requirements.txt ..." -ForegroundColor Yellow
    & $python -m pip install -r (Join-Path $Root "agent-service\requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python 依赖安装失败。" }
}

$java = (Get-Command java -ErrorAction SilentlyContinue).Source
if (-not $java) { throw "找不到 Java 17，请先安装 JDK 17。" }

$jar = Join-Path $Root "backend\target\support-agent.jar"
if ($Rebuild -or -not (Test-Path $jar)) {
    $mvn = Find-Maven
    if (-not $mvn) {
        throw "找不到 Maven。你可以直接使用已构建的 backend\target\support-agent.jar，或安装 Maven 后重试。"
    }
    Write-Host "正在构建 Spring Boot ..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "backend")
    try {
        & $mvn -q -DskipTests package
        if ($LASTEXITCODE -ne 0) { throw "Maven 构建失败。" }
    } finally {
        Pop-Location
    }
}

$agentOut = Join-Path $runDir "agent.log"
$agentErr = Join-Path $runDir "agent.err.log"
$backendOut = Join-Path $runDir "backend.log"
$backendErr = Join-Path $runDir "backend.err.log"

$env:PYTHONIOENCODING = "utf-8"
$agent = $null
$backend = $null
try {
    Write-Host "启动 Python Agent (: $AgentPort) ..." -ForegroundColor Cyan
    $agent = Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$AgentPort") `
        -WorkingDirectory (Join-Path $Root "agent-service") `
        -RedirectStandardOutput $agentOut `
        -RedirectStandardError $agentErr `
        -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $runDir "agent.pid") -Value $agent.Id

    $agentHealth = Wait-Http -Url "http://127.0.0.1:$AgentPort/v1/health" -Seconds 35
    if (-not $agentHealth) {
        Show-LogTail $agentErr
        throw "Python Agent 启动超时。"
    }

    $env:SERVER_PORT = "$BackendPort"
    $env:AGENT_BASE_URL = "http://127.0.0.1:$AgentPort"
    $env:BACKEND_DATA_DIR = (Join-Path $Root "backend\.data")

    Write-Host "启动 Spring Boot (: $BackendPort) ..." -ForegroundColor Cyan
    $backend = Start-Process -FilePath $java `
        -ArgumentList @("-jar", $jar) `
        -WorkingDirectory (Join-Path $Root "backend") `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $runDir "backend.pid") -Value $backend.Id

    $health = Wait-Http -Url "http://127.0.0.1:$BackendPort/api/health" -Seconds 45
    if (-not $health) {
        Show-LogTail $backendErr
        throw "Spring Boot 启动超时。"
    }

    $url = "http://127.0.0.1:$BackendPort"
    $providerName = "mock"
    if ($health.agent.providers.providers) {
        $providerName = $health.agent.providers.providers[0].name
    }
    Write-Host ""
    Write-Host "启动成功" -ForegroundColor Green
    Write-Host "工作台:       $url"
    Write-Host "Agent 文档:   http://127.0.0.1:$AgentPort/docs"
    Write-Host "运行日志:     .run\agent.log / .run\backend.log"
    Write-Host "停止服务:     .\stop.bat"
    Write-Host "模型:         $providerName"
    Write-Host ""

    if (-not $NoBrowser) { Start-Process $url }
} catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    if ($agent -and -not $agent.HasExited) { Stop-Process -Id $agent.Id -Force -ErrorAction SilentlyContinue }
    if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item (Join-Path $runDir "agent.pid") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $runDir "backend.pid") -ErrorAction SilentlyContinue
    exit 1
}
