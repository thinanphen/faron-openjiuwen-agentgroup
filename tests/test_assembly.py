# -*- coding: utf-8 -*-
"""Agent Group 装配测试 —— 逐成员断言其解析到【自己声明】的 spec 与工具集。

【这个文件为什么存在】
    仓库里曾有一个会让整个「多智能体」叙事崩塌的装配 bug（E1）：
    `group.py` 的 `agents` 字典只有 `{"leader":..., "teammate":...}`，
    而 SDK 按 `member_name → role.value → "teammate" → "leader"` 顺序解析。
    于是 `kg_curator` / `drafter` / `citation_auditor` 三个成员运行时
    **全部拿到检索员的 spec 与工具集**，框架静默兜底、不报错。

    当时没有任何测试能发现它 —— 所以本文件的第一条用例就是永久防线。

运行：
    python tests/test_assembly.py
    pytest tests/test_assembly.py -v
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from openjiuwen.agent_teams.agent.agent_configurator import AgentConfigurator  # noqa: E402
from openjiuwen.agent_teams.schema.team import TeamRole  # noqa: E402

from faron_agentgroup import config as cfg  # noqa: E402
from faron_agentgroup.group import (  # noqa: E402
    M_AUDITOR,
    M_DRAFTER,
    M_HUMAN,
    M_KG,
    M_LEADER,
    M_RETRIEVER,
    build_faron_spec,
)


# ---------------------------------------------------------------------------
# 期望的工具集（与 docs/04 编制表一致，作为唯一事实来源）
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    M_LEADER: {"kg_find_case", "kg_query", "audit_citations",
               "audit_applicability", "returned_refs_summary"},
    M_RETRIEVER: {"laws_search", "law_by_id", "laws_country_preview"},
    M_KG: {"kg_find_case", "kg_query", "kg_add_candidate", "kg_confirm_edge"},
    M_DRAFTER: {"template_load", "returned_refs_summary", "translate_text"},
    M_AUDITOR: {"audit_citations", "audit_applicability", "returned_refs_summary"},
    M_HUMAN: set(),          # 人类成员无工具
}

#: 成员的私有工作约定必须各不相同（若被兜底，会与检索员完全相同）
EXPECTED_PROMPT_MARKER = {
    M_LEADER: "团队主理",
    M_RETRIEVER: "检索员成员",
    M_KG: "图谱策展成员",
    M_DRAFTER: "起草员成员",
    M_AUDITOR: "质检员成员",
}


def _tool_names(spec) -> set:
    out = set()
    for t in (spec.tools or []):
        name = getattr(t, "name", None)
        if name:
            out.add(name)
    return out


def _resolve(spec, role: TeamRole, member_name: str):
    """走 SDK 真实解析路径，不绕过。"""
    return AgentConfigurator.resolve_agent_spec(spec, role, member_name)


# ---------------------------------------------------------------------------
# ★★ 核心防线：E1 回归测试
# ---------------------------------------------------------------------------

def test_agents_dict_covers_every_agent_member():
    """agents 字典必须按【成员名】含全部 teammate —— E1 的直接断言。

    注意主理的键是 SDK 约定的角色键 ``"leader"``（不是成员名 ``team_leader``），
    ``resolve_agent_spec`` 的第三级兜底 ``spec.agents["leader"]`` 依赖这个键。
    """
    spec = build_faron_spec()
    keys = set(spec.agents.keys())
    required = {M_RETRIEVER, M_KG, M_DRAFTER, M_AUDITOR}
    missing = required - keys
    assert not missing, (
        f"agents 字典缺少成员键 {sorted(missing)}；"
        f"缺失的成员会在 SDK 解析时静默兜底到 teammate/leader，运行时拿到错误的 spec 与工具集。"
        f"当前键：{sorted(keys)}"
    )
    assert "leader" in keys, "缺少 SDK 角色键 'leader'（主理兜底与主理解析都依赖它）"
    # 排除人类成员（无 DeepAgentSpec）后，每个 agent 成员都必须有自己的键
    for m in spec.predefined_members:
        if m.role_type == TeamRole.HUMAN_AGENT:
            continue
        assert m.member_name in keys, f"预定义成员 {m.member_name} 在 agents 中无对应键"
    print(f"  ✓ agents 字典含全部 agent 成员键：{sorted(keys)}")


def test_each_member_resolves_own_spec():
    """★ 每个成员必须解析到自己的 DeepAgentSpec —— 修 E1 前此用例为红。"""
    spec = build_faron_spec()
    failures = []

    for name, expected in EXPECTED_TOOLS.items():
        role = TeamRole.LEADER if name == M_LEADER else (
            TeamRole.HUMAN_AGENT if name == M_HUMAN else TeamRole.TEAMMATE)
        resolved = _resolve(spec, role, name)
        got = _tool_names(resolved)

        # 人类成员没有 DeepAgentSpec，跳过工具断言
        if name == M_HUMAN:
            continue

        if got != expected:
            failures.append(f"{name}: 期望 {sorted(expected)}，实得 {sorted(got)}")

    assert not failures, (
        "成员解析到了错误的 spec（E1 回归）：\n  " + "\n  ".join(failures)
    )
    print(f"  ✓ {len(EXPECTED_TOOLS) - 1} 个 agent 成员各自解析到正确工具集")


def test_members_do_not_share_spec_objects():
    """三个 teammate 必须是不同的 spec 对象，不能是同一个检索员 spec。"""
    spec = build_faron_spec()
    teammate_names = [M_RETRIEVER, M_KG, M_DRAFTER, M_AUDITOR]
    resolved = {n: id(_resolve(spec, TeamRole.TEAMMATE, n)) for n in teammate_names}
    distinct = set(resolved.values())
    assert len(distinct) == len(teammate_names), (
        f"存在成员共享同一 spec 对象（说明被兜底了）：{resolved}"
    )
    print(f"  ✓ {len(teammate_names)} 个 teammate 是 {len(distinct)} 个不同 spec 对象")


def test_each_member_resolves_own_prompt():
    """每个成员的私有工作约定必须各不相同（兜底会让它们全等于检索员的）。"""
    spec = build_faron_spec()
    seen = {}
    for name, marker in EXPECTED_PROMPT_MARKER.items():
        resolved = _resolve(spec, TeamRole.LEADER if name == M_LEADER else TeamRole.TEAMMATE, name)
        prompt = resolved.system_prompt or ""
        assert marker in prompt, (
            f"{name} 的 system_prompt 不含自己的标识「{marker}」，"
            f"很可能被兜底到了别的成员。实得前 60 字：{prompt[:60]!r}"
        )
        seen[name] = prompt
    assert len(set(seen.values())) == len(seen), "存在成员共用同一份 system_prompt"
    print(f"  ✓ {len(seen)} 个成员的 system_prompt 互不相同且各含自身标识")


def test_unpredefined_member_falls_back_to_teammate():
    """未预定义的动态成员应兜底到 teammate 键（这是设计意图，不是 bug）。"""
    spec = build_faron_spec()
    resolved = _resolve(spec, TeamRole.TEAMMATE, "some_dynamic_member")
    got = _tool_names(resolved)
    assert got == EXPECTED_TOOLS[M_RETRIEVER], (
        f"动态成员兜底应拿到 teammate 键的 spec，实得 {sorted(got)}"
    )
    print("  ✓ 未预定义成员按设计兜底到 teammate spec")


# ---------------------------------------------------------------------------
# 编制一致性
# ---------------------------------------------------------------------------

def test_predefined_members_match_expected_roster():
    spec = build_faron_spec()
    roster = {m.member_name: m.role_type for m in spec.predefined_members}
    assert roster.get(M_RETRIEVER) == TeamRole.TEAMMATE
    assert roster.get(M_KG) == TeamRole.TEAMMATE
    assert roster.get(M_DRAFTER) == TeamRole.TEAMMATE
    assert roster.get(M_AUDITOR) == TeamRole.TEAMMATE
    assert roster.get(M_HUMAN) == TeamRole.HUMAN_AGENT
    print(f"  ✓ 预定义编制成员：{sorted(roster.keys())}")


def test_hitt_enabled_matches_human_member():
    """有 HUMAN_AGENT 成员时 enable_hitt 必须为 True，否则 SDK 校验会报错。"""
    spec = build_faron_spec()
    has_human = any(m.role_type == TeamRole.HUMAN_AGENT for m in spec.predefined_members)
    assert has_human and spec.enable_hitt is True
    print("  ✓ enable_hitt=True 与 HUMAN_AGENT 成员一致")


def test_leader_name_is_default_and_not_reserved_collision():
    """主理用官方默认名 team_leader；成员名不得撞保留名。"""
    from openjiuwen.agent_teams.constants import RESERVED_MEMBER_NAMES
    spec = build_faron_spec()
    assert spec.leader.member_name == "team_leader"
    for m in spec.predefined_members:
        if m.role_type == TeamRole.HUMAN_AGENT:
            continue
        assert m.member_name not in RESERVED_MEMBER_NAMES, m.member_name
    print("  ✓ 主理=team_leader；成员名无保留名冲突")


def test_spec_is_json_serializable_and_roundtrips():
    """spec 必须可 JSON 序列化并反序列化（跨进程 spawn / 恢复依赖此性质）。"""
    spec = build_faron_spec()
    blob = spec.model_dump_json()
    from openjiuwen.agent_teams import TeamAgentSpec
    back = TeamAgentSpec.model_validate_json(blob)
    assert back.team_name == spec.team_name
    assert set(back.agents.keys()) == set(spec.agents.keys())
    print(f"  ✓ spec JSON 往返一致（{len(blob)} 字符，agents 键保留）")


# ---------------------------------------------------------------------------
# 运行器：自动发现，不做手写登记（修 E11）
# ---------------------------------------------------------------------------

def _discover():
    return [(n, f) for n, f in sorted(globals().items())
            if n.startswith("test_") and callable(f)]


def main() -> int:
    print("=" * 74)
    print("Agent Group 装配测试（E1 回归防线）")
    print("=" * 74)
    passed = failed = 0
    for name, fn in _discover():
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name} 失败：\n    {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {name} 异常：{type(exc).__name__}: {exc}")
    print("\n" + "=" * 74)
    print(f"结果：{passed} 通过 / {failed} 失败 / 共 {passed + failed}")
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
