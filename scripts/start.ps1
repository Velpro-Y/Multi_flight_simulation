$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = 'C:\Users\velpro\.conda\envs\simulink\python.exe'

if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "未找到 simulink 环境的 Python：$pythonExe"
}

$env:PYTHONPATH = Join-Path $projectRoot 'src'

Set-Location -LiteralPath $projectRoot
& $pythonExe -m uvicorn multiflight.main:app --host 127.0.0.1 --port 8000

