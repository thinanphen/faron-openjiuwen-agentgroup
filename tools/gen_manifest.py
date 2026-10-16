#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成仓库内提交物的 SHA256 清单（R4-P2-1 / 任务台账 P2-1）。

用途：给提交包一份「材料完整性凭证」。评委若想核验「我收到的包是否被改过」，
     可以拿这份清单逐文件比对。

用法：
    python tools/gen_manifest.py                 # 写入 资料/提交物清单.json
    python tools/gen_manifest.py --check         # 只校验，不写入（CI / 干净 clone 重跑用）
    python tools/gen_manifest.py --json          # 清单打印到 stdout

设计要点：
  1. **排除项必须在文档里写明理由**（见 EXCLUDE 的注释），不能默默跳过。
  2. 输出**按路径排序**，保证同一份代码在不同机器上产出逐字节一致的清单
     （除 `_generated_at` —— `--check` 模式会忽略该字段）。
  3. 用 `hashlib.blake2b`? 不 —— 用 **SHA256**，因为这是给外部核验用的，
     必须是通用算法。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "资料", "提交物清单.json")

# ---------------------------------------------------------------------------
# 控制台编码兜底
# ---------------------------------------------------------------------------
# 为什么要这个：中文 Windows 的控制台默认 GBK，打印 ✅ / ❌ 这类字符会抛
#   UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'
# 直接用 `python tools/gen_manifest.py` 就能踩到（本轮实测）。
# 处理方式：能改成 UTF-8 就改；改不了则把这些符号降级为 ASCII，
# 保证脚本在任何控制台上都能跑完 —— 不允许因为「打印不出来」而中断校验。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_UNICODE_OK = True
try:
    sys.stdout.write("")
    "✅".encode(sys.stdout.encoding or "utf-8")
except Exception:
    _UNICODE_OK = False

OK = "✅" if _UNICODE_OK else "[OK]"
NG = "❌" if _UNICODE_OK else "[FAIL]"

#: 纳入清单的顶层目录（相对仓库根）
INCLUDE_DIRS = ["提交包", "资料", "源码", "docs", "skill", "tests", "src", "tools"]
#: 纳入的顶层文件（相对仓库根）
INCLUDE_FILES = [
    "README.md", "接手必读.md", "AI工作须知.md", "任务台账.md",
    "requirements.txt", "probe_build.py", "run_offline_demo.py",
    "run_online.py", "conftest.py", "LICENSE",
]

#: 排除项 —— 每一项都写明「为什么不该进清单」
EXCLUDE = {
    # 版本库自身，不属于「提交物」
    ".git": "版本库元数据，非提交物",
    # Python 字节码缓存：随解释器版本变化，无核验价值
    "__pycache__": "Python 字节码缓存，随解释器版本变化",
    # 产出物：每次运行都变，纳入会导致清单永远对不上
    "runtime": "运行产出物（.docx / runlog），每次运行都变；核验其存在性即可",
    # 运行日志：已被 .gitignore（logs/），不是提交物
    "logs": "运行日志（openJiuwen 运行期输出）；已被 .gitignore，不属于提交物",
    # 本机暂存
    "_hold": "本机暂存目录；已被 .gitignore",
    # 流程产物：由 `git format-patch` 从提交生成，是「交付方式」而非「交付内容」
    "交付补丁": "由 git format-patch 从提交生成的交付方式，非交付内容",
    # 本清单自身：自引用会导致哈希永远算不出稳定值
    "提交物清单.json": "本清单自身；自引用无法得到稳定哈希",
    # 临时 / 编辑器产物
    ".DS_Store": "macOS 编辑器产物",
    "Thumbs.db": "Windows 缩略图缓存",
}

#: 按扩展名排除的临时文件
EXCLUDE_EXT = {".pyc", ".pyo", ".swp", ".tmp", ".log", ".orig", ".rej"}


def should_skip(name: str) -> bool:
    if name in EXCLUDE:
        return True
    if os.path.splitext(name)[1].lower() in EXCLUDE_EXT:
        return True
    return False


def git_tracked_files() -> list[str] | None:
    """用 `git ls-files` 取「提交物」的权威名单。

    为什么优先用它：提交物 = **仓库跟踪的文件**，而不是「某个目录下的所有文件」。
    手写目录清单容易把未跟踪的临时文件误纳（本轮就差点把 gitignore 的 `logs/` 纳入）。

    返回 None 表示不是 git 仓库 / git 不可用 → 退回目录遍历。
    """
    import subprocess
    try:
        p = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO, capture_output=True, timeout=60,
        )
        if p.returncode != 0:
            return None
        out = p.stdout.decode("utf-8", "replace")
        files = [f for f in out.split("\0") if f]
        return files or None
    except Exception:
        return None


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def sha256_of_git_blob(rel: str) -> tuple[str | None, int | None]:
    """对 **git 内的规范内容**（blob）取 SHA256。

    ⚠️ 为什么不能直接对工作区文件取哈希（本仓库实际踩到的坑）：

        本仓库 `.gitattributes` 声明 `* text=auto eol=lf`（仓库内规范形式为 **LF**），
        但若本机 `core.autocrlf=true`，Git 检出时会转成 **CRLF**。
        于是**同一个提交在不同机器上的工作区字节不同**：

            源码/Legal-Workspace/CHANGELOG.md   工作区 43,699 B  vs  blob 43,393 B（差 306）
            资料/04-产品演示站/demo.html         工作区 531,604 B vs  blob 527,219 B（差 4,385）

        对工作区取哈希 ⇒ 清单**平台相关** ⇒ 在另一台机器（或 Linux / CI）上重跑
        `--check` 会大面积报「变更」，而这**不是仓库被改动**，只是行尾不同。

    **所以：清单记录的是「git 内的内容」，不是「磁盘上的字节」。**
    这样清单在任何平台、任何 `core.autocrlf` 设置下都可比。

    Returns:
        (sha256, bytes)；取不到时返回 (None, None) 交由调用方回退。
    """
    import subprocess
    try:
        p = subprocess.run(
            ["git", "cat-file", "blob", f"HEAD:{rel}"],
            cwd=REPO, capture_output=True, timeout=60,
        )
        if p.returncode != 0:
            return None, None
        data = p.stdout
        return hashlib.sha256(data).hexdigest().upper(), len(data)
    except Exception:
        return None, None


def collect() -> tuple[list[dict], str]:
    """收集清单条目。

    Returns:
        (entries, source) —— source 为 `"git ls-files"` 或 `"目录遍历"`，写进清单便于追溯。
    """
    entries: list[dict] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        rel = rel.replace(os.sep, "/")
        if rel in seen:
            return
        abs_p = os.path.join(REPO, rel)
        if not os.path.isfile(abs_p):
            return
        # 排除规则对「路径上的任意一段」生效（git ls-files 会给出深层路径）
        parts = rel.split("/")
        if any(should_skip(p) for p in parts):
            return
        seen.add(rel)

        # 优先用 git blob（平台无关）；取不到再回退工作区字节
        blob_sha, blob_bytes = sha256_of_git_blob(rel)
        if blob_sha is not None:
            entries.append({
                "path": rel,
                "bytes": blob_bytes,
                "sha256": blob_sha,
                # 便于人工区分：本行哈希取自 git 内规范内容
                "source": "git-blob",
            })
        else:
            entries.append({
                "path": rel,
                "bytes": os.path.getsize(abs_p),
                "sha256": sha256_of(abs_p),
                "source": "working-tree",
            })

    tracked = git_tracked_files()
    if tracked is not None:
        source = "git ls-files"
        for rel in tracked:
            add(rel)
    else:
        source = "目录遍历"
        for f in INCLUDE_FILES:
            add(f)
        for d in INCLUDE_DIRS:
            base = os.path.join(REPO, d)
            if not os.path.isdir(base):
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = sorted(x for x in dirs if not should_skip(x))
                for fn in sorted(files):
                    if should_skip(fn):
                        continue
                    add(os.path.relpath(os.path.join(root, fn), REPO))

    entries.sort(key=lambda e: e["path"])
    return entries, source


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 / 校验仓库内提交物的 SHA256 清单")
    ap.add_argument("--check", action="store_true", help="只校验现有清单是否一致（忽略生成时间）")
    ap.add_argument("--json", action="store_true", help="打印 JSON 到 stdout，不写文件")
    args = ap.parse_args(argv)

    entries, source = collect()
    total = sum(e["bytes"] for e in entries)

    if args.check:
        if not os.path.isfile(OUT):
            print(f"{NG} 清单不存在：{OUT}")
            print("   先生成一次：python tools/gen_manifest.py")
            return 1
        with io.open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        old_map = {e["path"]: (e["bytes"], e["sha256"]) for e in old.get("files", [])}
        new_map = {e["path"]: (e["bytes"], e["sha256"]) for e in entries}
        added = sorted(set(new_map) - set(old_map))
        removed = sorted(set(old_map) - set(new_map))
        changed = sorted(p for p in set(new_map) & set(old_map) if new_map[p] != old_map[p])
        print("=" * 70)
        print("提交物清单校验")
        print("=" * 70)
        print(f"  清单文件: {os.path.relpath(OUT, REPO)}")
        print(f"  清单条目: {len(old_map)}    实际条目: {len(new_map)}")
        print(f"  新增: {len(added)}   删除: {len(removed)}   变更: {len(changed)}")
        for label, items in (("新增", added), ("删除", removed), ("变更", changed)):
            for p in items[:20]:
                print(f"    [{label}] {p}")
        ok = not (added or removed or changed)
        print("\n" + (f"{OK} 一致" if ok else f"{NG} 不一致（清单需重新生成或仓库有未登记改动）"))
        return 0 if ok else 1

    payload = {
        "_说明": "仓库内提交物的 SHA256 清单。用于核验提交材料完整性。",
        "_生成方式": "python tools/gen_manifest.py",
        "_校验方式": "python tools/gen_manifest.py --check",
        "_生成时间": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "_算法": "SHA256（大写十六进制）",
        "_条目来源": source,
        "_排除项及理由": EXCLUDE,
        "_统计": {"files": len(entries), "bytes": total},
        "files": entries,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("=" * 70)
    print("提交物清单已生成")
    print("=" * 70)
    print(f"  输出: {os.path.relpath(OUT, REPO)}")
    print(f"  条目: {len(entries)} 个文件")
    print(f"  体积: {total:,} 字节（{total / 1024 / 1024:.2f} MiB）")
    print(f"  排除: {', '.join(sorted(EXCLUDE))}")
    print("\n  校验：python tools/gen_manifest.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
