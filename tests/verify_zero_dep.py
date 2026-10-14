# -*- coding: utf-8 -*-
"""验证「零依赖复现路径」在**没装 openJiuwen** 的机器上真的能跑。

做法：用 import hook 拦截所有 openjiuwen* 的 import 并抛 ModuleNotFoundError，
以此模拟评委的干净环境。若本脚本通过，则 README 与 docs/05 中
「两段确定性自检零 API Key、零框架依赖可复现」的承诺成立（修 E12）。

⚠️ 关键细节：依赖 openJiuwen 的工具与编排模块，`faron_agentgroup/__init__.py`
会连带 import。因此**零依赖路径必须绕过包**，改为按文件路径直接加载
`citation.py` 与 `kg.py`（它们本身是纯函数模块，只用标准库）。

运行：
    python tests/verify_zero_dep.py
"""

from __future__ import annotations

import builtins
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

_orig_import = builtins.__import__
BLOCKED = []


def _blocking_import(name, *args, **kwargs):
    if name == "openjiuwen" or name.startswith("openjiuwen."):
        BLOCKED.append(name)
        raise ModuleNotFoundError(f"No module named '{name}'")
    return _orig_import(name, *args, **kwargs)


def _load_by_path(mod_name: str, rel_path: str):
    """按文件路径直接加载模块，绕过包 `__init__.py`。"""
    path = os.path.join(SRC, rel_path)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("=" * 74)
    print("零依赖复现路径验证（模拟评委干净机器：屏蔽全部 openjiuwen* import）")
    print("=" * 74)

    builtins.__import__ = _blocking_import
    try:
        # ---- 1) 两个纯函数模块可按路径加载 ----
        citation = _load_by_path("_zd_citation", "faron_agentgroup/citation.py")
        kg = _load_by_path("_zd_kg", "faron_agentgroup/kg.py")
        print("[1] ✓ citation.py / kg.py 在无框架环境下可加载（按文件路径，绕过包 __init__）")

        # ---- 2) 图谱可用 ----
        sk = kg.KG.skeleton("涉外合资经营合同纠纷")
        assert sk is not None, "图谱未命中案由"
        assert len(sk["elements"]) == 5, len(sk["elements"])
        print(f"[2] ✓ 图谱可用：案由={sk['case']}，要件 {len(sk['elements'])} 个，"
              f"请求权基础 {len(sk['lawNamesDisplay'])} 部")

        # ---- 3) 第一段自检可用（含反例点名）----
        refs = [{"title": "民法", "article_no": "第五百二十二条",
                 "source": "e-Gov", "excerpt": ""}]
        body = "依据第五百二十二条与第9999条，本案应支持原告请求。"
        a = citation.audit_citations(body, refs)
        assert a.total == 2, a.total
        assert a.covered == 1, a.covered
        assert a.unmatched == ["第9999条"], a.unmatched
        print(f"[3] ✓ 第一段自检可用：{a.covered}/{a.total} 命中，点名 {a.unmatched}")

        # ---- 4) 第二段自检可用（G12 修复后无中英名误报）----
        a2 = citation.audit_applicability(refs, sk["lawNames"], sk["lawNamesDisplay"])
        assert "民法" in a2.in_scope and not a2.out_of_scope, a2.to_dict()
        print(f"[4] ✓ 第二段自检可用：in_scope={a2.in_scope}，out_of_scope={a2.out_of_scope}")

        rep = citation.audit_report(a)
        assert "第9999条" in rep
        print("[5] ✓ 自检报告可渲染（含未覆盖项点名）")

        # ---- 5) 确认全程没有尝试 import 框架 ----
        assert not BLOCKED, (
            f"复现路径上发生了框架 import（E12 回归）：{sorted(set(BLOCKED))}"
        )
        print("[6] ✓ 全程零 openjiuwen import —— 零依赖承诺成立")

    finally:
        builtins.__import__ = _orig_import
        for m in ("_zd_citation", "_zd_kg"):
            sys.modules.pop(m, None)

    print()
    print("=" * 74)
    print("结论：两段确定性自检**不需要 openJiuwen、不需要 API Key** 即可复现。")
    print("      复现方式是按文件路径加载 citation.py / kg.py（绕过包 __init__）。")
    print("      团队装配与工具调用仍需 pip install -r requirements.txt。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
