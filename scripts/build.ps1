[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Maven {
    $command = Get-Command mvn.cmd -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $command = Get-Command mvn -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($base in @($env:MAVEN_HOME, $env:M2_HOME)) {
        if ($base) {
            $candidate = Join-Path $base "bin\mvn.cmd"
            if (Test-Path $candidate) { return $candidate }
        }
    }
    $fallback = "D:\apache-maven-3.9.6\bin\mvn.cmd"
    if (Test-Path $fallback) { return $fallback }
    throw "找不到 Maven，请安装 Maven 3.9+。"
}

if (-not $SkipFrontend) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { throw "找不到 npm，请安装 Node.js 20+。" }
    Push-Location (Join-Path $Root "frontend")
    try {
        if (-not (Test-Path "node_modules")) {
            if (Test-Path "package-lock.json") {
                & npm ci --no-audit --no-fund
            } else {
                & npm install --no-audit --no-fund
            }
            if ($LASTEXITCODE -ne 0) { throw "npm 安装失败。" }
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "前端构建失败。" }
    } finally {
        Pop-Location
    }
}

$mvn = Find-Maven
Push-Location (Join-Path $Root "backend")
try {
    & $mvn -DskipTests package
    if ($LASTEXITCODE -ne 0) { throw "后端构建失败。" }
} finally {
    Pop-Location
}

$jar = Join-Path $Root "backend\target\support-agent.jar"
Write-Host ""
Write-Host "构建完成：" -ForegroundColor Green
Write-Host "  $jar"
Write-Host "运行 .\start.bat 启动服务。"
