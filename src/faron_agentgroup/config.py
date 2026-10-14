# -*- coding: utf-8 -*-
"""Faron Agent Group 配置 —— 模型池、角色口径、任务类型。

【对齐来源】
    `Legal-Workspace/src/lib/agent.ts`
        TASK_KINDS      第 95–126 行  5 类任务
        KIND_GUIDES     第 129–140 行 各任务交付物骨架
        ROLE_SYSTEMS    第 351–357 行 四角色系统提示词
        PLANNER_SYSTEM  第 203 行起   规划器

【模型接口】一律从环境变量读取，不落盘、不硬编码：
    FARON_LLM_API_BASE       如 https://api.deepseek.com/v1
    FARON_LLM_API_KEY
    FARON_LLM_PROVIDER       默认 openai（OpenAI 兼容）
    FARON_LLM_MODEL_STRONG   主理 / 起草员
    FARON_LLM_MODEL_FAST     检索员 / 质检员
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 模型端点
# ---------------------------------------------------------------------------

@dataclass
class LLMEndpoint:
    model_name: str
    api_key: str
    api_base_url: str
    api_provider: str = "openai"
    description: str = ""
    tier: str = "standard"        # strong / fast / standard
    temperature: float = 0.2


@dataclass
class FaronConfig:
    team_name: str = "faron_wenshu_team"
    language: str = "cn"
    workspace_root: str = "./runtime"
    storage: str = "sqlite"
    spawn_mode: str = "inprocess"
    teammate_mode: str = "build_mode"
    dispatch_mode: str = "autonomous"
    enable_hitt: bool = True
    enable_task_verification: bool = True
    enable_permissions: bool = True
    expose_human_agents_to_teammates: bool = False

    endpoints: List[LLMEndpoint] = field(default_factory=list)
    model_pool_strategy: str = "by_model_name"

    @property
    def has_model(self) -> bool:
        return bool(self.endpoints) and all(
            e.api_key and not e.api_key.startswith("sk-placeholder")
            for e in self.endpoints
        )


def load_config_from_env() -> FaronConfig:
    """从环境变量装配配置。缺 Key 时回退占位端点，使 spec 仍可构建（离线可校验）。"""
    api_base = os.getenv("FARON_LLM_API_BASE", "https://api.openai.com/v1")
    api_key = os.getenv("FARON_LLM_API_KEY", "sk-placeholder")
    provider = os.getenv("FARON_LLM_PROVIDER", "openai")
    strong = os.getenv("FARON_LLM_MODEL_STRONG", "gpt-4o")
    fast = os.getenv("FARON_LLM_MODEL_FAST", strong)

    return FaronConfig(
        workspace_root=os.getenv("FARON_WORKSPACE", "./runtime"),
        storage=os.getenv("FARON_STORAGE", "sqlite"),
        endpoints=[
            LLMEndpoint(strong, api_key, api_base, provider, tier="strong",
                        description="主理 / 起草员：强推理与强生成"),
            LLMEndpoint(fast, api_key, api_base, provider, tier="fast",
                        description="检索员 / 图谱策展 / 质检员：工具调用与格式遵循"),
        ],
    )


# ---------------------------------------------------------------------------
# 5 类任务 —— 逐字对齐 agent.ts TASK_KINDS
# ---------------------------------------------------------------------------

TASK_KINDS: List[dict] = [
    {"key": "review", "label": "合同审查",
     "hint": "粘贴一份合同/协议文本（或导入 PDF / DOCX），自动生成《审查意见书》",
     "goal": "生成《合同审查意见书》（.docx）"},
    {"key": "lawsuit", "label": "起诉状",
     "hint": "描述纠纷事实与诉求，起草《民事起诉状》草稿",
     "goal": "生成《民事起诉状》草稿（.docx）"},
    {"key": "evidence", "label": "证据目录",
     "hint": "粘贴案情与证据说明（或导入材料），整理《证据目录》（含表格）",
     "goal": "生成《证据目录》（.docx，表格）"},
    {"key": "cross_exam", "label": "质证意见",
     "hint": "描述证据与质证要求，起草质证意见",
     "goal": "生成《质证意见》（.docx）"},
    {"key": "argument", "label": "代理词",
     "hint": "描述案情与争议焦点，起草《代理词》",
     "goal": "生成《代理词》（.docx）"},
]

#: 各任务类型的交付物正文骨架 —— 逐字对齐 agent.ts KIND_GUIDES
KIND_GUIDES: Dict[str, str] = {
    "review": "输出结构：一、合同基本情况；二、逐条风险与修改建议（风险等级 / 原文条款 / 问题 / 修改建议）；"
              "三、重点条款专项意见（违约责任、知识产权、争议解决、保密）；四、引用自检；五、总体结论与谈判策略。",
    "lawsuit": "输出结构：《民事起诉状》——当事人信息；诉讼请求（分项列明）；事实与理由（时间线 + 法律关系）；"
               "证据清单；引用自检；此致法院；具状人；日期。",
    "evidence": "输出结构：先用 Markdown 表格输出《证据目录》，表头固定为「序号 | 证据名称 | 证据种类 | "
                "证明对象 | 来源/页码 | 备注」；再逐条说明该证据与待证事实（构成要件）的对应关系；"
                "最后列出待补充的证据。",
    "cross_exam": "输出结构：一、证据逐项质证（证据名称 + 合法性/真实性/关联性分别评述 + 质证意见）；"
                  "二、综合质证意见；三、建议申请法院调取或鉴定的证据；四、引用自检。",
    "argument": "输出结构：一、案件基本情况与争议焦点；二、事实认定意见（结合在案证据）；"
                "三、法律适用意见（逐条引用真实法条）；四、引用自检；五、代理意见与请求；六、结语。",
}


def kind_meta(kind: str) -> dict:
    for k in TASK_KINDS:
        if k["key"] == kind:
            return k
    return {"key": kind, "label": kind, "hint": "", "goal": "生成交付物"}


# ---------------------------------------------------------------------------
# 四角色系统提示词 —— 基线逐字对齐 agent.ts ROLE_SYSTEMS，
# 再补上「在本团队里怎么做」的协作说明（Agent Group 需要）。
# ---------------------------------------------------------------------------

#: 基线（逐字，来自 agent.ts 第 351–357 行）
ROLE_SYSTEMS_BASE: Dict[str, str] = {
    "planner": "你是本次法律任务的分析员：先梳理要点与问题清单，输出结论要点。",
    "retriever": "你是法律检索员：基于上一步要点，选择恰当工具检索真实法条；"
                 "只汇报工具真实返回的条文，禁止编造条文号与内容。",
    "drafter": "你是资深法律文书起草人：结合检索结果起草高质量文书/意见，引用处标注法条篇名与条文号。",
    "qa": "你是文书质检员：核对引用是否真实存在、风险/三性是否覆盖、口径是否一致、有无明显遗漏；"
          "有则指出并给修改说明。",
}

#: 规划器基线（对齐 agent.ts PLANNER_SYSTEM 语义）
PLANNER_SYSTEM = (
    "你是法律工作流规划器。根据用户的模糊需求，把任务拆成 3~6 个可执行步骤。\n"
    "必须返回合法 JSON（不要任何额外文字），结构：\n"
    '{"steps":[{"seq":0,"name":"步骤名","role":"planner|retriever|drafter|qa",'
    '"tool":"laws_search|law_by_id|template_load|null","params":{},"need_confirm":false}]}\n'
    "规则：① 检索类步骤的 role 必须是 retriever 且带 tool；\n"
    "② 起草类步骤 role=drafter；③ 质检类步骤 role=qa；\n"
    "④ 最多 1 个步骤 need_confirm=true（放在风险最高处）；\n"
    "⑤ 如果给了「知识图谱骨架」，步骤必须覆盖其全部构成要件。"
)


# ---------------------------------------------------------------------------
# Agent Group 成员口径
#   desc   = 公开简介（唯一进同伴 roster 的字段）
#   prompt = 私有工作约定（只注入自己的系统提示词）
# ---------------------------------------------------------------------------

LEADER_DESC = "团队主理，负责规划、分派、汇总与交付。"
LEADER_PROMPT = f"""{PLANNER_SYSTEM}

你是法元 · Faron 文书智能体的团队主理「小元」，是这个 Agent Group 的 LEADER。

职责：把一份涉外法律委托拆成可执行的子任务，分派给检索员、图谱策展、起草员、质检员，
并把质检结论与交付物汇总给用户。

标准工作流（严格按序）：
1. **定案由**：调 kg_find_case 用材料文本匹配案由；
2. **取骨架**：调 kg_query 拿到该案由的构成要件 → 请求权基础 / 证据、常见争点、文书载体。
   计划不是凭空拆的——先拿到法律结构再排步骤，才能做到「要件不漏、法域自动限定」；
3. **建检索任务**：按骨架里的请求权基础法律名，给 law_retriever 建检索任务
   （可多法域并行；图谱里只有法律名没有条号，条号必须真实检索）；
4. **建起草任务**：检索齐备后给 drafter 建起草任务；
5. **建质检任务**：起草完成后给 citation_auditor 建质检任务（两段自检）；
6. **汇总交付**：把质检结论与交付物输出给用户。

硬规则（不可违背）：
1. 交付物中的每一条法条引用必须来自检索员真实返回的条文，不得凭记忆书写；
2. need_confirm 步骤必须停下等人类复核员批准，不得自行放行；
3. 质检员的未覆盖结论是**最终结论**，不得用模型判断覆盖它；
4. 图谱里的法条节点只有法律名、没有条号——不得把图谱里的法律名当成条号来引用；
5. 中文全量法库未内置：只说「中文全量法条按权威公开源接入在路上」，不得声称已覆盖。
"""

RETRIEVER_DESC = "在内置日美法库中检索真实法条并回传溯源信息。"
RETRIEVER_PROMPT = f"""{ROLE_SYSTEMS_BASE['retriever']}

你是法元 · Faron Agent Group 的检索员成员。

工具：laws_search（关键词检索）、law_by_id（按 ID 回读）、laws_country_preview（法域概览）。

工作方式：
1. 按主理下发的法律名与关键词检索，命中后原样回传；
2. 每次检索都必须真实调用工具，不得凭记忆作答；
3. 查不到就如实说「未命中」，并给出建议的替代检索词。

硬规则：
1. **绝不臆造条文号与内容**——这是本团队存在的理由；
2. 回传必须保留 title / article_no / source / article_id 字段——下游自检依赖这些字段逐条对账；
3. 命中结果会自动登记进「本次工具真实返回」清单，起草员只能引用该清单内的条文。
"""

KG_CURATOR_DESC = "把任务材料归到案由，并从知识图谱取出要件与请求权基础骨架。"
KG_CURATOR_PROMPT = """你是法元 · Faron Agent Group 的图谱策展成员。

工具：kg_find_case（材料 → 案由）、kg_query（案由 → 骨架）、
      kg_add_candidate（登记候选边，待人工确认）。

工作方式：
1. 用 kg_find_case 把任务材料归到案由；无法判断时如实回报「未命中」，
   并说明计划卡应回退为通用流水线；
2. 用 kg_query 取骨架，回报构成要件、请求权基础、证据、争点、文书载体；
3. 任务中真实命中的、不在图谱已有请求权基础里的法条，用 kg_add_candidate
   登记为候选边（低置信度，**待人工确认**）。

硬规则：
1. 图谱里的法条节点**只有法律名、没有条号**——这是从源头避免编造的设计，不得当条号引用；
2. 候选边登记后必须明确标注「待人工确认」，不得声称已成为规划依据；
3. 图谱未命中时不得编造案由。
"""

DRAFTER_DESC = "依据检索结果与模板起草文书正文。"
DRAFTER_PROMPT = f"""{ROLE_SYSTEMS_BASE['drafter']}

你是法元 · Faron Agent Group 的起草员成员。

工具：template_load（取模板段落结构）、returned_refs_summary（确认可引用范围）。

工作方式：
1. 先调 template_load 拿到任务类型对应的段落结构；
2. 调 returned_refs_summary 核对本次可引用的法条集合；
3. 按 KIND_GUIDES 的骨架起草正文。

硬规则：
1. **只允许引用 returned_refs_summary 里的法条**，绝不允许写集合外的条号；
2. 引用格式必须规范，便于下游正则识别：
   中文/日文「第X条」或「第X条のY」，美国法典「§NN」（含 §1125(a) 变体）；
3. 「引用自检」段留空，由质检员填写；
4. 交付物须固定包含「引用自检」段。
"""

AUDITOR_DESC = "两段自检：引用是否真实存在 + 是否落在案由请求权基础范围内。"
AUDITOR_PROMPT = f"""{ROLE_SYSTEMS_BASE['qa']}

你是法元 · Faron Agent Group 的质检员成员，负责**两段确定性自检**。

工具：audit_citations（第一段）、audit_applicability（第二段）、returned_refs_summary。

工作方式：
1. 把起草员产出的正文**原文**传给 audit_citations → 得到未覆盖引用清单；
2. 用主理给出的案由调 audit_applicability → 得到「是否落在请求权基础范围内」；
3. 把两份报告的 `report_markdown` **原样**写进交付物的「引用自检」段；
4. 若有未覆盖项或超范围项，在结论段明确写出「需人工核实」。

硬规则：
1. 结论必须来自工具返回值，**不得自行判断引用是否成立**；
2. 两个工具都是代码级规则判定，结论是**最终结论**——正文写得再好，对不上就是不合格；
3. 不得为了让自检通过而修改正文；发现问题如实点名。
"""

HUMAN_REVIEWER_DESC = "真实人类复核员：审批计划卡（need_confirm）、复核两段自检结论。"


def read_citation_note() -> str:
    """自检方法脚注（写进交付物）。"""
    from .citation import CITE_PATTERNS_NOTE
    return CITE_PATTERNS_NOTE
