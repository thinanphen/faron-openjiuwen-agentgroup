#!/usr/bin/env bash
# 法元 · Faron Agent Group —— 一键验证（评委 / 同伴可直接跑）
#
# 用法：
#   ./verify.sh            # 跑全部
#   ./verify.sh --quiet    # 只显示结论
#
# 退出码：0 = 全部通过；非 0 = 有未通过项（并指出是哪一项）
#
# 说明：这是个**薄包装**，真正的验证逻辑在 tools/run_all_checks.py ——
# 这样 Windows（verify.ps1）与 Linux/macOS（verify.sh）行为完全一致，
# 不会出现"两个平台各判一套"的分裂。
set -u

cd "$(dirname "$0")" || exit 2

# 找一个可用的 python
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "❌ 找不到 python（需要 3.11+）" >&2
  exit 2
fi

echo "=============================================================="
echo " 法元 · Faron Agent Group —— 一键验证"
echo "=============================================================="
echo " python : $("$PY" -V 2>&1)"
echo " 目录   : $(pwd)"
echo

"$PY" tools/run_all_checks.py "$@"
code=$?

echo
echo "=============================================================="
if [ "$code" -eq 0 ]; then
  echo " 结论：全部通过。"
  echo " 你没有用任何 API Key，也没有联网。"
else
  echo " 结论：有未通过项（exit=$code）。"
  echo " 上面标 ❌ 的那一项就是原因；先看它输出的最后一行。"
fi
echo "=============================================================="
exit "$code"
