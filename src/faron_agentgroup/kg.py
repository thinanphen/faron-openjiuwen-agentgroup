# -*- coding: utf-8 -*-
"""知识图谱 —— 与「法元」官方实现逐条对齐。

【对齐来源】
    `Legal-Workspace/src-tauri/src/db.rs`    第 1267–1430 行（种子与关系常量）
    `Legal-Workspace/src-tauri/src/db.rs`    kg_node / kg_edge 表结构
    `Legal-Workspace/src/lib/kgTypes.ts`     节点/边契约与候选边阈值
    `Legal-Workspace/src/lib/kg.ts`          skeletonOf() / describeSkeleton()

【照抄过来的两条设计约束（很重要）】
    1. **法条节点只写「法律名」，不写具体条号**——原注释：
       「人工策展的案由种子（涉外优先；法条节点只写「法律名」，不写具体条号，避免编造）」
       这是从源头杜绝编造条号的设计，本实现严格继承。
    2. **候选边需人工确认**：confidence < 0.8 视为候选边；任务真实命中的法条
       只登记为低置信度候选边，`confirmed` 后才作为后续规划依据。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# 关系类型（固定 5 种，方向固定）—— 对齐 db.rs 第 1271–1275 行
# ---------------------------------------------------------------------------

KG_REL_ELEMENT = "构成要件是"    # case    → element
KG_REL_LAW = "请求权基础是"      # element → law
KG_REL_EVIDENCE = "证明对象是"   # element → evidence
KG_REL_ISSUE = "常见争点是"      # case    → issue
KG_REL_DOC = "文书载体是"        # case    → doc

#: 节点类型中文名 —— 对齐 kg.ts `KG_TYPE_LABEL`
KG_TYPE_LABEL: Dict[str, str] = {
    "case": "案由",
    "element": "构成要件",
    "law": "法条",
    "evidence": "证据种类",
    "doc": "文书结构",
    "issue": "争议焦点",
}

#: 候选边阈值 —— 对齐 kgTypes.ts `KG_CANDIDATE_CONFIDENCE`
KG_CANDIDATE_CONFIDENCE = 0.8


# ---------------------------------------------------------------------------
# 数据模型 —— 对齐 kgTypes.ts KgNode / KgEdge
# ---------------------------------------------------------------------------

@dataclass
class KgNode:
    id: int
    type: str                  # case | element | law | evidence | doc | issue
    name: str
    name_alt: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 1.0
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "name": self.name,
                "name_alt": self.name_alt, "source": self.source,
                "confidence": self.confidence, "note": self.note}


@dataclass
class KgEdge:
    id: int
    src: int
    rel: str
    dst: int
    weight: float = 1.0
    source: Optional[str] = None
    confidence: float = 1.0
    confirmed: bool = False

    @property
    def is_candidate(self) -> bool:
        """置信度低于阈值 → 候选边，需人工复核。"""
        return self.confidence < KG_CANDIDATE_CONFIDENCE

    def to_dict(self) -> dict:
        return {"id": self.id, "src": self.src, "rel": self.rel, "dst": self.dst,
                "weight": self.weight, "source": self.source,
                "confidence": self.confidence, "confirmed": self.confirmed}


# ---------------------------------------------------------------------------
# 人工策展的案由种子 —— 逐字对齐 db.rs KG_SEED（第 1289–1337 行）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KgSeedCase:
    case: str
    keywords: Sequence[str]
    elements: Sequence[tuple]      # (构成要件, 请求权基础法律名列表)
    evidences: Sequence[tuple]     # (证据种类, 对应要件)
    issues: Sequence[str]
    docs: Sequence[str]


KG_SEED: List[KgSeedCase] = [
    KgSeedCase(
        case="涉外货物买卖合同纠纷",
        keywords=["货物买卖", "买卖合同", "交付", "验收", "货款", "提单",
                  "出口", "进口", "信用证"],
        elements=[
            ("合同成立与生效", ["民法", "美国法典 Title 15 — 商业与贸易"]),
            ("标的物交付与验收", ["民法"]),
            ("价款支付与结算", ["民法", "商法"]),
            ("违约责任与损害赔偿", ["民法"]),
            ("争议解决与法律适用", ["民事訴訟法"]),
        ],
        evidences=[
            ("书面合同/订单", "合同成立与生效"),
            ("往来函件与电子邮件", "合同成立与生效"),
            ("提单与运输单据", "标的物交付与验收"),
            ("检验报告/验收单", "标的物交付与验收"),
            ("发票与付款凭证", "价款支付与结算"),
            ("催告函与回函", "违约责任与损害赔偿"),
        ],
        issues=["合同效力争议", "交付与验收争议", "货款支付争议",
                "违约金过高", "管辖与法律适用争议"],
        docs=["合同审查意见书", "民事起诉状", "证据目录", "质证意见", "代理词"],
    ),
    KgSeedCase(
        case="涉外合资经营合同纠纷",
        keywords=["合资", "合营", "出资", "股权", "章程", "董事会",
                  "利润分配", "退出"],
        elements=[
            ("出资义务与验资", ["会社法"]),
            ("公司治理与决策程序", ["会社法"]),
            ("利润分配与财务", ["会社法", "美国法典 Title 15 — 商业与贸易"]),
            ("股权转让与退出", ["会社法"]),
            ("违约责任与损害赔偿", ["民法"]),
        ],
        evidences=[
            ("合资合同/合营协议", "出资义务与验资"),
            ("公司章程", "公司治理与决策程序"),
            ("出资凭证与验资报告", "出资义务与验资"),
            ("董事会/股东会决议", "公司治理与决策程序"),
            ("审计报告与财务报表", "利润分配与财务"),
        ],
        issues=["出资违约", "控制权与表决权争议", "利润分配争议", "股权转让效力"],
        docs=["合同审查意见书", "民事起诉状", "证据目录", "质证意见", "代理词"],
    ),
]


# ---------------------------------------------------------------------------
# 内存图谱（对应 db.rs 的 kg_node / kg_edge 表 + 幂等播种）
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """案由 → 构成要件 → 请求权基础 / 证据 / 争点 / 文书载体。

    对齐 db.rs：`(type,name)` 唯一、`(src,rel,dst)` 唯一，播种幂等。
    """

    def __init__(self) -> None:
        self.nodes: Dict[int, KgNode] = {}
        self.edges: Dict[int, KgEdge] = {}
        self._node_key: Dict[tuple, int] = {}
        self._edge_key: Dict[tuple, int] = {}
        self._next_node = 1
        self._next_edge = 1
        self._seed()

    # ---- 幂等取或插 ----

    def node_id(self, ntype: str, name: str, name_alt: Optional[str] = None,
                source: Optional[str] = None, confidence: float = 1.0,
                note: Optional[str] = None) -> int:
        key = (ntype, name)
        if key in self._node_key:
            return self._node_key[key]
        nid = self._next_node
        self._next_node += 1
        self.nodes[nid] = KgNode(id=nid, type=ntype, name=name, name_alt=name_alt,
                                 source=source, confidence=confidence, note=note)
        self._node_key[key] = nid
        return nid

    def edge_id(self, src: int, rel: str, dst: int, weight: float = 1.0,
                source: Optional[str] = None, confidence: float = 1.0,
                confirmed: bool = False) -> int:
        key = (src, rel, dst)
        if key in self._edge_key:
            return self._edge_key[key]
        eid = self._next_edge
        self._next_edge += 1
        self.edges[eid] = KgEdge(id=eid, src=src, rel=rel, dst=dst, weight=weight,
                                 source=source, confidence=confidence,
                                 confirmed=confirmed)
        self._edge_key[key] = eid
        return eid

    # ---- 播种（对齐 seed_kg_if_empty）----

    def _seed(self) -> None:
        for sc in KG_SEED:
            c = self.node_id("case", sc.case, source="人工策展", confidence=1.0)
            for el_name, laws in sc.elements:
                e = self.node_id("element", el_name, source="人工策展")
                self.edge_id(c, KG_REL_ELEMENT, e, source="人工策展", confirmed=True)
                for law in laws:
                    l = self.node_id("law", law, source="人工策展", confidence=1.0,
                                     note="只写法律名，不写具体条号（避免编造）")
                    self.edge_id(e, KG_REL_LAW, l, source="人工策展", confirmed=True)
            for ev_name, el_name in sc.evidences:
                ev = self.node_id("evidence", ev_name, source="人工策展")
                e = self.node_id("element", el_name)
                self.edge_id(e, KG_REL_EVIDENCE, ev, source="人工策展", confirmed=True)
            for issue in sc.issues:
                i = self.node_id("issue", issue, source="人工策展")
                self.edge_id(c, KG_REL_ISSUE, i, source="人工策展", confirmed=True)
            for doc in sc.docs:
                d = self.node_id("doc", doc, source="人工策展")
                self.edge_id(c, KG_REL_DOC, d, source="人工策展", confirmed=True)

    # ---- 查询（对齐 kg_list / kg_query / kg_find_case）----

    def list_all(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [e.to_dict() for e in self.edges.values()]}

    def query_case(self, case_name: str) -> Optional[dict]:
        """某案由的子图（2 跳内）。对齐 db.rs `kg_query`。"""
        root = self._node_key.get(("case", case_name))
        if root is None:
            return None
        hit_nodes = {root}
        hit_edges = []
        for e in self.edges.values():
            if e.src == root or e.dst == root:
                hit_edges.append(e)
                hit_nodes.update((e.src, e.dst))
        # 第 2 跳
        hop1 = set(hit_nodes)
        for e in self.edges.values():
            if e.src in hop1 or e.dst in hop1:
                if e not in hit_edges:
                    hit_edges.append(e)
                hit_nodes.update((e.src, e.dst))
        return {
            "case": case_name,
            "root": root,
            "nodes": [self.nodes[i].to_dict() for i in sorted(hit_nodes)],
            "edges": [e.to_dict() for e in hit_edges],
        }

    def find_case(self, text: str) -> Optional[str]:
        """按关键词把任务材料归到某个案由。对齐 db.rs `kg_find_case`。

        取命中关键词数最多的案由；平局取种子顺序靠前者。
        """
        if not text:
            return None
        best, best_hits = None, 0
        for sc in KG_SEED:
            hits = sum(1 for kw in sc.keywords if kw in text)
            if hits > best_hits:
                best, best_hits = sc.case, hits
        return best

    def add_candidate(self, case_name: str, law_title: str,
                      task_id: Optional[int] = None) -> Optional[int]:
        """运行期候选边：任务真实命中的法条挂到案由下（低置信度，待人工确认）。

        对齐 db.rs `kg_add_candidate`：重复登记返回 None。
        """
        c = self._node_key.get(("case", case_name))
        if c is None:
            return None
        l = self.node_id("law", law_title, source="任务观测", confidence=0.6)
        key = (c, KG_REL_LAW, l)
        if key in self._edge_key:
            return None
        return self.edge_id(c, KG_REL_LAW, l, weight=0.5, source="任务观测",
                            confidence=0.6, confirmed=False)

    def confirm_edge(self, edge_id: int, confirmed: bool) -> bool:
        """人工确认 / 拒绝一条候选边（拒绝即删除）。对齐 db.rs `kg_confirm_edge`。"""
        e = self.edges.get(edge_id)
        if e is None:
            return False
        if confirmed:
            e.confirmed = True
            e.confidence = 1.0
        else:
            del self.edges[edge_id]
            self._edge_key.pop((e.src, e.rel, e.dst), None)
        return True

    def skeleton(self, case_name: str) -> Optional[dict]:
        """图谱骨架 —— 对齐 kg.ts `skeletonOf()`。

        返回 {case, elements:[{name,laws,evidences}], issues, docs, lawNames}
        """
        sub = self.query_case(case_name)
        if sub is None:
            return None
        by_id = {n["id"]: n for n in sub["nodes"]}
        elements: Dict[int, dict] = {}
        issues: List[str] = []
        docs: List[str] = []

        for e in sub["edges"]:
            src, dst = by_id.get(e["src"]), by_id.get(e["dst"])
            if not src or not dst:
                continue
            if e["rel"] == KG_REL_ELEMENT and dst["type"] == "element":
                elements.setdefault(dst["id"], {"name": dst["name"],
                                                "laws": [], "evidences": []})
            elif e["rel"] == KG_REL_LAW and src["type"] == "element" and dst["type"] == "law":
                elements.setdefault(src["id"], {"name": src["name"],
                                                "laws": [], "evidences": []})
                elements[src["id"]]["laws"].append(dst["name"])
            elif e["rel"] == KG_REL_EVIDENCE and src["type"] == "element" and dst["type"] == "evidence":
                elements.setdefault(src["id"], {"name": src["name"],
                                                "laws": [], "evidences": []})
                elements[src["id"]]["evidences"].append(dst["name"])
            elif e["rel"] == KG_REL_ISSUE and dst["type"] == "issue":
                issues.append(dst["name"])
            elif e["rel"] == KG_REL_DOC and dst["type"] == "doc":
                docs.append(dst["name"])

        law_names = [n["name"] for n in sub["nodes"] if n["type"] == "law"]
        return {
            "case": case_name,
            "elements": list(elements.values()),
            "issues": list(dict.fromkeys(issues)),
            "docs": list(dict.fromkeys(docs)),
            "lawNames": list(dict.fromkeys(law_names)),
        }

    def describe_skeleton(self, sk: dict) -> str:
        """把骨架渲染成注入规划提示的一段文本。对齐 kg.ts `describeSkeleton()`。"""
        lines = [f"案由：{sk['case']}", "构成要件（须逐一覆盖）："]
        for el in sk["elements"]:
            laws = f"｜请求权基础：{'、'.join(el['laws'])}" if el["laws"] else ""
            evs = f"｜证据：{'、'.join(el['evidences'])}" if el["evidences"] else ""
            lines.append(f"- {el['name']}{laws}{evs}")
        if sk["issues"]:
            lines.append(f"争议焦点：{'、'.join(sk['issues'])}")
        if sk["docs"]:
            lines.append(f"相关文书：{'、'.join(sk['docs'])}")
        return "\n".join(lines)


#: 进程级图谱单例（对齐 db.rs 单库）
KG = KnowledgeGraph()
