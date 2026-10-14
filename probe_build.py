# -*- coding: utf-8 -*-
"""法元 · Faron Agent Group —— 构建探针（含逐成员 spec 区分）。

【本文件为什么要重写】
    旧版 `probe_build.py` 自建了一个**独立的小型 spec**（只有 3 个成员、
    成员名还是早期的 `law_retriever/drafter/citation_auditor`），从未验证
    `group.py` 里真正使用的 `build_faron_spec()`。
    因此它**盖不住 E1 那个装配 bug** —— 旧版照样打印"build() 成功"。

    现在改为直接验证真实装配，并**逐成员打印解析到的 spec 与工具集**，
    使任何"成员被兜底"的问题在探针阶段就可见。

运行：
    python probe_build.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from openjiuwen.agent_teams import TeamAgentSpec  # noqa: E402
from openjiuwen.agent_teams.agent.agent_configurator import AgentConfigurator  # noqa: E402
from openjiuwen.agent_teams.schema.team import TeamRole  # noqa: E402

from faron_agentgroup.group import (  # noqa: E402
    M_AUDITOR,
    M_DRAFTER,
    M_HUMAN,
    M_KG,
    M_LEADER,
    M_RETRIEVER,
    build_faron_spec,
)

#: 期望编制（与 docs/04 编制表一致）
AGENT_MEMBERS = [M_LEADER, M_RETRIEVER, M_KG, M_DRAFTER, M_AUDITOR]


def tool_names(spec) -> list:
    out = []
    for t in (spec.tools or []):
        n = getattr(t, "name", None)
        if n:
            out.append(n)
    return sorted(out)


def role_of(name: str) -> TeamRole:
    if name == M_LEADER:
        return TeamRole.LEADER
    if name == M_HUMAN:
        return TeamRole.HUMAN_AGENT
    return TeamRole.TEAMMATE


def main() -> int:
    print("=" * 78)
    print("法元 · Faron Agent Group —— 构建探针（真实装配 + 逐成员 spec 区分）")
    print("=" * 78)

    # ---------- [1] 真实 spec 校验 ----------
    spec = build_faron_spec()
    print(f"[1] 真实 build_faron_spec() 校验通过：team_name={spec.team_name}")
    print(f"    agents 字典键      = {sorted(spec.agents.keys())}")
    print(f"    predefined_members = {[m.member_name for m in spec.predefined_members]}")
    print(f"    enable_hitt        = {spec.enable_hitt}")
    print(f"    spawn_mode         = {spec.spawn_mode}")
    print(f"    dispatch_mode      = {spec.dispatch_mode}")

    # ---------- [2] 逐成员 spec 区分（E1 防线）----------
    print("\n[2] 逐成员解析（走 SDK 真实 resolve_agent_spec 路径）")
    print(f"    {'成员':<20} {'role':<12} {'spec 对象 id':<16} 工具集")
    print("    " + "-" * 74)
    resolved_ids = {}
    rows = []
    for name in AGENT_MEMBERS:
        r = AgentConfigurator.resolve_agent_spec(spec, role_of(name), name)
        oid = id(r)
        resolved_ids[name] = oid
        tools = tool_names(r)
        rows.append((name, role_of(name).value, oid, tools))
        print(f"    {name:<20} {role_of(name).value:<12} {oid:<16} {tools}")

    distinct = len(set(resolved_ids.values()))
    ok_distinct = distinct == len(AGENT_MEMBERS)
    print(f"\n    不同 spec 对象数：{distinct} / {len(AGENT_MEMBERS)}  "
          f"{'✅ 各成员互不干扰' if ok_distinct else '❌ 存在成员被兜底（E1 回归）'}")

    # ---------- [3] 成员身份隔离抽查 ----------
    print("\n[3] 成员身份隔离抽查（prompt 不得互相污染）")
    markers = {
        M_LEADER: "团队主理",
        M_RETRIEVER: "检索员成员",
        M_KG: "图谱策展成员",
        M_DRAFTER: "起草员成员",
        M_AUDITOR: "质检员成员",
    }
    ok_prompt = True
    for name, marker in markers.items():
        r = AgentConfigurator.resolve_agent_spec(spec, role_of(name), name)
        hit = marker in (r.system_prompt or "")
        ok_prompt &= hit
        print(f"    {name:<20} 含「{marker}」：{'✅' if hit else '❌'}")
    print(f"    {'→ 全部通过' if ok_prompt else '→ 存在身份污染'}")

    # ---------- [4] JSON 往返 ----------
    dumped = spec.model_dump_json()
    back = TeamAgentSpec.model_validate_json(dumped)
    ok_rt = set(back.agents.keys()) == set(spec.agents.keys())
    print(f"\n[4] JSON 序列化 {len(dumped)} 字符；往返后 agents 键一致：{'✅' if ok_rt else '❌'}")

    # ---------- [5] 真实 build() ----------
    print("\n[5] spec.build() 真实构建 TeamAgent")
    try:
        agent = spec.build()
    except Exception as exc:  # noqa: BLE001
        print(f"    ❌ build() 失败：{type(exc).__name__}: {exc}")
        return 1
    print(f"    ✅ build() 成功：{type(agent).__name__}  role={agent.role.value}")
    print(f"       member_name         = {agent._member_name()}")
    print(f"       leader_member_name  = {agent.team_spec.leader_member_name}")
    print(f"       model_pool_strategy = {agent.team_spec.model_pool_strategy}")

    # ---------- 结论 ----------
    all_ok = ok_distinct and ok_prompt and ok_rt
    print("\n" + "=" * 78)
    if all_ok:
        print("结论：Agent Group 装配正确 —— 全部成员解析到各自的 spec 与工具集。")
    else:
        print("结论：❌ 装配存在问题，见上方标记。")
    print("=" * 78)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
