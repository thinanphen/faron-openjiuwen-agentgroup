# -*- coding: utf-8 -*-
"""最小构建探针：验证 openJiuwen TeamAgentSpec 能否被官方框架构建。

目的：在写方案文档之前，先证明「法元 Agent Group」的成员规格是可落地的。
不调用真实模型，只验证 spec 校验与 TeamAgent 构建。
"""

import asyncio
import sys

from openjiuwen.agent_teams import (
    TeamAgentSpec,
    LeaderSpec,
    TeamMemberSpec,
    TeamRole,
)
from openjiuwen.agent_teams.schema.deep_agent_spec import (
    DeepAgentSpec,
    TeamModelConfig,
)
from openjiuwen.agent_teams.models.pool import ModelPoolEntry
from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
from openjiuwen.core.single_agent.schema.agent_card import AgentCard


def build_model_config(model_name: str, base_url: str, api_key: str) -> TeamModelConfig:
    return TeamModelConfig(
        model_client_config=ModelClientConfig(
            client_provider="openai",
            api_key=api_key,
            api_base=base_url,
            verify_ssl=False,
        ),
        model_request_config=ModelRequestConfig(model=model_name),
    )


def make_spec() -> TeamAgentSpec:
    """构造「法元 · 小元」文书智能体团队规格（4 个 AI 成员 + 1 个人类复核员）。"""
    placeholder = build_model_config(
        "PLACEHOLDER_MODEL", "https://api.example.com/v1", "sk-placeholder"
    )

    leader = DeepAgentSpec(
        card=AgentCard(
            id="faron_team_leader",
            name="小元·主理",
            description="法元文书智能体的团队主理：理解委托、拆分任务、汇总交付。",
        ),
        system_prompt=(
            "你是法元 · Faron 文书智能体的团队主理「小元」。"
            "你把一份涉外法律委托拆成可并行的子任务，分派给检索员、起草员、质检员，"
            "并把质检结论与交付物汇总给用户。"
            "硬规则：交付物中的每一条法条引用必须来自检索员真实返回的条文，不得凭记忆书写。"
        ),
        model=placeholder,
    )

    def teammate(name, display, card_id, desc, prompt):
        return TeamMemberSpec(
            member_name=name,
            display_name=display,
            desc=desc,
            prompt=prompt,
            role_type=TeamRole.TEAMMATE,
        )

    return TeamAgentSpec(
        team_name="faron_wenshu_team",
        agents={"leader": leader},
        leader=LeaderSpec(
            member_name="team_leader",
            display_name="小元·主理",
            desc="团队主理，负责规划、分派与交付汇总。",
        ),
        predefined_members=[
            teammate(
                "law_retriever", "检索员·民商",
                "faron_retriever",
                "在内置日美法库中检索真实法条并回传溯源信息。",
                "你只做一件事：用本地法库工具检索法条，返回条文号 + 篇名 + 来源。绝不臆造条文。",
            ),
            teammate(
                "drafter", "起草员",
                "faron_drafter",
                "依据检索结果与模板起草文书正文。",
                "你只允许引用检索员真实返回的法条，输出固定五段式文书正文。",
            ),
            teammate(
                "citation_auditor", "质检员·引用自检",
                "faron_auditor",
                "代码级逐条对账引用，点名未覆盖项。",
                "你用确定性规则逐条比对正文引用与本次工具真实返回，未覆盖项一律点名，不计为有效引用。",
            ),
        ],
        enable_hitt=True,
        teammate_mode="build_mode",
        dispatch_mode="autonomous",
        spawn_mode="inprocess",
        storage=None,
        language="cn",
    )


def main() -> int:
    print("=" * 70)
    print("openJiuwen TeamAgentSpec 构建探针")
    print("=" * 70)
    spec = make_spec()
    print(f"[1] spec 校验通过：team_name={spec.team_name}")
    print(f"    predefined_members = {[m.member_name for m in spec.predefined_members]}")
    print(f"    enable_hitt        = {spec.enable_hitt}")
    print(f"    spawn_mode         = {spec.spawn_mode}")

    dumped = spec.model_dump_json()
    print(f"[2] JSON 序列化成功：{len(dumped)} 字符（可跨进程分发）")

    try:
        agent = spec.build()
    except Exception as exc:  # noqa: BLE001
        print(f"[3] build() 失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"[3] build() 成功：{type(agent).__name__}  role={agent.role.value}")
    print(f"    member_name = {agent._member_name()}")
    print(f"    leader_member_name = {agent.team_spec.leader_member_name}")
    print(f"    model_pool_strategy = {agent.team_spec.model_pool_strategy}")

    spec2 = TeamAgentSpec.model_validate_json(dumped)
    print(f"[4] 反序列化成功：team_name={spec2.team_name}（跨进程恢复可用）")
    print("=" * 70)
    print("结论：Agent Group 成员规格可被 openJiuwen 官方框架构建。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
