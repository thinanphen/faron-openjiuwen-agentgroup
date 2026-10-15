#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法条引用自检 Skill —— 自包含 CLI（零三方依赖）。

设计要点：**按文件路径加载纯函数模块**，不 import `faron_agentgroup` 包。
原因：包的 `__init__.py` 会连带 import 依赖 openJiuwen 的工具模块，
那样本 Skill 就无法在「只有 Python 标准库」的环境里运行 —— 而这正是它最大的价值。

用法：
    python scripts/audit_citations.py --demo
    python scripts/audit_citations.py --body-file draft.md --refs-file refs.json --json
    python scripts/audit_citations.py --body "依§1125与§9999" --refs-json '[{"title":"United States Code, Title 15","article_no":"§1125"}]'
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
#: 按优先级尝试的模块目录：
#:   ① 本 Skill 自带的副本（分发后独立可用）
#:   ② 仓库根的 src/faron_agentgroup（仓库内直接运行）
#:   ③ 本 Skill 根下的 src/faron_agentgroup
#:   ④ scripts 同目录
_CANDIDATE_DIRS = [
    os.path.join(_HERE, "faron_agentgroup"),
    os.path.join(_HERE, "..", "..", "..", "src", "faron_agentgroup"),
    os.path.join(_HERE, "..", "src", "faron_agentgroup"),
    _HERE,
]


def _load_pure(module_name: str, filename: str):
    """按文件路径加载纯函数模块（绕过包 __init__，从而避开框架依赖）。"""
    for d in _CANDIDATE_DIRS:
        path = os.path.abspath(os.path.join(d, filename))
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit(
        f"找不到 {filename}。\n"
        f"已尝试：\n" + "\n".join(f"  - {os.path.abspath(os.path.join(d, filename))}" for d in _CANDIDATE_DIRS)
    )


_CIT = _load_pure("_ca_citation", "citation.py")

#: kg.py 可选（只有需要案由图谱时才用）
try:
    _KG = _load_pure("_ca_kg", "kg.py")
except SystemExit:
    _KG = None


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------

def audit(
    body: str,
    returned_refs: List[Dict[str, Any]],
    law_names: Optional[List[str]] = None,
    law_names_display: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """执行两段确定性自检。

    Args:
        body: 待校验正文。
        returned_refs: **本次工具真实返回**的法条列表（第一段的唯一判据）。
        law_names: 案由图谱请求权基础法名（匹配用，可含别名）；给了才做第二段。
        law_names_display: 展示用主名；缺省沿用 law_names。

    Returns:
        含 total / covered / ok / unmatched / report_markdown，
        以及在给了 law_names 时的 applicability 明细。
    """
    a = _CIT.audit_citations(body, returned_refs)
    out: Dict[str, Any] = a.to_dict()
    out["report_markdown"] = _CIT.audit_report(a)

    if law_names:
        ap = _CIT.audit_applicability(returned_refs, law_names, law_names_display)
        out["applicability"] = ap.to_dict()
        out["applicability_report_markdown"] = _CIT.applicability_report(ap)

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEMO_BODY = (
    "依据《民法》第五百二十二条，本案应支持原告请求。\n"
    "另依第百三条の二，被告应承担违约责任。\n"
    "并请参照第9999条（本条并不存在于本地法库）。"
)
DEMO_REFS = [
    {"title": "民法", "article_no": "第五百二十二条", "source": "e-Gov", "excerpt": ""},
    {"title": "民法", "article_no": "第百三条の二", "source": "e-Gov", "excerpt": ""},
]


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="法条引用自检（确定性，不调用大模型）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--body", help="待校验正文")
    ap.add_argument("--body-file", help="从文件读取正文")
    ap.add_argument("--refs-json", help="工具真实返回的法条（JSON 数组字符串）")
    ap.add_argument("--refs-file", help="从文件读取工具真实返回的法条（JSON）")
    ap.add_argument("--law-names", nargs="*", default=None, help="案由图谱请求权基础法名（启用第二段）")
    ap.add_argument("--law-names-display", nargs="*", default=None, help="展示用主名")
    ap.add_argument("--demo", action="store_true", help="跑内建演示（含故意埋的库外条号）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.demo:
        body, refs = DEMO_BODY, DEMO_REFS
        if not args.law_names:
            args.law_names = ["民法", "Civil Code"]
            args.law_names_display = ["民法"]
    else:
        if args.body_file:
            body = _read(args.body_file)
        elif args.body:
            body = args.body
        else:
            ap.error("需要 --body / --body-file / --demo 之一")
            return 2

        if args.refs_file:
            refs = json.loads(_read(args.refs_file))
        elif args.refs_json:
            refs = json.loads(args.refs_json)
        else:
            refs = []

    if not isinstance(refs, list):
        ap.error("--refs-json / --refs-file 必须是 JSON 数组")
        return 2

    result = audit(body, refs, args.law_names, args.law_names_display)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("法条引用自检 · 确定性规则校验（不调用任何大模型）")
        print("=" * 70)
        print(f"\n正文引用 {result['total']} 处（去重），命中 {result['covered']} 处\n")
        print(result["report_markdown"])
        if "applicability_report_markdown" in result:
            print()
            print(result["applicability_report_markdown"])
        print()
        print("=" * 70)
        if result["ok"]:
            print("结论：全部引用均已获得工具返回凭证。")
        else:
            print(f"结论：{len(result['unmatched'])} 处引用**未获凭证**，请人工核实或删除后再采用：")
            for t in result["unmatched"]:
                print(f"  · {t}")
        print("=" * 70)

    # 退出码：有未覆盖项时返回 1，便于在 CI / 流水线里当闸门用
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
