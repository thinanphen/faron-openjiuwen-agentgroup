#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验本 Skill 是否符合 JiuwenSwarm Skill 规范（R4-P2-2）。

规范来源（实查 2026-10-15）：
  https://raw.githubusercontent.com/openJiuwen-ai/jiuwenswarm/develop/docs/en/Skills.md

规范要求（逐条落成断言）：
  1. Skill 是一个文件夹，至少含 `SKILL.md`（可选 `references/`、`scripts/`）
  2. `SKILL.md` **必须以 `---` 开头的 YAML frontmatter 块起始**
  3. frontmatter 必须同时含 **`name` 与 `description`**
     （原文：bare .md files or directories without a valid SKILL.md frontmatter are not importable）
  4. `name` 应唯一、优先 kebab-case
  5. `description` 里 **避免 `<` 与 `>`**
  6. **目录名必须与 frontmatter 的 `name` 一致**，否则导入被拒
     （错误码 `SKILL_SYNC_INVALID_PAYLOAD`：directory name mismatch with frontmatter name）
  7. 可选字段：`version` / `author` / `tags`（YAML 列表或逗号串）/ `allowed_tools`

为什么要有这个脚本：
  「符合规范」如果只是文档里的一句话，就无法核验。
  把它变成可执行断言，才能在任何机器上一条命令确认可导入性。

用法：
    python skill/citation-audit/scripts/verify_skill_spec.py
退出码：0 = 全部通过；1 = 有未通过项
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
DIR_NAME = os.path.basename(SKILL_DIR)

# 控制台编码兜底（中文 Windows 默认 GBK）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_OK = True
try:
    "✅".encode(sys.stdout.encoding or "utf-8")
except Exception:
    _OK = False
OK = "✅" if _OK else "[OK]"
NG = "❌" if _OK else "[FAIL]"

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name, detail))


# ---------------------------------------------------------------------------
# 解析 frontmatter
# ---------------------------------------------------------------------------
raw = ""
if os.path.isfile(SKILL_MD):
    with open(SKILL_MD, "r", encoding="utf-8") as f:
        raw = f.read()

fm: dict[str, str] = {}
body = raw
fm_ok = False
fm_err = ""

if raw:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", raw, re.S)
    if m:
        fm_ok = True
        block = m.group(1)
        body = raw[m.end():]
        for line in block.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    else:
        fm_err = "文件未以 `---` 开头的 frontmatter 块起始"

# ---------------------------------------------------------------------------
# 逐条校验
# ---------------------------------------------------------------------------
check("SKILL.md 存在", os.path.isfile(SKILL_MD), SKILL_MD)
check("以 `---` 开头的 YAML frontmatter 块起始", fm_ok, fm_err)
check("frontmatter 含 `name`", "name" in fm, f"name={fm.get('name', '(缺失)')}")
check("frontmatter 含 `description`", "description" in fm,
      f"description 长度={len(fm.get('description', ''))}")

nm = fm.get("name", "")
check("`name` 为非空字符串", bool(nm), nm)
check("`name` 为 kebab-case（推荐）", bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", nm)) if nm else False, nm)
check("**目录名与 frontmatter 的 `name` 一致**（否则导入被拒）", nm == DIR_NAME,
      f"目录={DIR_NAME}  name={nm}")

desc = fm.get("description", "")
check("`description` 不含 `<` 或 `>`（规范明确要求避免）",
      ("<" not in desc and ">" not in desc), desc[:60])

# 可选字段的形态
tags_raw = fm.get("tags", "")
check("`tags`（可选）为 YAML 列表或逗号串",
      (not tags_raw) or tags_raw.startswith("[") or ("," in tags_raw),
      tags_raw)

# 目录结构：scripts/ 可选；有则列出
scripts = os.path.join(SKILL_DIR, "scripts")
check("`scripts/`（可选）结构存在", os.path.isdir(scripts),
      ", ".join(sorted(os.listdir(scripts))) if os.path.isdir(scripts) else "(无)")

# body 非空且含关键小节
check("skill body 非空", len(body.strip()) > 200, f"{len(body.strip())} 字符")
for sec in ("这个 Skill 解决什么问题", "何时使用", "已知边界"):
    check(f"body 含关键小节「{sec}」", sec in body)

# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
print("=" * 74)
print("JiuwenSwarm Skill 规范符合性校验")
print("=" * 74)
print(f"  Skill 目录: {os.path.relpath(SKILL_DIR)}")
print(f"  规范来源  : jiuwenswarm docs/en/Skills.md")
print()
failed = 0
for ok, name, detail in results:
    if not ok:
        failed += 1
    line = f"{OK if ok else NG} {name}"
    print(line)
    if detail and not ok:
        print(f"      → {detail}")
print()
print("=" * 74)
print(f"结果：{len(results) - failed} 通过 / {failed} 未通过 / 共 {len(results)}")
print("=" * 74)

if failed == 0:
    print()
    print("结论：本 Skill **符合 JiuwenSwarm Skill 规范**，可通过「导入本地 Skill」装载：")
    print(f"  左侧栏 → Skills → Import local skill → 填入绝对路径：")
    print(f"    {SKILL_DIR}")
    print("  （规范要求绝对路径或 ~/ 路径；相对路径会被拒绝）")
    print("  亦可手工拷贝到：~/.jiuwenswarm/agent/workspace/skills/")

sys.exit(1 if failed else 0)
