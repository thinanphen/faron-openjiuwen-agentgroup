# 法元 · Faron Agent Group —— 一键验证（Windows / PowerShell）
#
# 用法：
#   ./verify.ps1
#   ./verify.ps1 -Quiet
#
# 退出码约定（**重要，别混用**）：
#   0  = 全部检查通过
#   1  = 有检查未通过（run_all_checks.py 判红）
#   2  = **环境问题**：找不到可用的 Python（验证根本没启动）
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

# ─────────────────────────────────────────────────────────────────────
# 找 Python：必须"真能跑"，不能只看"名字存在"
#
# 踩过的坑（R9 · P0-1，别人机器上第一秒就撞上）：
#   Windows 上 `python` / `python3` 常常是 **Microsoft Store 占位**
#   （`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`，0 字节）。
#   `Get-Command python` **能找到它**，但一执行就：
#       Python was not found; run without arguments to install from the
#       Microsoft Store, ...        （exit=9009）
#   旧版脚本只判断 `Get-Command` 命中就用了，结果 `& python -V` 返回空、
#   `run_all_checks.py` 根本没启动，却还提示"看 ❌ 那一项" ——
#   **指向一个根本不存在的 ❌**，看的人完全无从下手。
#
# 所以这里三道关：① 名字存在 → ② 真能执行且 exit=0 → ③ 版本 >= 3.11。
# 并把 `py`（Windows 官方启动器）列为候选，它通常不受 Store 占位影响。
# ─────────────────────────────────────────────────────────────────────
$py = $null
$pyVer = $null
$tried = @()

foreach ($cand in @('python', 'python3', 'py')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if (-not $cmd) {
        $tried += "$cand (未找到)"
        continue
    }

    # 真跑一次，问解释器自己的版本号 —— 不看 `-V` 的文本，避免占位符的假输出
    #
    # 注意：占位符有两种失败形态，都要安静地吃掉，别让 PowerShell 的原生报错
    # 盖住我们自己的说明：
    #   ① 真实的 Store 占位（0 字节 reparse point）：进程能起，exit=9009
    #   ② 压根不是可执行文件：PowerShell 直接抛
    #      "Program 'python.exe' failed to run: ... is not a valid application"
    #      —— 这种连 $LASTEXITCODE 都不会被设置
    $probe = $null
    $probeCode = $null
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $probe = & $cand -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2>$null
        $probeCode = $LASTEXITCODE
    } catch {
        $probe = $null
    } finally {
        $ErrorActionPreference = $prevEap
    }

    if ($null -eq $probeCode -or $probeCode -ne 0) {
        $why = if ($null -ne $probeCode) { "exit=$probeCode" } else { "无法执行" }
        $tried += "$cand ($why —— 多为 Store 占位)"
        continue
    }

    $ver = ($probe -join ' ').Trim()
    if ($ver -notmatch '^(\d+)\s+(\d+)') {
        $tried += "$cand (版本输出无法解析：'$ver')"
        continue
    }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        $tried += "$cand (版本 $major.$minor，需要 3.11+)"
        continue
    }

    $py = $cand
    $pyVer = "Python $major.$minor"
    break
}

if (-not $py) {
    Write-Host "=============================================================="
    Write-Host " 法元 · Faron Agent Group —— 一键验证"
    Write-Host "=============================================================="
    Write-Host ""
    Write-Host "❌ 找不到可用的 Python（需要 3.11+），验证**没有启动**。" -ForegroundColor Red
    Write-Host ""
    Write-Host "   已尝试："
    foreach ($t in $tried) { Write-Host "     - $t" }
    Write-Host ""
    Write-Host "   常见原因：Windows 上 python / python3 是 **Microsoft Store 占位**，"
    Write-Host "             'Get-Command' 能找到它，但一执行就报 'Python was not found'。"
    Write-Host ""
    Write-Host "   修法（任选一个）："
    Write-Host "     1) 装 python.org 的 3.11+（安装时勾选 Add python.exe to PATH）"
    Write-Host "     2) 用官方启动器：py -3 -V 能出版本号即可（本脚本会自动用 py）"
    Write-Host "     3) 设置 -> 应用 -> 高级应用设置 -> 应用执行别名 -> 关掉 python/python3"
    Write-Host ""
    Write-Host "   这是**环境问题**，不是本项目检查未通过（exit=2）。" -ForegroundColor Yellow
    exit 2
}

Write-Host "=============================================================="
Write-Host " 法元 · Faron Agent Group —— 一键验证"
Write-Host "=============================================================="
Write-Host " python : $pyVer  (via '$py')"
Write-Host " 目录   : $(Get-Location)"
Write-Host ""

# 中文 Windows 控制台默认 GBK，子脚本里有 ✅/❌；统一用 UTF-8 输出避免乱码
$env:PYTHONIOENCODING = 'utf-8'

# 边跑边显示，同时把输出抓住 —— 失败时要靠它判断"到底跑没跑起来"
$out = @()
if ($Quiet) {
    & $py tools/run_all_checks.py 2>&1 | Tee-Object -Variable out | Select-Object -Last 6
} else {
    & $py tools/run_all_checks.py 2>&1 | Tee-Object -Variable out
}
$code = $LASTEXITCODE

Write-Host ""
Write-Host "=============================================================="
if ($code -eq 0) {
    Write-Host " 结论：全部通过。" -ForegroundColor Green
    Write-Host " 你没有用任何 API Key，也没有联网。"
} else {
    # 必须区分两种失败：**检查未通过** vs **验证脚本根本没启动**。
    # 混在一起说"看 ❌ 那一项"，在最糟的情况下会指向一个不存在的 ❌。
    $text = ($out -join "`n")
    $hasVerdict = $text -match '[✅❌]'
    if ($hasVerdict) {
        Write-Host " 结论：有未通过项（exit=$code）。" -ForegroundColor Red
        Write-Host " 上面标 ❌ 的那一项就是原因；先看它输出的最后一行。"
    } else {
        Write-Host " 结论：验证脚本本身**没有启动**（exit=$code），不是检查未通过。" -ForegroundColor Red
        Write-Host " 往上翻第一条报错。常见原因："
        Write-Host "   - 依赖没装：pip install -r requirements.txt"
        Write-Host "   - Python 能跑但环境不完整（缺 openjiuwen / aiosqlite）"
        Write-Host "   - 当前目录不对（本脚本应在本仓库根目录运行）"
    }
}
Write-Host "=============================================================="
exit $code
