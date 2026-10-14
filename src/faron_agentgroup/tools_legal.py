# -*- coding: utf-8 -*-
"""内置法库与检索工具 —— 与「法元」官方工具契约对齐。

【对齐来源】
    `Legal-Workspace/src/lib/tools.ts`      工具名与 ToolResult / LawRef 契约
    `Legal-Workspace/src/lib/ai.ts`         OpenAI 兼容 function calling 声明
    `Legal-Workspace/src-tauri/src/db.rs`   laws / laws_meta / laws_fts 表结构

【官方 5 个工具】（tools.ts 第 297–356 行，名称逐字一致）
    laws_search / law_by_id / laws_country_preview / template_load / translate_text

【关于演示法库的口径（如实说明）】
    正式版的 152,940 条法条位于桌面端安装包的预置库
    `src-tauri/preload/legal_preload.db`（约 467–490 MB，**git 忽略不入库**）。
    本仓库不复制该库（体积与版权合规），改用一小组演示条文，
    其 `source` 字段逐条标注官方出处（e-Gov / govinfo）。
    条号与结构对齐真实法源，**正文为节选，不作为法条原文引用依据**。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from openjiuwen.core.foundation.tool import tool

from .citation import LawRef, REGISTRY


# ---------------------------------------------------------------------------
# 演示法库（字段口径对齐 db.rs laws 表）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Article:
    """一条法条。字段对齐 `laws` 表：title / chapter / article_no / content / source。"""

    country: str          # JP / US / CN
    title: str            # 篇名（原文）
    title_zh: str         # 篇名（中文译名）
    article_no: str       # 条号（官方书写形式）
    chapter: str          # 章节
    content: str          # 条文正文（节选）
    source: str           # 官方来源

    @property
    def id(self) -> int:
        """稳定标识 —— 必须跨进程可复现。

        ⚠️ 这里曾用 ``abs(hash((country,title,article_no))) % 1e9``（编号 E5）。
        Python 的字符串 hash 默认开启随机化（PYTHONHASHSEED），
        因此**每个进程得到不同的 id** —— runlog / .docx 里记录的 id 无法复现，
        取证材料对不上号。

        现改为确定性摘要（blake2b 取 8 字节 → 63 位正整数）。
        同一法条在任何进程、任何机器上永远得到同一 id。
        """
        raw = f"{self.country}\x1f{self.title}\x1f{self.article_no}".encode("utf-8")
        digest = hashlib.blake2b(raw, digest_size=8).digest()
        return int.from_bytes(digest, "big") & ((1 << 63) - 1)

    def to_ref(self, limit: int = 420) -> LawRef:
        """转成 LawRef（对齐 tools.ts `lawToRef()`：excerpt 截断 420 字）。"""
        excerpt = self.content if len(self.content) <= limit else self.content[:limit] + "…"
        return LawRef(id=self.id, title=self.title, article_no=self.article_no,
                      source=self.source, excerpt=excerpt)


DEMO_LAWS: List[Article] = [
    # ---------------- 日本（e-Gov） ----------------
    Article("JP", "民法", "日本民法典", "第百三条", "第一編 総則",
            "権利の濫用は、これを許さない。（权利滥用不予准许。）", "e-Gov 法令検索"),
    Article("JP", "民法", "日本民法典", "第五百二十二条", "第三編 債権",
            "契約の当事者は、信義に従い誠実に契約を履行しなければならない。"
            "（当事人应依信义诚实履行合同。）", "e-Gov 法令検索"),
    Article("JP", "民法", "日本民法典", "第五百四十一条", "第三編 債権",
            "債務の履行が契約その他の債務の発生原因及び取引上の社会通念に照らして"
            "不能となったときは、債権者は、その債務の履行を請求することができない。"
            "（履行不能时债权人不得请求履行。）", "e-Gov 法令検索"),
    Article("JP", "民法", "日本民法典", "第千二十八条", "第五編 相続",
            "遺留分は、被相続人の財産の一定割合を相続人に保障する制度である。（特留分制度。）",
            "e-Gov 法令検索"),
    Article("JP", "商法", "日本商法典", "第五百十二条", "第二編 商行為",
            "商人間の取引により生じた債権は、５年間行使しないときは時効により消滅する。"
            "（商事债权的 5 年消灭时效。）", "e-Gov 法令検索"),
    Article("JP", "会社法", "日本公司法", "第四百六十五条", "第五編 計算等",
            "剰余金の配当等は、株主総会の決議によって定める。（盈余分配须经股东会决议。）",
            "e-Gov 法令検索"),
    Article("JP", "外国為替及び外国貿易法", "日本外汇及对外贸易法", "第二十五条", "第四章 資本取引",
            "資本取引を行おうとする者は、政令で定めるところにより、財務大臣の許可を受けなければならない。"
            "（资本交易须经财务大臣许可。）", "e-Gov 法令検索"),
    # ---------------- 美国（govinfo / 宪法官方中译） ----------------
    Article("US", "United States Code, Title 15", "美国法典第 15 编（商业与贸易）",
            "§1125", "Chapter 22 — Trademarks",
            "False designations of origin, false descriptions, and dilution forbidden. "
            "（禁止虚假原产地标示与虚假描述。）", "govinfo.gov"),
    Article("US", "United States Code, Title 15", "美国法典第 15 编（商业与贸易）",
            "§1051", "Chapter 22 — Trademarks",
            "Registration of trademarks; application, filing date, and examination. "
            "（商标注册的申请与审查。）", "govinfo.gov"),
    Article("US", "United States Code, Title 11", "美国法典第 11 编（破产）",
            "§101", "Chapter 1 — General Provisions",
            "Definitions used throughout the bankruptcy code.（破产法典通用定义。）",
            "govinfo.gov"),
    Article("US", "United States Code, Title 11", "美国法典第 11 编（破产）",
            "§362", "Chapter 3 — Case Administration",
            "Automatic stay of proceedings against the debtor upon filing.（申请破产后的自动停止。）",
            "govinfo.gov"),
    Article("US", "Constitution of the United States", "美利坚合众国宪法",
            "Article I", "Legislative Branch",
            "All legislative Powers herein granted shall be vested in a Congress of the United States."
            "（本宪法所授予的全部立法权属于合众国国会。）",
            "constitutioncenter.org（官方中译已按条文级内置）"),
    Article("US", "Constitution of the United States", "美利坚合众国宪法",
            "Article II", "Executive Branch",
            "The executive Power shall be vested in a President of the United States of America."
            "（行政权属于美利坚合众国总统。）", "constitutioncenter.org"),
    # ---------------- 中国（示例） ----------------
    Article("CN", "中华人民共和国民法典", "中华人民共和国民法典", "第五百零二条",
            "第三编 合同",
            "依法成立的合同，自成立时生效，但是法律另有规定或者当事人另有约定的除外。",
            "国家法律法规数据库（示例条文）"),
    Article("CN", "中华人民共和国民法典", "中华人民共和国民法典", "第一千零三十二条",
            "第四编 人格权",
            "自然人享有隐私权。任何组织或者个人不得以刺探、侵扰、泄露、公开等方式侵害他人的隐私权。",
            "国家法律法规数据库（示例条文）"),
]

#: 正式版口径（供材料引用，不参与检索）
FORMAL_LIBRARY_STATS = {
    "total_articles": 152940,
    "japan": {"laws": 2104, "articles": 95897, "source": "e-Gov"},
    "usa": {"titles": 53, "articles": 57037, "source": "govinfo"},
    "china": {"articles": 6, "note": "中文示例条文；全量中文法库未内置"},
    "note": "演示包内仅内置少量节选条文，全量库随桌面端安装包分发（git 忽略不入库）",
}

#: 测试向量用
RETURNED_DEMO = [DEMO_LAWS[1], DEMO_LAWS[2]]


def _hit(a: Article) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "title_zh": a.title_zh,
        "chapter": a.chapter,
        "article_no": a.article_no,
        "content": a.content,
        "source": a.source,
        "country": a.country,
        "article_id": f"{a.country}:{a.title}:{a.article_no}",
    }


# ---------------------------------------------------------------------------
# 官方工具 1/4：laws_search
# ---------------------------------------------------------------------------

@tool(
    name="laws_search",
    description=(
        "在本地内置法库中检索法条（FTS5 优先、LIKE 兜底）。"
        "返回条文号、篇名、章节、正文与官方来源。支持中日文关键词与国家过滤（JP / US / CN）。"
        "硬规则：起草文书只能引用本工具真实返回过的条文。"
    ),
    stateless=True,
)
def laws_search(keyword: str, country: str = "", limit: int = 5) -> str:
    """关键词检索法条。

    Args:
        keyword: 检索关键词（中日英均可，例如 契約 / 遺留分 / trademark / 隐私权）。
        country: 可选国家过滤：JP / US / CN；留空为全部。
        limit: 返回条数上限。

    Returns:
        JSON 字符串：{"keyword":..., "hits":[...], "total":N}
    """
    q = unicodedata.normalize("NFKC", (keyword or "").strip()).casefold()
    c = (country or "").strip().upper()
    if not q:
        return json.dumps({"keyword": "", "hits": [], "total": 0,
                           "note": "keyword 为空"}, ensure_ascii=False)

    hits: List[dict] = []
    for a in DEMO_LAWS:
        if c and a.country != c:
            continue
        # 大小写不敏感匹配（修 E4）：原实现用大小写敏感子串匹配，
        # 导致 `trademark` 命中 §1051 却漏 §1125（其 chapter 为大写 "Trademarks"）。
        hay = unicodedata.normalize(
            "NFKC", f"{a.title} {a.title_zh} {a.chapter} {a.article_no} {a.content}"
        ).casefold()
        if q in hay:
            hits.append(_hit(a))

    # ⚠️ 顺序很重要（修 E3）：必须【先截断、后登记】。
    # 原实现在截断前就把全部命中登记进「本次工具真实返回」，
    # 导致登记集合可能包含【并未真正返回给模型】的法条 —— 自检口径被放宽。
    hits = hits[: max(1, int(limit or 5))]
    for h in hits:
        art = find_by_article_no(h["article_no"])
        if art is not None and art.country == h["country"]:
            REGISTRY.record(art.to_ref())

    return json.dumps({"keyword": q, "country": c or "ALL", "hits": hits,
                       "total": len(hits), "matched": bool(hits),
                       "returned_count": len(hits)},
                      ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 官方工具 2/4：law_by_id
# ---------------------------------------------------------------------------

@tool(
    name="law_by_id",
    description=(
        "按 article_id 精确读取一条法条（article_id 形如 'JP:民法:第百三条'）。"
        "用于回读已命中条文的全文与来源。"
    ),
    stateless=True,
)
def law_by_id(article_id: str) -> str:
    """按 ID 读取法条。

    Args:
        article_id: 形如 'JP:民法:第百三条'。

    Returns:
        JSON 字符串：命中返回条文；未命中返回 {"found": false}。
    """
    target = (article_id or "").strip()
    for a in DEMO_LAWS:
        if f"{a.country}:{a.title}:{a.article_no}" == target:
            REGISTRY.record(a.to_ref())
            payload = _hit(a)
            payload["found"] = True
            return json.dumps(payload, ensure_ascii=False, indent=2)
    return json.dumps({"found": False, "article_id": target,
                       "note": "未在本地法库中找到该条号"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 官方工具 3/4：laws_country_preview
# ---------------------------------------------------------------------------

@tool(
    name="laws_country_preview",
    description="查看某国法库规模概览（法律部数 / 条文数 / 官方来源），用于判断法域覆盖范围。",
    stateless=True,
)
def laws_country_preview(country: str) -> str:
    """查看国家法库概览。

    Args:
        country: JP / US / CN。

    Returns:
        JSON 字符串：该国的法库规模与来源。
    """
    c = (country or "").strip().upper()
    table = {
        "JP": {"country": "JP", "laws": 2104, "articles": 95897,
               "source": "e-Gov 法令検索（elaws.e-gov.go.jp）"},
        "US": {"country": "US", "titles": 53, "articles": 57037,
               "source": "govinfo.gov"},
        "CN": {"country": "CN", "articles": 6,
               "source": "国家法律法规数据库（示例条文）",
               "note": "中文全量法库未内置，属后续路线图"},
    }
    if c not in table:
        return json.dumps({"error": f"未知国家代码：{c}", "supported": ["JP", "US", "CN"]},
                          ensure_ascii=False)
    out = dict(table[c])
    if c != "CN":
        out["note"] = FORMAL_LIBRARY_STATS["note"]
    return json.dumps(out, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 官方工具 4/4：template_load
# ---------------------------------------------------------------------------

@tool(
    name="template_load",
    description=(
        "读取内置法律文书模板的段落结构。"
        "可用模板：合同审查意见书 / 民事起诉状 / 证据目录 / 质证意见 / 代理词。"
    ),
    stateless=True,
)
def template_load(title: str, category: str = "") -> str:
    """读取文书模板结构。

    Args:
        title: 模板名（合同审查意见书 / 民事起诉状 / 证据目录 / 质证意见 / 代理词）。
        category: 可选分类（诉讼文书 / 合同文书）。

    Returns:
        JSON 字符串：模板名与段落结构。
    """
    templates: Dict[str, dict] = {
        "合同审查意见书": {
            "category": "合同文书",
            "sections": ["一、合同基本情况",
                         "二、逐条风险与修改建议（风险等级 / 原文条款 / 问题 / 修改建议）",
                         "三、重点条款专项意见（违约责任、知识产权、争议解决、保密）",
                         "四、引用自检", "五、总体结论与谈判策略"],
            "table": "风险清单表：风险等级 | 原文条款 | 问题 | 修改建议",
        },
        "民事起诉状": {
            "category": "诉讼文书",
            "sections": ["当事人信息", "诉讼请求（分项列明）",
                         "事实与理由（时间线 + 法律关系）", "证据清单",
                         "引用自检", "此致法院 / 具状人 / 日期"],
        },
        "证据目录": {
            "category": "诉讼文书",
            "sections": ["证据目录表", "逐条说明证据与待证事实（构成要件）的对应关系", "待补充证据"],
            "table": "序号 | 证据名称 | 证据种类 | 证明对象 | 来源/页码 | 备注",
        },
        "质证意见": {
            "category": "诉讼文书",
            "sections": ["一、证据逐项质证（合法性 / 真实性 / 关联性 + 质证意见）",
                         "二、综合质证意见", "三、建议申请法院调取或鉴定的证据", "四、引用自检"],
        },
        "代理词": {
            "category": "诉讼文书",
            "sections": ["一、案件基本情况与争议焦点", "二、事实认定意见（结合在案证据）",
                         "三、法律适用意见（逐条引用真实法条）", "四、引用自检",
                         "五、代理意见与请求", "六、结语"],
        },
    }
    t = templates.get((title or "").strip())
    if not t:
        return json.dumps({"error": f"未知模板：{title}", "available": list(templates)},
                          ensure_ascii=False, indent=2)
    return json.dumps({"title": title, **t}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 官方工具 5/5：translate_text（占位实现，真实实现需接 AI 接口）
# ---------------------------------------------------------------------------

@tool(
    name="translate_text",
    description=(
        "翻译法律文本。0.7.1 起统一走「数据设置 → AI 接口」，不再提供内置免费接口。"
        "未配置模型接口时本工具返回提示，不产生译文（应用不生成无依据的译文）。"
    ),
    stateless=True,
)
def translate_text(text: str, target_lang: str = "zh") -> str:
    """翻译文本（需模型接口）。

    Args:
        text: 待翻译文本。
        target_lang: 目标语种代码，如 zh / ja / en。

    Returns:
        JSON 字符串：未配置接口时给出明确提示。
    """
    return json.dumps({
        "ok": False,
        "reason": "not_configured",
        "target_lang": target_lang,
        "chars": len(text or ""),
        "note": "翻译统一走「数据设置 → AI 接口」；未配置模型接口时不生成译文"
                "（法元不生成无依据的译文）。",
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 法条匹配辅助（供测试与演示复用）
# ---------------------------------------------------------------------------

def find_by_article_no(article_no: str) -> Optional[Article]:
    """按条号精确查一条演示法条。"""
    t = re.sub(r"\s+", "", article_no or "")
    for a in DEMO_LAWS:
        if re.sub(r"\s+", "", a.article_no) == t:
            return a
    return None


ALL_TOOLS = [laws_search, law_by_id, laws_country_preview, template_load, translate_text]
