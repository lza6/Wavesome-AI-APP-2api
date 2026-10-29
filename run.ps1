param(
    [ValidateSet('live', 'mock')][string]$Mode = 'live',
    [int]$Port = 8931
)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PORT = "$Port"
if ($Mode -eq 'mock') {
    $env:MOCK = '1'
    Remove-Item Env:WAVESOME_DEVICE_TOKEN -ErrorAction SilentlyContinue
} else {
    Remove-Item Env:MOCK -ErrorAction SilentlyContinue
    $tokFile = Join-Path $root 'probe\token2.txt'
    if (Test-Path $tokFile) {
        $env:WAVESOME_DEVICE_TOKEN = (Get-Content $tokFile -Raw).Trim()
        Write-Host "device-token: 已载入 (probe/token2.txt)" -ForegroundColor Green
    } else {
        Write-Host "device-token: 未配置 -> LIVE 出图会返回 503（公开端点仍可用）" -ForegroundColor Yellow
    }
}
Write-Host "启动 demo 网关 http://127.0.0.1:$Port  (mode=$Mode)" -ForegroundColor Cyan
python demo_server.py
