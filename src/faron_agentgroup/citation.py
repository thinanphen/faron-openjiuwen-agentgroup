# -*- coding: utf-8 -*-
"""引用解析与确定性自检 —— 与「法元」官方实现逐条对齐。

【对齐来源】`Legal-Workspace/src/lib/agent.ts`（feature/赛事版 @ 0.7.2）
    - `extractCitationTokens()`  第 609–622 行
    - `normArticleNo()`          第 625–627 行
    - `articleCovers()`          第 630–635 行
    - `auditCitations()`         第 649–654 行
    - `CITE_PATTERNS_NOTE`       第 604–606 行

【为什么必须对齐】
    Python 侧如果不复刻官方规则，就会出现「TS 端判有效、Python 端判无效」
    的双端漂移，交付物口径自相矛盾。本模块是唯一来源（single source of truth）
    的 Python 镜像，配套 `tests/test_citation_audit.py` 用同一组向量双向校验。

【关键性质】纯函数：不调用模型；结论只依赖 (正文, 工具真实返回集合)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

# ---------------------------------------------------------------------------
# 官方规则（逐字复刻）
# ---------------------------------------------------------------------------

#: 自检方法脚注（官方 CITE_PATTERNS_NOTE，逐字）
CITE_PATTERNS_NOTE = (
    "自检为确定性规则校验：按中文/日文「第X条(之Y/のY)」、美国法典「§NN」等条文号格式识别正文引用，"
    "并判定每条引用是否能在「本次工具真实返回」的法条中找到对应条文号；未覆盖项仅提示人工核实，不视为有效引用。"
)

#: 官方正则（agent.ts 第 610–611 行）
#:   第[0-9〇零一二三四五六七八九十百千万]+条(?:(?:之|の|ノ)[...]+)?   —— 中日文条号（含「之/の/ノ」分条）
#:   §\s*\d+(?:[.\-]\d+)?(?:\(\d+\))?                              —— 美国法典（含 1125(a) / 101-1 变体）
CITATION_RE = re.compile(
    r"第[0-9〇零一二三四五六七八九十百千万]+条"
    r"(?:(?:之|の|ノ)[0-9〇零一二三四五六七八九十百千万]+)?"
    r"|§\s*\d+(?:[.\-]\d+)?(?:\(\d+\))?"
)


def extract_citation_tokens(text: str) -> List[str]:
    """从文本中抽取**去重后**的条文号引用 token。

    对齐 agent.ts `extractCitationTokens()`：去空白、按出现先后去重。

    >>> extract_citation_tokens("依第103条与§1125(a)，另见第103条。")
    ['第103条', '§1125(a)']
    """
    seen: Set[str] = set()
    out: List[str] = []
    for m in CITATION_RE.finditer(text or ""):
        t = re.sub(r"\s+", "", m.group(0))
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def norm_article_no(s: Optional[str]) -> str:
    """规范化条文号：去空白、去全半角括号。对齐 agent.ts `normArticleNo()`。"""
    if not s:
        return ""
    return re.sub(r"[（）()]", "", re.sub(r"\s+", "", s))


def article_covers(article_no: Optional[str], token: str) -> bool:
    """条文号是否「覆盖」引用 token。

    对齐 agent.ts `articleCovers()`：**完全相等**，或
    **条文号以该引用为前缀**（如「第一百四十三条」覆盖「第一百四十三条第一款」）。

    >>> article_covers("第一百四十三条", "第一百四十三条")
    True
    >>> article_covers("第一百四十三条第二款", "第一百四十三条")
    True
    >>> article_covers("第一百四十三条", "第一百四十四条")
    False
    """
    a = norm_article_no(article_no)
    t = norm_article_no(token)
    if not a or not t:
        return False
    return a == t or (len(t) < len(a) and a.startswith(t))


# ---------------------------------------------------------------------------
# 第一段自检：引用是否真实存在
# ---------------------------------------------------------------------------

@dataclass
class CitationAudit:
    """对齐 agent.ts `CitationAudit`。"""

    ok: bool
    total: int          # 识别到的条文号引用数（去重）
    covered: int        # 能在工具返回法条中找到的引用数
    unmatched: List[str]  # 未找到的引用清单

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "method": "deterministic_rule",
            "total": self.total,
            "covered": self.covered,
            "unmatched": self.unmatched,
            "note": CITE_PATTERNS_NOTE,
        }


def audit_citations(body_text: str, refs: Sequence) -> CitationAudit:
    """对正文做确定性引用自检（第一段）。

    正文中每一条条文号引用都必须能对应到**本次工具真实返回**的法条。
    这是代码层面的硬校验——不依赖模型「说自己检查过」，而是规则必然执行。

    Args:
        body_text: 文书正文。
        refs: 本次工具真实返回的法条，每项需有 `article_no` 属性或 dict 键。

    Returns:
        CitationAudit
    """
    tokens = extract_citation_tokens(body_text)

    def _no(r) -> Optional[str]:
        if isinstance(r, dict):
            return r.get("article_no")
        return getattr(r, "article_no", None)

    nos = [_no(r) for r in refs]
    covered = [t for t in tokens if any(article_covers(n, t) for n in nos)]
    unmatched = [t for t in tokens if not any(article_covers(n, t) for n in nos)]
    return CitationAudit(ok=not unmatched, total=len(tokens),
                         covered=len(covered), unmatched=unmatched)


def audit_report(a: CitationAudit) -> str:
    """把自检结果渲染成 Markdown。对齐 agent.ts `auditReport()`。"""
    lines = [
        f"- 识别到条文号引用 {a.total} 处（去重）",
        f"- 与「本次工具真实返回」法条对应：{a.covered}/{a.total}",
    ]
    if a.ok:
        lines.append("- 自检通过：正文引用均可回溯到本次检索/工具返回的本地法条（未发现编造引用）")
    else:
        joined = "、".join(f"「{t}」" for t in a.unmatched)
        lines.append(
            "- 以下引用未在工具返回中找到对应条文"
            "（可能来自用户材料原文或模型笔误，请人工核实后再采用）：\n  " + joined
        )
    lines.append(f"- {CITE_PATTERNS_NOTE}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 第二段自检：法条适用性（是否落在案由图谱的请求权基础范围内）
# ---------------------------------------------------------------------------

@dataclass
class ApplicabilityAudit:
    """对齐 agent.ts `ApplicabilityAudit`。"""

    checked: int
    in_scope: List[str]
    out_of_scope: List[str]
    law_names: List[str]

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "in_scope": self.in_scope,
            "out_of_scope": self.out_of_scope,
            "law_names": self.law_names,
        }


def same_law(a: str, b: str) -> bool:
    """名称互含即视为同一部法。对齐 agent.ts `sameLaw()`。

    图谱存法名（如「民法」），法条返回 title 可能带后缀（如「民法（日本民法典）」）。
    """
    x = re.sub(r"\s+", "", a or "")
    y = re.sub(r"\s+", "", b or "")
    if not x or not y:
        return False
    return x == y or x in y or y in x


def audit_applicability(refs: Sequence, law_names: Sequence[str]) -> ApplicabilityAudit:
    """法条适用性校验（第二段）。

    第一段校验「引用是否真实存在（工具返回）」；
    第二段校验「引用是否落在本案由图谱的请求权基础范围内」。
    """
    def _title(r) -> str:
        return r.get("title") if isinstance(r, dict) else getattr(r, "title", "")

    titles = list(dict.fromkeys(_title(r) for r in refs))
    titles = [t for t in titles if t]
    in_scope = [t for t in titles if any(same_law(t, l) for l in law_names)]
    out = [t for t in titles if t not in in_scope]
    return ApplicabilityAudit(checked=len(titles), in_scope=in_scope,
                              out_of_scope=out, law_names=list(law_names))


def applicability_report(a: ApplicabilityAudit) -> str:
    """渲染适用性校验报告。对齐 agent.ts `applicabilityReport()`。"""
    if not a.law_names:
        return "- 未命中知识图谱案由，跳过适用性校验。"
    lines = [
        f"- 本案由图谱请求权基础：{'、'.join(a.law_names)}",
        f"- 本次引用法条 {a.checked} 部，落在案由范围内的 {len(a.in_scope)} 部",
    ]
    if a.out_of_scope:
        joined = "、".join(f"「{t}」" for t in a.out_of_scope)
        lines.append(f"- 以下引用不在本案由图谱范围内（可能仍然相关，请人工判断）：{joined}")
    elif a.checked > 0:
        lines.append("- 全部引用均落在本案由图谱的请求权基础范围内")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 「本次工具真实返回」登记簿
# ---------------------------------------------------------------------------
#
# 设计要点：登记簿只由**检索工具**写入，自检只读它。
# 这样自检结论与模型输出内容完全解耦——模型说「我查过了」不影响结论，
# 这正是可以用反例现场验证的前提。

@dataclass
class LawRef:
    """一次引用（真法条：可反查）。对齐 tools.ts `LawRef`。"""

    id: int
    title: str
    article_no: Optional[str]
    source: Optional[str]
    excerpt: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "article_no": self.article_no,
            "source": self.source, "excerpt": self.excerpt,
        }


class RefRegistry:
    """记录本次会话中工具真实返回过的法条。"""

    def __init__(self) -> None:
        self._refs: List[LawRef] = []
        self._keys: Set[str] = set()

    def record(self, ref: LawRef) -> None:
        key = (ref.title, norm_article_no(ref.article_no))
        if key in self._keys:
            return
        self._keys.add(key)
        self._refs.append(ref)

    def record_many(self, refs: Sequence[LawRef]) -> None:
        for r in refs:
            self.record(r)

    @property
    def refs(self) -> List[LawRef]:
        return list(self._refs)

    def titles(self) -> List[str]:
        return list(dict.fromkeys(r.title for r in self._refs))

    def summary(self) -> dict:
        return {
            "returned_count": len(self._refs),
            "returned": [r.to_dict() for r in self._refs],
        }

    def clear(self) -> None:
        self._refs.clear()
        self._keys.clear()


#: 进程级登记簿（单机单会话演示用；多会话应绑定 session）
REGISTRY = RefRegistry()
