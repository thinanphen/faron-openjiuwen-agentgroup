#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证法条引用自检 Skill 在**无三方依赖**环境下可用。

做法：拦截所有非标准库 import（除 os/sys/json/re/argparse 等），
再跑一次 CLI。若通过，则 SKILL.md 里「零三方依赖」的承诺成立。

运行：
    python skill/citation-audit/scripts/verify_no_deps.py
"""

from __future__ import annotations

import builtins
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "audit_citations.py")

#: 允许的顶层模块（标准库白名单；按实际 import 需要最小化）
ALLOWED = {
    "os", "sys", "json", "re", "argparse", "typing", "dataclasses",
    "importlib", "collections", "itertools", "functools", "textwrap",
    "enum", "pathlib", "warnings", "types", "abc", "copy", "math",
    "unicodedata", "string", "io", "contextlib", "operator", "bisect",
    "heapq", "decimal", "fractions", "statistics", "datetime", "time",
    "hashlib", "base64", "binascii", "struct", "codecs", "locale",
    "__future__", "_ca_citation", "_ca_kg", "audit_citations",
}


def main() -> int:
    print("=" * 70)
    print("法条引用自检 Skill · 零三方依赖验证")
    print("=" * 70)

    # ---- 1) 静态检查：citation.py / kg.py 的 import ----
    print("\n[1] 纯函数模块的 import 清单")
    for fn in ("citation.py", "kg.py"):
        p = os.path.abspath(os.path.join(HERE, "..", "..", "..", "src", "faron_agentgroup", fn))
        if not os.path.isfile(p):
            print(f"    ! 找不到 {fn}，跳过")
            continue
        names = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("from ") and " import " in s:
                    names.append(s.split()[1].split(".")[0])
                elif s.startswith("import "):
                    names.append(s.split()[1].split(".")[0].rstrip(","))
        bad = sorted({n for n in names if n not in ALLOWED})
        status = "✅ 全部在标准库白名单内" if not bad else f"❌ 疑似三方依赖：{bad}"
        print(f"    {fn}: {sorted(set(names))}")
        print(f"           → {status}")

    # ---- 2) 运行时检查：在屏蔽三方 import 的子进程里跑 CLI ----
    print("\n[2] 屏蔽**非标准库** import 后运行 CLI")
    # 用哨兵包住 JSON，避免依赖 runpy 的退出码传递方式，也便于定位解析边界
    SENTINEL = "___AUDIT_JSON_BEGIN___"
    # 判定方式改用 sys.stdlib_module_names（Python 3.10+ 自带的权威标准库名单），
    # 比手写白名单严谨：不会漏掉 enum/builtins 这类被间接 import 的模块，
    # 也不会因为将来标准库变动而失效。
    code = f'''
import builtins, sys
_orig = builtins.__import__
STDLIB = set(sys.stdlib_module_names)
#: 本 Skill 自身的模块 + 编译期伪模块（不是三方依赖）
LOCAL = {{"audit_citations", "__future__"}}
BLOCKED = []
def guard(name, *a, **k):
    # 相对导入（from .x import y）时 level>0 —— 那是标准库包的内部结构，
    # __import__ 签名是 (name, globals, locals, fromlist, level)，level 在第 4 个位置参数。
    level = a[3] if len(a) > 3 else 0
    if isinstance(level, int) and level > 0:
        return _orig(name, *a, **k)
    top = (name or "").split(".")[0]
    if not top:
        return _orig(name, *a, **k)
    # 放行：标准库、本 Skill 自身模块、私有/内部模块（_ca_citation 等）
    if top not in STDLIB and top not in LOCAL and not top.startswith("_"):
        BLOCKED.append(name)
        raise ModuleNotFoundError("No module named " + repr(name))
    return _orig(name, *a, **k)
builtins.__import__ = guard
sys.argv = ["audit_citations.py", "--demo", "--json"]
sys.path.insert(0, {HERE!r})
print({SENTINEL!r})
import audit_citations
try:
    rc = audit_citations.main(["--demo", "--json"])
except SystemExit as e:
    rc = e.code if isinstance(e.code, int) else 0
builtins.__import__ = _orig
if BLOCKED:
    print("BLOCKED_IMPORTS:" + ",".join(sorted(set(BLOCKED))), file=sys.stderr)
    raise SystemExit(97)
raise SystemExit(rc or 0)
'''
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # 必须显式指定 encoding：Windows 上 text=True 默认按系统 locale（gbk）解码，
    # 而自检输出含中文，会抛 UnicodeDecodeError。
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=120)
    out = proc.stdout or ""
    err = (proc.stderr or "").strip()

    if "BLOCKED_IMPORTS:" in err:
        blocked = err.split("BLOCKED_IMPORTS:", 1)[1].strip()
        print(f"    ❌ 运行时尝试了非标准库 import：{blocked}")
        print("       → 「零三方依赖」承诺不成立")
        return 1

    if proc.returncode not in (0, 1):
        print(f"    ❌ CLI 异常退出 code={proc.returncode}")
        print(err[-800:])
        return 1

    if SENTINEL not in out:
        print("    ❌ 未捕获到哨兵，无法定位 JSON")
        print(f"       returncode={proc.returncode}")
        print(f"       stdout[:400]={out[:400]!r}")
        print(f"       stderr[-400:]={err[-400:]!r}")
        return 1
    payload = out.split(SENTINEL, 1)[1].strip()

    import json as _json
    try:
        data = _json.loads(payload)
    except Exception as exc:
        print(f"    ❌ 输出不是合法 JSON：{exc}")
        print(f"       returncode={proc.returncode}")
        print(f"       stdout[:400]={out[:400]!r}")
        print(f"       stderr[-600:]={err[-600:]!r}")
        return 1

    print(f"    ✅ CLI 正常运行（exit={proc.returncode}）")
    print(f"       total={data['total']} covered={data['covered']} ok={data['ok']}")
    print(f"       unmatched={data['unmatched']}")
    assert data["unmatched"] == ["第9999条"], data["unmatched"]
    print("       ✅ 库外条号「第9999条」被正确点名")

    print("\n" + "=" * 70)
    print("结论：本 Skill **不需要任何三方依赖**（含 openJiuwen）即可运行。")
    print("      这就是「零 API Key、本地可复现」的真实适用范围。")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
