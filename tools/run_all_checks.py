#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键跑完 agent-group 侧的全部验证（供人 / 同伴的 AI 一条命令复核）。

用法：
    python tools/run_all_checks.py

覆盖：
  A. Python 测试        —— verify_zero_dep / test_citation_audit / test_assembly
  B. 构建探针           —— probe_build.py（逐成员 spec 解析）
  C. 端到端             —— run_offline_demo.py（出 .docx）
  D. Skill 自证         —— 规范符合性 / 零依赖 / 演示
  E. 提交物清单一致性   —— gen_manifest.py --check
"""

from __future__ import annotations

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

C = {
    "g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "d": "\033[2m", "x": "\033[0m",
}


def run(label: str, args: list[str], expect_ok: bool = True) -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=600)
    ok = (p.returncode == 0) if expect_ok else True
    # 提取有信息量的摘要行：优先「结果：/结论：/✓ 一致」，否则取最后一条非分隔线
    tail = ""
    lines = [l.strip() for l in (p.stdout or "").splitlines() if l.strip()]
    for key in ("结果：", "结论：", "一致"):
        for l in lines:
            if key in l and not set(l) <= set("=─- "):
                tail = l
                break
        if tail:
            break
    if not tail:
        for l in reversed(lines):
            if not set(l) <= set("=─- "):
                tail = l
                break
    return ok, tail


STEPS: list[tuple[str, list[str], bool]] = [
    ("零依赖验证 (6 项)", [sys.executable, "tests/verify_zero_dep.py"], True),
    ("自检测试向量 (31 组)", [sys.executable, "tests/test_citation_audit.py"], True),
    ("装配防线 (9 组)", [sys.executable, "tests/test_assembly.py"], True),
    ("构建探针 probe_build", [sys.executable, "probe_build.py"], True),
    ("端到端 run_offline_demo", [sys.executable, "run_offline_demo.py"], True),
    ("Skill 规范符合性 (14 条)", [sys.executable, "skill/citation-audit/scripts/verify_skill_spec.py"], True),
    ("Skill 零依赖", [sys.executable, "skill/citation-audit/scripts/verify_no_deps.py"], True),
    ("Skill 演示（应 exit=1：库外条号被点名）",
     [sys.executable, "skill/citation-audit/scripts/audit_citations.py", "--demo"], False),
    ("提交物清单一致性", [sys.executable, "tools/gen_manifest.py", "--check"], True),
]

print("=" * 74)
print("agent-group 侧 · 全部验证")
print("=" * 74)

passed = failed = 0
for label, args, expect in STEPS:
    ok, tail = run(label, args, expect)
    if ok:
        passed += 1
        print(f"{C['g']}✅{C['x']} {label}")
    else:
        failed += 1
        print(f"{C['r']}❌{C['x']} {label}")
    if tail:
        print(f"   {C['d']}{tail[:110]}{C['x']}")

print()
print("=" * 74)
print(f"结果：{passed} 通过 / {failed} 未通过 / 共 {len(STEPS)}")
print("=" * 74)
if failed == 0:
    print()
    print("另需单独跑（TypeScript 侧，在 Legal-Workspace 仓库）：")
    print("   npm test            → 期望 74 passed")
    print("   npm run build       → 期望 exit=0")
    print("   node scripts/check-ui-copy.mjs  → 期望 6/6")

sys.exit(1 if failed else 0)
