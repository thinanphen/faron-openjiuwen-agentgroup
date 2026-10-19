#!/usr/bin/env bash
# 法元 · Faron Agent Group —— 一键验证（评委 / 同伴可直接跑）
#
# 用法：
#   ./verify.sh            # 跑全部
#   ./verify.sh --quiet    # 只显示结论
#
# 退出码约定（与 verify.ps1 保持一字不差，别混用）：
#   0  = 全部检查通过
#   1  = 有检查未通过（run_all_checks.py 判红）
#   2  = **环境问题**：找不到可用的 Python（验证根本没启动）
#
# 说明：这是个**薄包装**，真正的验证逻辑在 tools/run_all_checks.py ——
# 这样 Windows（verify.ps1）与 Linux/macOS（verify.sh）行为完全一致，
# 不会出现"两个平台各判一套"的分裂。
set -u

cd "$(dirname "$0")" || exit 2

# ─────────────────────────────────────────────────────────────────────
# 找 Python：必须"真能跑"，不能只看"命令存在"
#
# 为什么加这道关（R9 · P0-1，Windows 侧踩得很惨）：
#   Windows 上 `python` / `python3` 常常是 **Microsoft Store 占位**，
#   `Get-Command` / `command -v` 都能找到，但一执行就失败（exit=9009）。
#   旧脚本只看"存在"就用了，结果验证根本没启动，却还提示"看 ❌ 那一项"
#   —— 指向一个根本不存在的 ❌。
#
#   Linux/macOS 上一般没有这种占位，但同理：一个坏掉的 venv shim、
#   一个只装了 python2 的路径，都会让 `command -v` 骗过检查。
#   所以两边统一成：**真跑一次、问解释器自己的版本号、要求 >= 3.11**。
# ─────────────────────────────────────────────────────────────────────
PY=""
PY_VER=""
TRIED=""

for cand in python3 python py; do
  if ! command -v "$cand" >/dev/null 2>&1; then
    TRIED="$TRIED\n     - $cand (未找到)"
    continue
  fi

  probe="$("$cand" -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null)"
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$probe" ]; then
    TRIED="$TRIED\n     - $cand (exit=$rc，多为坏 shim 或 Store 占位)"
    continue
  fi

  major="$(echo "$probe" | awk '{print $1}')"
  minor="$(echo "$probe" | awk '{print $2}')"
  case "$major" in
    ''|*[!0-9]*) TRIED="$TRIED\n     - $cand (版本输出无法解析：$probe)"; continue ;;
  esac
  case "$minor" in
    ''|*[!0-9]*) TRIED="$TRIED\n     - $cand (版本输出无法解析：$probe)"; continue ;;
  esac

  if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
    TRIED="$TRIED\n     - $cand (版本 $major.$minor，需要 3.11+)"
    continue
  fi

  PY="$cand"
  PY_VER="Python $major.$minor"
  break
done

if [ -z "$PY" ]; then
  echo "=============================================================="
  echo " 法元 · Faron Agent Group —— 一键验证"
  echo "=============================================================="
  echo
  echo "❌ 找不到可用的 Python（需要 3.11+），验证**没有启动**。"
  echo
  echo "   已尝试："
  printf "%b\n" "$TRIED"
  echo
  echo "   常见原因："
  echo "     - 只有 Python 2 或低于 3.11 的版本"
  echo "     - venv / pyenv / conda 的 shim 坏了（命令在，但一跑就退出非 0）"
  echo "     - Windows 上 python/python3 是 Microsoft Store 占位（见 verify.ps1）"
  echo
  echo "   修法：装 python.org 的 3.11+（或 pyenv install 3.12），确保 python3 -V 有输出。"
  echo
  echo "   这是**环境问题**，不是本项目检查未通过（exit=2）。"
  exit 2
fi

echo "=============================================================="
echo " 法元 · Faron Agent Group —— 一键验证"
echo "=============================================================="
echo " python : $PY_VER  (via '$PY')"
echo " 目录   : $(pwd)"
echo

# 边跑边显示，同时把输出抓住 —— 失败时要靠它判断"到底跑没跑起来"
TMP_OUT="$(mktemp 2>/dev/null || echo /tmp/faron_verify.$$)"
"$PY" tools/run_all_checks.py "$@" 2>&1 | tee "$TMP_OUT"
code=$?
# shellcheck disable=SC2002
# 注意：grep -c 在计数为 0 时**退出码是 1**（不是错），所以用 `|| true` 吃掉退出码，
# 只留它打印的 "0"。不这样写会得到 "0\n0"，后面的 -gt 比较就会报
# "integer expression expected"。
HAS_VERDICT="$(grep -c '[✅❌]' "$TMP_OUT" 2>/dev/null || true)"
HAS_VERDICT="${HAS_VERDICT:-0}"
rm -f "$TMP_OUT"

echo
echo "=============================================================="
if [ "$code" -eq 0 ]; then
  echo " 结论：全部通过。"
  echo " 你没有用任何 API Key，也没有联网。"
else
  # 必须区分两种失败：**检查未通过** vs **验证脚本根本没启动**。
  if [ "$HAS_VERDICT" -gt 0 ]; then
    echo " 结论：有未通过项（exit=$code）。"
    echo " 上面标 ❌ 的那一项就是原因；先看它输出的最后一行。"
  else
    echo " 结论：验证脚本本身**没有启动**（exit=$code），不是检查未通过。"
    echo " 往上翻第一条报错。常见原因："
    echo "   - 依赖没装：pip install -r requirements.txt"
    echo "   - Python 能跑但环境不完整（缺 openjiuwen / aiosqlite）"
    echo "   - 当前目录不对（本脚本应在本仓库根目录运行）"
  fi
fi
echo "=============================================================="
exit "$code"
