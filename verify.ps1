# 法元 · Faron Agent Group —— 一键验证（Windows / PowerShell）
#
# 用法：
#   ./verify.ps1
#   ./verify.ps1 -Quiet
#
# 退出码：0 = 全部通过；非 0 = 有未通过项（并指出是哪一项）
#
# 说明：这是个**薄包装**，真正的验证逻辑在 tools/run_all_checks.py ——
# 这样 Windows（verify.ps1）与 Linux/macOS（verify.sh）行为完全一致，
# 不会出现"两个平台各判一套"的分裂。

[CmdletBinding()]
param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

# 找一个可用的 python
$py = $null
foreach ($cand in @('python', 'python3')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "❌ 找不到 python（需要 3.11+）" -ForegroundColor Red
    exit 2
}

$pyVersion = (& $py -V 2>&1) -join ' '
Write-Host "=============================================================="
Write-Host " 法元 · Faron Agent Group —— 一键验证"
Write-Host "=============================================================="
Write-Host " python : $pyVersion"
Write-Host " 目录   : $(Get-Location)"
Write-Host ""

# 中文 Windows 控制台默认 GBK，子脚本里有 ✅/❌；统一用 UTF-8 输出避免乱码
$env:PYTHONIOENCODING = 'utf-8'

if ($Quiet) {
    & $py tools/run_all_checks.py | Select-Object -Last 6
} else {
    & $py tools/run_all_checks.py
}
$code = $LASTEXITCODE

Write-Host ""
Write-Host "=============================================================="
if ($code -eq 0) {
    Write-Host " 结论：全部通过。" -ForegroundColor Green
    Write-Host " 你没有用任何 API Key，也没有联网。"
} else {
    Write-Host " 结论：有未通过项（exit=$code）。" -ForegroundColor Red
    Write-Host " 上面标 ❌ 的那一项就是原因；先看它输出的最后一行。"
}
Write-Host "=============================================================="
exit $code
