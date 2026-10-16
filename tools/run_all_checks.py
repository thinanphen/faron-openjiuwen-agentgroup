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


def _git_dirty() -> list[str]:
    """返回工作区/暂存区有改动的文件；非 git 仓库或取不到时返回 []。"""
    try:
        p = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO, capture_output=True, timeout=60,
        )
        if p.returncode != 0:
            return []
        out = p.stdout.decode("utf-8", "replace")
        return [ln[3:].strip() for ln in out.splitlines() if len(ln) > 3]
    except Exception:
        return []


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
    # ⚠️ 顺序很重要：清单一致性**必须排在最前**。
    #    因为「端到端」会生成新的 runtime/deliverable_* 与 runlog_*，
    #    从而改变工作区 —— 若把清单检查排在后面，第一次跑必然报「不一致」。
    #    （本轮实测踩到：第一次 8/9，第二次才 9/9。这正是顺序依赖。）
    ("提交物清单一致性", [sys.executable, "tools/gen_manifest.py", "--check"], True),
    ("零依赖验证 (6 项)", [sys.executable, "tests/verify_zero_dep.py"], True),
    ("自检测试向量 (31 组)", [sys.executable, "tests/test_citation_audit.py"], True),
    ("装配防线 (9 组)", [sys.executable, "tests/test_assembly.py"], True),
    ("构建探针 probe_build", [sys.executable, "probe_build.py"], True),
    ("Skill 规范符合性 (14 条)", [sys.executable, "skill/citation-audit/scripts/verify_skill_spec.py"], True),
    ("Skill 零依赖", [sys.executable, "skill/citation-audit/scripts/verify_no_deps.py"], True),
    ("Skill 演示（应 exit=1：库外条号被点名）",
     [sys.executable, "skill/citation-audit/scripts/audit_citations.py", "--demo"], False),
    # 放最后：它会写新文件
    ("端到端 run_offline_demo（会生成新的 runtime 产出）",
     [sys.executable, "run_offline_demo.py"], True),
]


def prune_runtime() -> list[str]:
    """清理 runtime/ 里**未跟踪**的历史产出；**已跟踪的取证物一律不动**。

    ── 为什么这样设计（前几版都错了）────────────────────────────────
    早期版本「按时间戳排序，保留最新一个，其余全删」，有两个致命问题：

    ① **`files[:-1]` 在只有 1 个文件时是空操作** —— 若已提交的恰好是唯一一个，
       它既不会被删也不会被恢复，逻辑形同虚设（本轮实测踩到）。
    ② **更根本：不该删已提交的取证物。** `runtime/deliverable_*.docx` 是
       「第9999条被点名」的**物证**（见 runtime/README.md），是**有意提交**的。
       一个验证脚本**没有权力**把它删掉 —— 这会改变仓库内容，并让紧随其后的
       「清单一致性」检查因工作区变脏而报错。

    ── 现在的规则 ────────────────────────────────────────────────
      · **已跟踪的文件：不碰**（它是取证物，属于提交内容）
      · **未跟踪的文件：删除**（它们只是本地跑 demo 的副产品）

    这样 `run_all_checks.py` 不再改变任何已提交内容，
    「清单一致性」也就不会因为清理动作而失败。
    """
    import glob
    import subprocess

    rt = os.path.join(REPO, "runtime")
    if not os.path.isdir(rt):
        return []

    # 一次取全部未跟踪文件，避免逐个 git 调用
    try:
        p = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=REPO, capture_output=True, timeout=60,
        )
        untracked = set(
            f for f in p.stdout.decode("utf-8", "replace").split("\0") if f
        )
    except Exception:
        return []

    handled: list[str] = []
    for pattern in ("deliverable_*.docx", "runlog_*.json"):
        for f in sorted(glob.glob(os.path.join(rt, pattern))):
            name = os.path.basename(f)
            rel = f"runtime/{name}"
            if rel in untracked:
                try:
                    os.remove(f)
                    handled.append(f"{name}（未跟踪，已删除）")
                except OSError:
                    pass
            # 已跟踪 → 什么都不做（取证物，属于提交内容）
    return handled


print("=" * 74)
print("agent-group 侧 · 全部验证")
print("=" * 74)

# ⚠️ 先清理 runtime/：`run_offline_demo.py` 每次运行都生成一对带时间戳的文件，
#    而「清单一致性」排在第一位 —— 若不清到「只剩最新一组」，
#    清单检查必然报不一致（工作区与清单对不上）。
#    本轮实测：不先清理时 8/9，先清理后 9/9。这是**顺序 + 状态**双重依赖。
pre_pruned = prune_runtime()
if pre_pruned:
    print(f"{C['y']}预处理{C['x']} runtime/ 历史产出 {len(pre_pruned)} 个（只保留最新一组）")

# ---------------------------------------------------------------------------
# 闸门：工作区必须干净
# ---------------------------------------------------------------------------
# 为什么必需：本轮（第五、六轮）「清单不一致」反复出现，**报 9 次、根因各异**，
# 其中相当一部分是我自己的流程问题 ——
# 「改了文档 → 忘了重新生成清单 → 提交推送」，或「清理脚本删掉了已提交的文件」。
# 这类问题本机怎么跑都可能看不出来，只有**别人 clone 时才暴露**。
#
# 所以：**工作区不干净就直接判失败**，并明确告诉使用者该做什么。
# 一个「允许在脏工作区上判绿」的验证脚本，等于没有验证。
dirty = _git_dirty()
if dirty:
    print()
    print(f"{C['r']}❌{C['x']} 工作区不干净（{len(dirty)} 项），拒绝给出「全部通过」的结论")
    for p in dirty[:12]:
        print(f"   {C['d']}{p}{C['x']}")
    if len(dirty) > 12:
        print(f"   {C['d']}… 另有 {len(dirty) - 12} 项{C['x']}")
    print()
    print("   → 清单比对的是 **git HEAD 的内容**；通常意味着：")
    print("     ① 改了文件但**没有重新生成清单** → 跑 `python tools/gen_manifest.py`")
    print("     ② 改了文件但**没有提交** → 先提交")
    print("   → 处理后再跑本脚本；**不要在脏工作区上宣告验证通过**。")
    print()
    # 仍然继续跑其余项，便于一次看到全部信息，但最终必然 exit=1
    dirty_gate_failed = True
else:
    dirty_gate_failed = False

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
if dirty_gate_failed:
    print(f"结果：{passed} 通过 / {failed + 1} 未通过 / 共 {len(STEPS) + 1}（含「工作区干净」闸门）")
else:
    print(f"结果：{passed} 通过 / {failed} 未通过 / 共 {len(STEPS)}")
print("=" * 74)

# 跑完 demo 又会生成一组，再清理一次，保持「只剩最新一组」的不变式
post_pruned = prune_runtime()
if post_pruned:
    print()
    print(f"已清理 runtime/ 的 {len(post_pruned)} 个历史产出（只保留最新一组）：")
    for f in post_pruned:
        print(f"   - {f}")

if failed == 0:
    print()
    print("另需单独跑（TypeScript 侧，在 Legal-Workspace 仓库）：")
    print("   npm test            → 期望 75 passed (75)")
    print("   npm run build       → 期望 exit=0")
    print("   node scripts/check-ui-copy.mjs  → 期望 6/6")

sys.exit(1 if (failed or dirty_gate_failed) else 0)
