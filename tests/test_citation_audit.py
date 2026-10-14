# -*- coding: utf-8 -*-
"""引用自检与知识图谱 —— 对齐官方规则的测试向量。

这组测试同时承担两个职责：
    1. 证明「可用反例现场验证」的宣称（注入库外条号必须被点名）；
    2. 守住 **TS/Python 双端一致**——向量与 `Legal-Workspace/src/lib/agent.ts`
       的 extractCitationTokens / articleCovers 行为逐条对齐。

运行：
    python tests/test_citation_audit.py
或（装了 pytest）：
    pytest tests/test_citation_audit.py -v
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from faron_agentgroup import (          # noqa: E402
    KG,
    KG_REL_ELEMENT,
    KG_REL_LAW,
    REGISTRY,
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
from faron_agentgroup.tools_legal import DEMO_LAWS, RETURNED_DEMO  # noqa: E402


# ---------------------------------------------------------------------------
# 一、token 抽取（对齐 agent.ts extractCitationTokens）
# ---------------------------------------------------------------------------

def test_extract_basic_cn_jp():
    toks = extract_citation_tokens("依第103条与第五百二十二条，另见第百三条。")
    assert toks == ["第103条", "第五百二十二条", "第百三条"], toks
    print(f"  ✓ 中日文条号抽取：{toks}")


def test_extract_jp_sub_article():
    """日文「の」分条 —— 官方正则含 之|の|ノ 三种分隔符。"""
    for sep in ("の", "之", "ノ"):
        toks = extract_citation_tokens(f"第百三条{sep}二の規定による。")
        assert toks, f"分隔符 {sep} 未抽取到"
    toks = extract_citation_tokens("第百三条の二の規定による。")
    assert toks[0] == "第百三条の二", toks
    print(f"  ✓ 日文分条（の/之/ノ）抽取：{toks[0]}")


def test_extract_us_section_variants():
    """美国法典 §NN，含 -1 与 .1 变体 —— 官方正则 §\\s*\\d+(?:[.\\-]\\d+)?(?:\\(\\d+\\+)?。

    ⚠ 实测记录（Python re 与 JS matchAll 语义一致，均为全局非重叠匹配）：

        'Under §1125(a)' → token 为 '§1125'，**捕获组 (\\d+) 的 (a) 后缀未被纳入**

    这是官方正则的一个真实覆盖缺口：`§1125(a)` 与 `§1125` 归一化后都是 "§1125"，
    两处引用会被**当成同一处**（去重后只算 1 处）。对「相同法律的不同款项」这种
    高频引用形式，自检的粒度会偏粗——但方向是**偏严**（不会漏报编造条号），
    因为 `§9999` 之类依然会被如实点名。此结论已回写评估建议文档 G11。

    本用例固化真实行为，而非想要的行为——避免「测试通过但实现与官方不一致」。
    """
    cases = {
        "Under §1125 the claim stands.": "§1125",
        "See §101-1 and §362.": "§101-1",
        "See § 1125 for details.": "§1125",        # 空白被去除
    }
    for text, expected in cases.items():
        toks = extract_citation_tokens(text)
        assert expected in toks, f"{text!r} → {toks}，期望含 {expected}"

    # 固化官方缺口：捕获组后缀不被纳入
    toks = extract_citation_tokens("Under §1125(a) the claim stands.")
    assert toks == ["§1125"], f"官方行为应为 ['§1125']，实得 {toks}"
    print(f"  ✓ 美国法典 §NN 变体（{len(cases)} 组）＋ 固化官方缺口：§1125(a) → {toks}")


def test_extract_dedup_preserves_order():
    toks = extract_citation_tokens("第103条 §1125 第103条 §1125 第五百二十二条")
    assert toks == ["第103条", "§1125", "第五百二十二条"], toks
    print(f"  ✓ 去重且保序：{toks}")


def test_extract_empty():
    assert extract_citation_tokens("") == []
    assert extract_citation_tokens("本意见书不涉及具体法条。") == []
    print("  ✓ 边界：空文本 / 无引用 → 空列表")


# ---------------------------------------------------------------------------
# 二、覆盖判定（对齐 agent.ts normArticleNo / articleCovers）
# ---------------------------------------------------------------------------

def test_norm_article_no():
    assert norm_article_no(" 第 一百四十三条 ") == "第一百四十三条"
    assert norm_article_no("§1125（a）") == "§1125a"
    assert norm_article_no(None) == ""
    print("  ✓ 归一化：去空白 + 去全半角括号")


def test_article_covers():
    # 完全相等
    assert article_covers("第一百四十三条", "第一百四十三条") is True
    # 条文号以引用为前缀（官方注释给出的例子）
    assert article_covers("第一百四十三条第二款", "第一百四十三条") is True
    # 引用更长 → 不覆盖（官方逻辑是 len(t) < len(a) 且 startswith）
    assert article_covers("第一百四十三条", "第一百四十三条第二款") is False
    # 完全不同的条号
    assert article_covers("第一百四十三条", "第一百四十四条") is False
    # 空值
    assert article_covers(None, "第103条") is False
    assert article_covers("第103条", "") is False
    print("  ✓ 覆盖判定：相等 / 前缀覆盖 / 反向不覆盖 / 空值")


# ---------------------------------------------------------------------------
# 三、第一段自检
# ---------------------------------------------------------------------------

def test_audit_pass():
    refs = [r.to_ref() for r in RETURNED_DEMO]      # 第五百二十二条 / 第五百四十一条
    body = f"依据{RETURNED_DEMO[0].article_no}与{RETURNED_DEMO[1].article_no}，结论如下。"
    a = audit_citations(body, refs)
    assert a.total == 2 and a.covered == 2 and a.ok is True, a
    assert "自检通过" in audit_report(a)
    print(f"  ✓ 正向：{a.total} 处引用全部命中 → ok={a.ok}")


def test_audit_catch_fake_citation():
    """★ 核心宣称的证明：注入库外条号，必须当场点名。"""
    refs = [r.to_ref() for r in RETURNED_DEMO]
    body = (f"依据{RETURNED_DEMO[0].article_no}、{RETURNED_DEMO[1].article_no}"
            f"以及第9999条，本案应支持原告请求。")
    a = audit_citations(body, refs)
    assert a.total == 3, f"期望 3 处，实得 {a.total}"
    assert a.covered == 2 and a.ok is False
    assert a.unmatched == ["第9999条"], a.unmatched
    rep = audit_report(a)
    assert "第9999条" in rep and "请人工核实" in rep
    print(f"  ✓ 反例：库外条号被点名 → {a.unmatched}")


def test_audit_catch_fake_us_section():
    refs = [r.to_ref() for r in RETURNED_DEMO]
    body = "依 §1125、§9999 与 §101-1，均不成立。"
    a = audit_citations(body, refs)
    assert set(a.unmatched) == {"§1125", "§9999", "§101-1"}, a.unmatched
    print(f"  ✓ 反例（美国法典）：工具零返回美国法条 → 3 处全部点名 {a.unmatched}")


def test_audit_partial_coverage_us():
    """§1125(a) 被归一化后与 §1125 相同 → 只算 1 处（固化的官方粒度）。"""
    refs = [DEMO_LAWS[7].to_ref()]                  # §1125
    body = "依 §1125 与 §1125(a)，均成立。"
    a = audit_citations(body, refs)
    assert a.total == 1, f"两处写法归一化后应为 1 处，实得 {a.total}"
    assert a.covered == 1 and a.ok is True, a.to_dict()
    print(f"  ✓ 官方粒度：§1125 与 §1125(a) 归一化后合并为 1 处 → {a.total} 处全命中")


def test_audit_us_partial_with_miss():
    """美国法典部分命中：真实返回 §1125，正文引 §1125 与 §9999 → 点名 §9999。"""
    refs = [DEMO_LAWS[7].to_ref()]                  # §1125
    body = "依 §1125 成立；依 §9999 不成立。"
    a = audit_citations(body, refs)
    assert a.total == 2 and a.covered == 1, a.to_dict()
    assert a.unmatched == ["§9999"], a.unmatched
    print(f"  ✓ 美国法典部分命中：covered={a.covered}/{a.total}，点名 {a.unmatched}")


def test_audit_deterministic():
    refs = [r.to_ref() for r in RETURNED_DEMO]
    body = "依据第五百二十二条与第8888条。"
    a1, a2 = audit_citations(body, refs), audit_citations(body, refs)
    assert a1.to_dict() == a2.to_dict(), "同一输入两次自检结论不一致——确定性被破坏"
    print("  ✓ 确定性：同一输入两次自检结论逐字段一致")


def test_audit_empty_returned():
    a = audit_citations("依据第五百二十二条。", [])
    assert a.total == 1 and a.covered == 0 and a.ok is False
    print("  ✓ 边界：工具零返回 → 全部判未覆盖")


# ---------------------------------------------------------------------------
# 四、第二段自检（法条适用性）
# ---------------------------------------------------------------------------

def test_same_law():
    assert same_law("民法", "民法（日本民法典）") is True
    assert same_law("会社法", "会社法") is True
    assert same_law("民法", "会社法") is False
    assert same_law("", "民法") is False
    print("  ✓ sameLaw：名称互含即同法")


def test_applicability_in_and_out_of_scope():
    sk = KG.skeleton("涉外合资经营合同纠纷")
    assert sk is not None, "图谱未命中案由"
    law_names = sk["lawNames"]
    assert "会社法" in law_names and "民法" in law_names, law_names

    refs = [DEMO_LAWS[5].to_ref(),                   # 会社法 —— 在范围内
            DEMO_LAWS[8].to_ref()]                   # §1051（Title 15）—— 视名称互含而定
    a = audit_applicability(refs, law_names)
    assert a.checked == 2, a.checked
    assert "会社法" in a.in_scope, a.in_scope
    rep = applicability_report(a)
    assert "请求权基础" in rep
    print(f"  ✓ 适用性：in_scope={a.in_scope} out_of_scope={a.out_of_scope}")


def test_applicability_skip_without_case():
    a = audit_applicability([], [])
    assert "跳过适用性校验" in applicability_report(a)
    print("  ✓ 边界：未命中案由 → 跳过适用性校验")


# ---------------------------------------------------------------------------
# 五、知识图谱（对齐 db.rs 种子与 kg.ts skeletonOf）
# ---------------------------------------------------------------------------

def test_kg_seed_cases():
    cases = [sc.case for sc in __import__("faron_agentgroup.kg",
                                          fromlist=["KG_SEED"]).KG_SEED]
    assert "涉外货物买卖合同纠纷" in cases
    assert "涉外合资经营合同纠纷" in cases
    print(f"  ✓ 图谱种子案由：{cases}")


def test_kg_find_case():
    assert KG.find_case("本合同为中外合资经营合同，约定出资与董事会席位") == "涉外合资经营合同纠纷"
    assert KG.find_case("提单、信用证、货款支付与验收发生争议") == "涉外货物买卖合同纠纷"
    assert KG.find_case("今天天气不错") is None
    print("  ✓ 案由匹配：合资 / 货物买卖 / 无命中")


def test_kg_skeleton_structure():
    sk = KG.skeleton("涉外合资经营合同纠纷")
    assert sk is not None
    assert sk["case"] == "涉外合资经营合同纠纷"
    names = [e["name"] for e in sk["elements"]]
    assert "出资义务与验资" in names, names
    assert "违约责任与损害赔偿" in names, names
    # 要件必须挂到请求权基础
    for e in sk["elements"]:
        assert "laws" in e and "evidences" in e
    assert sk["issues"] and sk["docs"] and sk["lawNames"]
    print(f"  ✓ 骨架结构：{len(sk['elements'])} 要件 / {len(sk['lawNames'])} 法条 / "
          f"{len(sk['issues'])} 争点 / {len(sk['docs'])} 文书")


def test_kg_law_nodes_have_no_article_numbers():
    """★ 官方设计约束：图谱里的法条节点只写法律名，不写条号（避免编造）。"""
    import re
    sk = KG.skeleton("涉外合资经营合同纠纷")
    for name in sk["lawNames"]:
        assert not re.search(r"第[0-9零一二三四五六七八九十百千万]+条", name), \
            f"图谱法条节点不应含条号：{name}"
        assert not re.search(r"§", name), f"图谱法条节点不应含条号：{name}"
    print(f"  ✓ 设计约束：{len(sk['lawNames'])} 个法条节点全部只有法律名、无条号")


def test_kg_candidate_edge_needs_confirmation():
    """候选边机制：低置信度登记 → 重复登记返回 None → 人工确认后升为 1.0。"""
    kg = __import__("faron_agentgroup.kg", fromlist=["KnowledgeGraph"]).KnowledgeGraph()
    eid = kg.add_candidate("涉外合资经营合同纠纷", "手形法")
    assert eid is not None, "首次登记应返回 edge_id"
    edge = kg.edges[eid]
    assert edge.confirmed is False and edge.is_candidate is True, edge
    assert kg.add_candidate("涉外合资经营合同纠纷", "手形法") is None, "重复登记应返回 None"
    assert kg.confirm_edge(eid, True) is True
    assert kg.edges[eid].confirmed is True and kg.edges[eid].confidence == 1.0
    print("  ✓ 候选边：登记(0.6) → 幂等 → 人工确认(1.0)")


def test_kg_confirm_reject_deletes():
    kg = __import__("faron_agentgroup.kg", fromlist=["KnowledgeGraph"]).KnowledgeGraph()
    eid = kg.add_candidate("涉外货物买卖合同纠纷", "海商法")
    assert kg.confirm_edge(eid, False) is True
    assert eid not in kg.edges, "拒绝后该边应被删除"
    print("  ✓ 候选边：拒绝即删除")


# ---------------------------------------------------------------------------
# 六、端到端：检索 → 图谱 → 起草 → 两段自检
# ---------------------------------------------------------------------------

def test_end_to_end_two_stage():
    """模拟真实链路：图谱定案由 → 检索登记 → 起草（埋雷）→ 两段自检。"""
    reg = RefRegistry()

    # ① 图谱：定案由 + 取骨架
    case_name = KG.find_case("中外合资经营合同，出资与董事会争议")
    assert case_name == "涉外合资经营合同纠纷", case_name
    sk = KG.skeleton(case_name)
    assert sk is not None

    # ② 检索：真实命中并登记进「工具真实返回」
    for a in DEMO_LAWS:
        if a.article_no in ("第五百二十二条", "第五百四十一条"):
            reg.record(a.to_ref())
    assert len(reg.refs) == 2, len(reg.refs)

    # ③ 起草：写 3 处引用，其中 1 处凭记忆编造
    body = ("一、合同基本情况\n"
            "二、逐条风险与修改建议\n"
            "依据第五百二十二条与第五百四十一条，日方出资迟延构成违约。\n"
            "另依据第12345条，该条款无效。\n"
            "四、引用自检\n（待质检员填写）\n")

    # ④ 第一段：引用真实性
    a1 = audit_citations(body, reg.refs)
    assert a1.total == 3, a1.total
    assert a1.covered == 2, a1.covered
    assert a1.ok is False
    assert a1.unmatched == ["第12345条"], a1.unmatched

    # ⑤ 第二段：适用性
    a2 = audit_applicability(reg.refs, sk["lawNames"])
    assert a2.checked == 1, a2.checked          # 两条都属「民法」→ 去重后 1 部
    assert "民法" in a2.in_scope, a2.in_scope

    print("  ✓ 端到端两段自检：")
    print(f"     第一段 {a1.covered}/{a1.total} 命中，点名 {a1.unmatched}")
    print(f"     第二段 in_scope={a2.in_scope} out_of_scope={a2.out_of_scope}")


# ---------------------------------------------------------------------------
# 运行器
# ---------------------------------------------------------------------------

GROUPS = [
    ("一、token 抽取（对齐 extractCitationTokens）", [
        test_extract_basic_cn_jp, test_extract_jp_sub_article,
        test_extract_us_section_variants, test_extract_dedup_preserves_order,
        test_extract_empty]),
    ("二、覆盖判定（对齐 normArticleNo / articleCovers）", [
        test_norm_article_no, test_article_covers]),
    ("三、第一段自检", [
        test_audit_pass, test_audit_catch_fake_citation,
        test_audit_catch_fake_us_section, test_audit_partial_coverage_us,
        test_audit_us_partial_with_miss,
        test_audit_deterministic, test_audit_empty_returned]),
    ("四、第二段自检（适用性）", [
        test_same_law, test_applicability_in_and_out_of_scope,
        test_applicability_skip_without_case]),
    ("五、知识图谱（对齐 db.rs 种子）", [
        test_kg_seed_cases, test_kg_find_case, test_kg_skeleton_structure,
        test_kg_law_nodes_have_no_article_numbers,
        test_kg_candidate_edge_needs_confirmation,
        test_kg_confirm_reject_deletes]),
    ("六、端到端两段自检", [test_end_to_end_two_stage]),
]


def main() -> int:
    print("=" * 74)
    print("引用自检与知识图谱 · 测试向量（对齐官方规则）")
    print("=" * 74)
    passed = failed = 0
    for title, fns in GROUPS:
        print(f"\n{title}")
        for fn in fns:
            try:
                fn()
                passed += 1
            except AssertionError as exc:
                failed += 1
                print(f"  ✗ {fn.__name__} 失败：{exc}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  ✗ {fn.__name__} 异常：{type(exc).__name__}: {exc}")
    print("\n" + "=" * 74)
    print(f"结果：{passed} 通过 / {failed} 失败 / 共 {passed + failed}")
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
