# -*- coding: utf-8 -*-
"""法元 · Faron Agent Group —— 规格装配与团队构建。

方案文档：`../01-方案/法元Faron-AgentGroup方案.md`
真实实现对齐：`../_source/Legal-Workspace`（feature/赛事版 @ 0.7.2）

    §三 成员定义  → build_faron_spec()
    §四 通信协议  → 由 openJiuwen agent_teams 原生提供
    §五 接口定义  → FaronAgentGroup 门面
    §六 模型选型  → FaronConfig.model_pool_strategy
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from openjiuwen.agent_teams import (
    LeaderSpec,
    TeamAgentSpec,
    TeamMemberSpec,
    TeamRole,
)
from openjiuwen.agent_teams.models.pool import ModelPoolEntry
from openjiuwen.agent_teams.schema.blueprint import StorageSpec
from openjiuwen.agent_teams.schema.deep_agent_spec import DeepAgentSpec, TeamModelConfig
from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
from openjiuwen.core.single_agent.schema.agent_card import AgentCard

from . import config as cfg
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
from .tools_legal import (
    ALL_TOOLS,
    law_by_id,
    laws_country_preview,
    laws_search,
    template_load,
    translate_text,
)

# ---------------------------------------------------------------------------
# 成员名（全队唯一，避开 openJiuwen 保留名 user / human_agent）
# ---------------------------------------------------------------------------

M_LEADER = "team_leader"           # 官方默认主理名
M_RETRIEVER = "law_retriever"
M_KG = "kg_curator"
M_DRAFTER = "drafter"
M_AUDITOR = "citation_auditor"
M_HUMAN = "human_reviewer"

#: 全员工具清单（注册到 openJiuwen 资源管理器）
FARON_TOOLS = list(ALL_TOOLS) + list(AUDIT_TOOLS) + list(KG_TOOLS)


def _cards(tools) -> list:
    """把 @tool 装饰出的 LocalFunction 摊平成 ToolCard。

    DeepAgentSpec.tools 的联合类型是 ``ToolCard | BuiltinToolSpec``，
    不接受 LocalFunction 实例本身；执行时由 Runner 资源管理器按 card.id 回查实例。
    """
    return [t.card if hasattr(t, "card") else t for t in tools]


def register_tools() -> int:
    """把法元工具箱注册到 openJiuwen 资源管理器。返回成功注册数。"""
    from openjiuwen.core.runner import Runner

    ok = 0
    for t in FARON_TOOLS:
        try:
            Runner.resource_mgr.add_tool(t, skip_if_exists=True)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[tools] 注册失败：{type(exc).__name__}: {exc}")
    return ok


def _to_team_model(ep: cfg.LLMEndpoint) -> TeamModelConfig:
    return TeamModelConfig(
        model_client_config=ModelClientConfig(
            client_provider=ep.api_provider,
            api_key=ep.api_key,
            api_base=ep.api_base_url,
            verify_ssl=False,
        ),
        model_request_config=ModelRequestConfig(
            model=ep.model_name, temperature=ep.temperature),
    )


def _to_pool_entry(ep: cfg.LLMEndpoint) -> ModelPoolEntry:
    return ModelPoolEntry(
        model_name=ep.model_name,
        api_key=ep.api_key,
        api_base_url=ep.api_base_url,
        api_provider=ep.api_provider,
        description=ep.description,
        metadata={"request": {"temperature": ep.temperature}},
    )


def build_faron_spec(conf: Optional[cfg.FaronConfig] = None) -> TeamAgentSpec:
    """装配「法元 · 小元」文书智能体团队的完整规格。

    成员编制（对应方案 §三）：
        LEADER        小元·主理          —— 规划 / 分派 / 汇总
        TEAMMATE      检索员·民商         —— 本地法库检索 + 溯源
        TEAMMATE      图谱策展            —— 案由匹配 + 骨架 + 候选边
        TEAMMATE      起草员              —— 依检索结果起草
        TEAMMATE      质检员·两段自检      —— 确定性对账
        HUMAN_AGENT   人类复核员          —— 审批 / 复核
    """
    conf = conf or cfg.load_config_from_env()

    strong = next((e for e in conf.endpoints if e.tier == "strong"), None) \
        or (conf.endpoints[0] if conf.endpoints else None)
    fast = next((e for e in conf.endpoints if e.tier == "fast"), None) or strong
    ph = cfg.LLMEndpoint("PLACEHOLDER", "sk-placeholder", "https://api.example.com/v1")
    strong, fast = strong or ph, fast or ph

    ws = {"root_path": conf.workspace_root, "language": conf.language}
    base = dict(workspace=ws, language=conf.language)

    # ---- LEADER：小元·主理 ----
    leader = DeepAgentSpec(
        card=AgentCard(id="faron_team_leader", name="小元·主理",
                       description=cfg.LEADER_DESC),
        system_prompt=cfg.LEADER_PROMPT,
        tools=_cards([kg_find_case, kg_query, audit_citations_tool,
                      audit_applicability_tool, returned_refs_summary]),
        model=_to_team_model(strong), max_iterations=40, **base,
    )
    # ---- TEAMMATE：检索员 ----
    retriever = DeepAgentSpec(
        card=AgentCard(id="faron_retriever", name="检索员·民商",
                       description=cfg.RETRIEVER_DESC),
        system_prompt=cfg.RETRIEVER_PROMPT,
        tools=_cards([laws_search, law_by_id, laws_country_preview]),
        model=_to_team_model(fast), max_iterations=25, **base,
    )
    # ---- TEAMMATE：图谱策展 ----
    kg_curator = DeepAgentSpec(
        card=AgentCard(id="faron_kg_curator", name="图谱策展",
                       description=cfg.KG_CURATOR_DESC),
        system_prompt=cfg.KG_CURATOR_PROMPT,
        tools=_cards([kg_find_case, kg_query, kg_add_candidate, kg_confirm_edge]),
        model=_to_team_model(fast), max_iterations=25, **base,
    )
    # ---- TEAMMATE：起草员 ----
    drafter = DeepAgentSpec(
        card=AgentCard(id="faron_drafter", name="起草员",
                       description=cfg.DRAFTER_DESC),
        system_prompt=cfg.DRAFTER_PROMPT,
        tools=_cards([template_load, returned_refs_summary, translate_text]),
        model=_to_team_model(strong), max_iterations=25, **base,
    )
    # ---- TEAMMATE：质检员 ----
    auditor = DeepAgentSpec(
        card=AgentCard(id="faron_auditor", name="质检员·两段自检",
                       description=cfg.AUDITOR_DESC),
        system_prompt=cfg.AUDITOR_PROMPT,
        tools=_cards([audit_citations_tool, audit_applicability_tool,
                      returned_refs_summary]),
        model=_to_team_model(fast), max_iterations=25, **base,
    )

    agents = {"leader": leader, "teammate": retriever}

    predefined: List[TeamMemberSpec] = [
        TeamMemberSpec(member_name=M_RETRIEVER, display_name="检索员·民商",
                       desc=cfg.RETRIEVER_DESC, prompt=cfg.RETRIEVER_PROMPT,
                       role_type=TeamRole.TEAMMATE, model_name=fast.model_name),
        TeamMemberSpec(member_name=M_KG, display_name="图谱策展",
                       desc=cfg.KG_CURATOR_DESC, prompt=cfg.KG_CURATOR_PROMPT,
                       role_type=TeamRole.TEAMMATE, model_name=fast.model_name),
        TeamMemberSpec(member_name=M_DRAFTER, display_name="起草员",
                       desc=cfg.DRAFTER_DESC, prompt=cfg.DRAFTER_PROMPT,
                       role_type=TeamRole.TEAMMATE, model_name=strong.model_name),
        TeamMemberSpec(member_name=M_AUDITOR, display_name="质检员·两段自检",
                       desc=cfg.AUDITOR_DESC, prompt=cfg.AUDITOR_PROMPT,
                       role_type=TeamRole.TEAMMATE, model_name=fast.model_name),
        TeamMemberSpec(member_name=M_HUMAN, display_name="人类复核员",
                       desc=cfg.HUMAN_REVIEWER_DESC, prompt="",
                       role_type=TeamRole.HUMAN_AGENT),
    ]

    return TeamAgentSpec(
        team_name=conf.team_name,
        agents=agents,
        leader=LeaderSpec(member_name=M_LEADER, display_name="小元·主理",
                          desc=cfg.LEADER_DESC, prompt=cfg.LEADER_PROMPT,
                          model_name=strong.model_name),
        predefined_members=predefined,
        model_pool=[_to_pool_entry(e) for e in conf.endpoints] or [_to_pool_entry(ph)],
        model_pool_strategy=conf.model_pool_strategy,
        storage=StorageSpec(type=conf.storage),
        spawn_mode=conf.spawn_mode,
        teammate_mode=conf.teammate_mode,
        dispatch_mode=conf.dispatch_mode,
        enable_hitt=conf.enable_hitt,
        enable_task_verification=conf.enable_task_verification,
        enable_permissions=conf.enable_permissions,
        expose_human_agents_to_teammates=conf.expose_human_agents_to_teammates,
        language=conf.language,
        workspace={"root_path": conf.workspace_root, "language": conf.language},
        evolution_enabled=True,
        default_max_review_rounds=3,
        metadata={
            "product": "法元 · Faron",
            "framework": "openjiuwen.agent_teams",
            "core_asset": "two-stage deterministic audit (audit_citations + audit_applicability)",
            "aligned_with": "Legal-Workspace feature/赛事版 @0.7.2 (agent.ts / kg.ts / tools.ts)",
        },
    )


# ---------------------------------------------------------------------------
# 门面
# ---------------------------------------------------------------------------

class FaronAgentGroup:
    """法元 Agent Group 门面：构建 / 运行 / 介入 / 人审 / 离线两段自检。"""

    def __init__(self, conf: Optional[cfg.FaronConfig] = None):
        self.conf = conf or cfg.load_config_from_env()
        self.tools_registered = register_tools()
        self.spec = build_faron_spec(self.conf)
        Path(self.conf.workspace_root).mkdir(parents=True, exist_ok=True)
        self._agent = None

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self.spec.build()
        return self._agent

    # ---- 生命周期 ----

    async def run(self, query: str, session=None):
        async for chunk in self.agent.stream({"query": query}, session=session):
            yield chunk

    async def interact(self, message: str) -> None:
        await self.agent.interact(message)

    async def human_say(self, content: str, to: Optional[str] = M_LEADER):
        return await self.agent.human_agent_say(content, to=to)

    async def broadcast(self, content: str):
        return await self.agent.broadcast(content)

    # ---- 离线两段自检（不依赖模型，可直接调用）----

    @staticmethod
    def audit_citations(body_text: str):
        """第一段：引用是否真实存在。"""
        from .citation import audit_citations as _f
        from .citation import REGISTRY
        return _f(body_text, REGISTRY.refs)

    @staticmethod
    def audit_applicability(case_name: str):
        """第二段：是否落在案由图谱的请求权基础范围内。"""
        from .citation import REGISTRY, audit_applicability as _f
        from .kg import KG
        sk = KG.skeleton(case_name)
        if sk is None:
            return None
        return _f(REGISTRY.refs, sk["lawNames"])

    def describe(self) -> dict:
        """输出团队编制摘要，供材料/答辩引用。"""
        return {
            "team_name": self.spec.team_name,
            "framework": "openjiuwen.agent_teams",
            "leader": self.spec.leader.member_name,
            "members": [
                {"name": m.member_name, "display": m.display_name,
                 "role": m.role_type.value, "desc": m.desc}
                for m in self.spec.predefined_members
            ],
            "tools": [t.card.name if hasattr(t, "card") else str(t)
                      for t in FARON_TOOLS],
            "tool_count": len(FARON_TOOLS),
            "enable_hitt": self.spec.enable_hitt,
            "dispatch_mode": self.spec.dispatch_mode,
            "teammate_mode": self.spec.teammate_mode,
            "spawn_mode": self.spec.spawn_mode,
            "model_pool_strategy": self.spec.model_pool_strategy,
            "model_pool": [e.model_name for e in self.spec.model_pool],
            "has_real_model": self.conf.has_model,
            "storage": self.spec.storage.type if self.spec.storage else None,
        }
