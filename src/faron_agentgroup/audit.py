# -*- coding: utf-8 -*-
"""质检与图谱工具 —— 把「法元」的两段自检与知识图谱暴露为 Agent 工具。

【两段自检（对齐 agent.ts 第 599–717 行）】
    第一段 `audit_citations`      —— 引用是否**真实存在**（能否在本次工具真实返回中找到）
    第二段 `audit_applicability`  —— 引用是否**落在案由图谱的请求权基础范围内**

【为什么它是「法元」的核心资产】
    通用 Agent 会说「我查过了」。在高风险域，"模型自称查过"不是证据。
    本模块把「引用是否成立」变成**代码级规则判定**：
        - 不调用任何模型；
        - 结论只依赖 (正文, 工具真实返回集合)；
        - 同样输入永远得到同样输出。
    因此可以用反例现场验证，也可以被评审核验。
"""

from __future__ import annotations

import json
from typing import Optional

from openjiuwen.core.foundation.tool import tool

from .citation import (
    CITE_PATTERNS_NOTE,
    REGISTRY,
    applicability_report,
    audit_applicability,
    audit_citations,
    audit_report,
)
from .kg import KG, KG_SEED


# ---------------------------------------------------------------------------
# 第一段：确定性引用自检
# ---------------------------------------------------------------------------

@tool(
    name="audit_citations",
    description=(
        "对文书正文做**第一段确定性自检**：逐条比对正文里的条文号引用与"
        "「本次工具真实返回的法条集合」，未覆盖项一律点名、不视为有效引用。"
        "本工具是代码级规则判定，不调用模型，因此可用反例现场验证。"
        "硬规则：本工具的结论是最终结论，不得用模型判断覆盖。"
    ),
    stateless=True,
)
def audit_citations_tool(body_text: str) -> str:
    """确定性引用自检（第一段）。

    Args:
        body_text: 待检的文书正文（Markdown 或纯文本）。

    Returns:
        JSON 字符串：total / covered / unmatched / 渲染后的 Markdown 报告。
    """
    a = audit_citations(body_text, REGISTRY.refs)
    payload = a.to_dict()
    payload["report_markdown"] = audit_report(a)
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 第二段：法条适用性校验
# ---------------------------------------------------------------------------

@tool(
    name="audit_applicability",
    description=(
        "对本次引用做**第二段自检**：校验引用到的法律是否落在「本案由图谱的请求权基础范围」内。"
        "需先用 kg_find_case / kg_query 命中案由，再把图谱的 lawNames 传入。"
        "不在范围内的引用会列出，但可能仍然相关，仅供人工判断。"
    ),
    stateless=True,
)
def audit_applicability_tool(case_name: str) -> str:
    """法条适用性校验（第二段）。

    Args:
        case_name: 命中的案由名（如「涉外合资经营合同纠纷」）。

    Returns:
        JSON 字符串：checked / in_scope / out_of_scope / law_names + Markdown 报告。
    """
    sk = KG.skeleton((case_name or "").strip())
    if sk is None:
        return json.dumps({
            "skipped": True,
            "reason": f"图谱未命中案由「{case_name}」",
            "report_markdown": "- 未命中知识图谱案由，跳过适用性校验。",
        }, ensure_ascii=False, indent=2)

    a = audit_applicability(REGISTRY.refs, sk["lawNames"])
    payload = a.to_dict()
    payload["case"] = sk["case"]
    payload["report_markdown"] = applicability_report(a)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool(
    name="returned_refs_summary",
    description=(
        "查看「本次工具真实返回过的法条」清单与数量。"
        "起草前用它确认可引用范围；自检前用它核对检索是否充分。"
    ),
    stateless=True,
)
def returned_refs_summary() -> str:
    """查看本次工具真实返回的法条清单。

    Returns:
        JSON 字符串：返回过的法条数量与逐条明细（含条号、篇名、来源）。
    """
    return json.dumps(REGISTRY.summary(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 知识图谱工具（对齐 db.rs 的 kg_* 命令）
# ---------------------------------------------------------------------------

@tool(
    name="kg_find_case",
    description=(
        "按关键词把任务材料归到某个案由（返回案由名；无法判断返回 null）。"
        "用于在制定计划前先定案由——案由定了，构成要件与请求权基础才定得下来。"
    ),
    stateless=True,
)
def kg_find_case(text: str) -> str:
    """按材料文本匹配案由。

    Args:
        text: 任务材料文本（合同 / 案情描述）。

    Returns:
        JSON 字符串：{"case": "涉外合资经营合同纠纷"} 或 {"case": null}。
    """
    case = KG.find_case(text or "")
    out = {"case": case, "matched": case is not None}
    if case is None:
        out["known_cases"] = [sc.case for sc in KG_SEED]
        out["note"] = "未命中案由；计划卡应回退为通用流水线"
    return json.dumps(out, ensure_ascii=False, indent=2)


@tool(
    name="kg_query",
    description=(
        "查询某案由的知识图谱骨架：构成要件 → 请求权基础 / 证据，以及常见争点与文书载体。"
        "**用于驱动计划卡编排**——要件不漏、法域自动限定。"
        "注意：图谱里的法条节点只有「法律名」，没有具体条号，条号必须靠 laws_search 真实检索。"
    ),
    stateless=True,
)
def kg_query(case_name: str) -> str:
    """查询案由图谱骨架。

    Args:
        case_name: 案由名，如「涉外合资经营合同纠纷」「涉外货物买卖合同纠纷」。

    Returns:
        JSON 字符串：骨架 {case, elements, issues, docs, lawNames} + 渲染文本。
    """
    sk = KG.skeleton((case_name or "").strip())
    if sk is None:
        return json.dumps({
            "matched": False,
            "query": case_name,
            "known_cases": [sc.case for sc in KG_SEED],
            "note": "图谱未命中；计划卡应回退为通用五步流水线",
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "matched": True,
        "skeleton": sk,
        "described": KG.describe_skeleton(sk),
    }, ensure_ascii=False, indent=2)


@tool(
    name="kg_add_candidate",
    description=(
        "把任务中真实命中的法条登记为「候选边」（低置信度，挂在案由下，**待人工确认**）。"
        "对齐法元的图谱自进化机制：人工确认后才作为后续规划依据。"
        "重复登记同一法条返回 registered=false。"
    ),
    stateless=True,
)
def kg_add_candidate(case_name: str, law_title: str) -> str:
    """登记候选边（待人工确认）。

    Args:
        case_name: 案由名。
        law_title: 法律名（不是条号）。

    Returns:
        JSON 字符串：{"registered": true, "edge_id": N} 或 registered=false。
    """
    eid = KG.add_candidate((case_name or "").strip(), (law_title or "").strip())
    return json.dumps({
        "registered": eid is not None,
        "edge_id": eid,
        "confirmed": False,
        "note": "候选边置信度 0.6 < 0.8，需人工确认后才作为后续规划依据",
    }, ensure_ascii=False, indent=2)


@tool(
    name="kg_confirm_edge",
    description=(
        "人工确认或拒绝一条候选边（拒绝即删除）。对齐法元「人工确认制」图谱自进化。"
        "确认后该边置信度升为 1.0 并标记 confirmed。"
    ),
    stateless=True,
)
def kg_confirm_edge(edge_id: int, confirmed: bool) -> str:
    """人工确认 / 拒绝候选边。

    Args:
        edge_id: 候选边 id（来自 kg_add_candidate）。
        confirmed: True 确认 / False 拒绝（删除）。

    Returns:
        JSON 字符串：{"ok": true, ...}
    """
    ok = KG.confirm_edge(int(edge_id), bool(confirmed))
    return json.dumps({"ok": ok, "edge_id": int(edge_id),
                       "action": "confirmed" if confirmed else "rejected"},
                      ensure_ascii=False, indent=2)


#: 质检与图谱工具清单（供注册）
AUDIT_TOOLS = [
    audit_citations_tool,
    audit_applicability_tool,
    returned_refs_summary,
]
KG_TOOLS = [
    kg_find_case,
    kg_query,
    kg_add_candidate,
    kg_confirm_edge,
]

# 兼容旧引用名
audit = audit_citations
