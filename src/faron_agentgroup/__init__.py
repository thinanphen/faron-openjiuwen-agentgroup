# -*- coding: utf-8 -*-
"""法元 · Faron Agent Group —— 基于 openJiuwen 的多智能体协同编排。

本包把「法元」文书智能体的编排层迁移到 openJiuwen 官方 AgentGroup 框架
（`openjiuwen.agent_teams`），同时**逐条对齐**法元自研的确定性自检与知识图谱，
把它们作为框架之上的可信层。

分工：
    openJiuwen agent_teams  → 解决「一起干活」（协同 / 任务板 / 人在环 / 模型池）
    法元两段确定性自检        → 解决「干得可信」（引用对账 + 适用性校验，反例可验证）

对齐基线：`Legal-Workspace` feature/赛事版 @ 0.7.2
    src/lib/agent.ts      四角色 / 5 类任务 / 两段自检
    src/lib/kg.ts         图谱骨架
    src/lib/kgTypes.ts    节点边契约
    src/lib/tools.ts      5 个工具
    src-tauri/src/db.rs   kg_node / kg_edge / 种子
"""

from .citation import (
    CITE_PATTERNS_NOTE,
    REGISTRY,
    ApplicabilityAudit,
    CitationAudit,
    LawRef,
    RefRegistry,
    applicability_report,
    article_covers,
    audit_applicability,
    audit_citations,
    audit_report,
    extract_citation_tokens,
    norm_article_no,
    same_law,
)
from .config import (
    KIND_GUIDES,
    ROLE_SYSTEMS_BASE,
    TASK_KINDS,
    FaronConfig,
    LLMEndpoint,
    kind_meta,
    load_config_from_env,
)
from .kg import (
    KG,
    KG_CANDIDATE_CONFIDENCE,
    KG_REL_DOC,
    KG_REL_ELEMENT,
    KG_REL_EVIDENCE,
    KG_REL_ISSUE,
    KG_REL_LAW,
    KG_SEED,
    KG_TYPE_LABEL,
    KnowledgeGraph,
    KgEdge,
    KgNode,
)
from .tools_legal import (
    ALL_TOOLS,
    DEMO_LAWS,
    FORMAL_LIBRARY_STATS,
    RETURNED_DEMO,
    Article,
    find_by_article_no,
    law_by_id,
    laws_country_preview,
    laws_search,
    template_load,
    translate_text,
)
from .audit import (
    AUDIT_TOOLS,
    KG_TOOLS,
    audit_applicability_tool,
    audit_citations_tool,
    kg_add_candidate,
    kg_confirm_edge,
    kg_find_case,
    kg_query,
    returned_refs_summary,
)

__version__ = "0.2.0"

__all__ = [
    # 自检（核心资产）
    "audit_citations", "audit_applicability", "audit_report",
    "applicability_report", "extract_citation_tokens", "article_covers",
    "same_law", "norm_article_no", "CITE_PATTERNS_NOTE",
    "CitationAudit", "ApplicabilityAudit", "LawRef", "RefRegistry", "REGISTRY",
    # 图谱
    "KG", "KnowledgeGraph", "KgNode", "KgEdge", "KG_SEED", "KG_TYPE_LABEL",
    "KG_CANDIDATE_CONFIDENCE", "KG_REL_ELEMENT", "KG_REL_LAW", "KG_REL_EVIDENCE",
    "KG_REL_ISSUE", "KG_REL_DOC",
    # 工具
    "laws_search", "law_by_id", "laws_country_preview", "template_load",
    "translate_text", "ALL_TOOLS", "AUDIT_TOOLS", "KG_TOOLS",
    "audit_citations_tool", "audit_applicability_tool", "returned_refs_summary",
    "kg_find_case", "kg_query", "kg_add_candidate", "kg_confirm_edge",
    # 法库
    "DEMO_LAWS", "FORMAL_LIBRARY_STATS", "Article", "find_by_article_no",
    "RETURNED_DEMO",
    # 配置
    "FaronConfig", "LLMEndpoint", "load_config_from_env",
    "TASK_KINDS", "KIND_GUIDES", "ROLE_SYSTEMS_BASE", "kind_meta",
    # 门面
    "build_faron_spec", "FaronAgentGroup",
]


def __getattr__(name):
    """延迟导入 group，避免 `python -m` 循环导入。"""
    if name in ("build_faron_spec", "FaronAgentGroup"):
        from . import group as _g
        return getattr(_g, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
