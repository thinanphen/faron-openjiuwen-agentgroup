# 法元 · Faron Agent Group（v0.2 — 对齐真实源码）

> 基于 **openJiuwen `agent-core`（`openjiuwen.agent_teams`）** 的多智能体协同编排。
> **逐条对齐** 法元真实实现：`Legal-Workspace` `feature/赛事版` @ 0.7.2
> 方案文档：[`03-AgentGroup方案.md`](03-AgentGroup方案.md)
> 2026-10-13 ｜ **已在真机跑通：24/24 测试通过 + 端到端出 .docx**

---

## 一、为什么要「对齐真实源码」

第一版 Agent Group 是我基于**提交包材料**（README / 计划书 / 分镜）推断实现的。
拿到真实仓库后逐行核对，发现**推断版与真实实现在 3 处不一致**——若不修正，
交付给评委的 Python 侧行为会与桌面端 TS 侧行为**打架**，恰好违反法元自己
「口径一致是我们对评委的基本尊重」这条原则。

| 项 | 推断版（v0.1） | **真实实现（v0.2 已对齐）** |
|---|---|---|
| 引用抽取正则 | 我自己写的，含 `Article I`、中日文数字解析 | 官方 `/第[0-9〇零一二三四五六七八九十百千万]+条(?:(?:之\|の\|ノ)[…]+)?\|§\s*\d+(?:[.\-]\d+)?(?:\(\d+\))?/g` |
| 覆盖判定 | 归一化为 `article:103` 规范键做集合比较 | 官方 `articleCovers`：归一化（去空白+去括号）后**完全相等 或 条文号以引用为前缀** |
| 知识图谱 | 我自造的「请求权基础」结构 | 官方 `kg_node`/`kg_edge` + **5 种固定关系** + 真实种子（2 个涉外案由） |
| 自检段数 | 1 段 | **2 段**（引用真实性 + 法条适用性） |
| 工具集 | 我命名 | 官方 5 个：`laws_search`/`law_by_id`/`laws_country_preview`/`template_load`/`translate_text` |
| 任务类型 | 自造 | 官方 5 类 + `KIND_GUIDES` 骨架 |
| 角色提示词 | 自造 | 官方 `ROLE_SYSTEMS`（planner/retriever/drafter/qa）为基线 |

---

## 二、从真实源码照抄过来的两条设计约束

这两条不是我加的，是原注释里写着的，**本实现严格继承**：

### 2.1 图谱法条节点只写法律名，不写条号

> 原注释（`db.rs` 第 1277 行）：
> 「人工策展的案由种子（涉外优先；**法条节点只写「法律名」，不写具体条号，避免编造**）」

这是**从源头杜绝编造条号**的设计——图谱负责「该查哪部法」，条号必须由
`laws_search` 真实检索得到。所以 Leader 的提示词里我加了一条硬规则：
「图谱里的法条节点只有法律名、没有条号，不得把法律名当成条号来引用」。

✅ 有测试固化：`test_kg_law_nodes_have_no_article_numbers`

### 2.2 候选边需人工确认

> `kgTypes.ts`：`KG_CANDIDATE_CONFIDENCE = 0.8`，「置信度低于此值的关系需要人工复核」

任务真实命中的、不在图谱已有请求权基础里的法，只登记为 **0.6 置信度的候选边**，
`confirmed=true` 后才升为 1.0 并作为后续规划依据。

✅ 有测试固化：`test_kg_candidate_edge_needs_confirmation` / `test_kg_confirm_reject_deletes`

---

## 三、团队编制（6 成员 / 12 工具）

| 成员 | `role_type` | 职责 | 挂载工具 |
|---|---|---|---|
| **小元·主理** | `LEADER` | 定案由 → 取骨架 → 建单分派 → 汇总交付 | `kg_find_case` `kg_query` `audit_citations` `audit_applicability` `returned_refs_summary` |
| **检索员·民商** | `TEAMMATE` | 本地法库真实检索 + 溯源 | `laws_search` `law_by_id` `laws_country_preview` |
| **图谱策展** | `TEAMMATE` | 案由匹配 / 骨架 / 候选边登记 | `kg_find_case` `kg_query` `kg_add_candidate` `kg_confirm_edge` |
| **起草员** | `TEAMMATE` | 依模板与可引用范围起草 | `template_load` `returned_refs_summary` `translate_text` |
| **质检员·两段自检** | `TEAMMATE` | 引用真实性 + 适用性 | `audit_citations` `audit_applicability` `returned_refs_summary` |
| **人类复核员** | `HUMAN_AGENT` | 审批计划卡 / 复核自检结论 | — |

**`desc` / `prompt` 语义**（来自官方 schema）：
`desc` = 公开简介，唯一进同伴 roster 的字段；`prompt` = 私有工作约定，只注入自己的系统提示词。

---

## 四、快速开始

```bash
pip install openjiuwen==0.1.19
pip install opentelemetry-exporter-otlp-proto-http opentelemetry-exporter-otlp-proto-grpc

cd faron-openjiuwen-agentgroup
python probe_build.py                 # spec 可被官方框架构建
python tests/test_citation_audit.py   # 31 组向量（含★反例点名）
python run_offline_demo.py            # 端到端出 .docx，不需要模型
```

在线运行（需模型 Key）：

```powershell
$env:FARON_LLM_API_BASE="https://api.deepseek.com/v1"
$env:FARON_LLM_API_KEY="sk-xxxx"
$env:FARON_LLM_MODEL_STRONG="deepseek-chat"
$env:FARON_LLM_MODEL_FAST="deepseek-chat"
python run_online.py --probe
python run_online.py
```

---

## 五、两段确定性自检（核心资产）

```
正文里的每一处法条引用
    ↓ extract_citation_tokens()      官方正则（中日文条号 / 日文分条 / 美国法典 §NN）
token 去重
    ↓ article_covers()               归一化后：完全相等 或 条文号以引用为前缀
第一段：能否在「本次工具真实返回」中找到 → 未覆盖项点名
    ↓ same_law()                     名称互含即同法
第二段：是否落在案由图谱的请求权基础范围内 → 超范围项列出
```

**纯函数性质**：不调用模型；结论只依赖 `(正文, 工具真实返回集合, 案由图谱)`；同输入必同输出。

### 实测结论

```
三、第一段自检
  ✓ 正向：2 处引用全部命中 → ok=True
  ✓ 反例：库外条号被点名 → ['第9999条']
  ✓ 反例（美国法典）：工具零返回美国法条 → 3 处全部点名
  ✓ 官方粒度：§1125 与 §1125(a) 归一化后合并为 1 处
  ✓ 确定性：同一输入两次自检结论逐字段一致
  ✓ 边界：工具零返回 → 全部判未覆盖

四、第二段自检（适用性）
  ✓ sameLaw：名称互含即同法
  ✓ 适用性：in_scope=['会社法'] out_of_scope=['United States Code, Title 15']

五、知识图谱（对齐 db.rs 种子）
  ✓ 图谱种子案由：['涉外货物买卖合同纠纷', '涉外合资经营合同纠纷']
  ✓ 骨架结构：5 要件 / 3 法条 / 4 争点 / 5 文书
  ✓ 设计约束：3 个法条节点全部只有法律名、无条号
  ✓ 候选边：登记(0.6) → 幂等 → 人工确认(1.0)
  ✓ 候选边：拒绝即删除
```

---

## 六、对齐过程中发现的 2 个真实问题（回写评估建议）

### G11 · 官方正则的 `§NN(n)` 覆盖缺口

实测（Python `re` 与 JS `matchAll` 语义一致，均为全局非重叠匹配）：

```
'Under §1125(a)' → token 为 '§1125'，捕获组 (\d+) 的 (a) 后缀未被纳入
```

后果：`§1125(a)` 与 `§1125` 归一化后都是 `"§1125"`，**两处引用被当成同一处**。
对「同一法条不同款项」这种高频引用形式，自检粒度偏粗。
但方向是**偏严**——`§9999` 之类依然会被如实点名，不会漏报编造条号。

> 建议：若要精细到款项，把 `(?:\(\d+\))?` 移到非捕获组并去掉其后的 `\d+` 贪婪边界，
> 或改为 `§\s*(\d+)(?:[.\-]\d+)?((?:\([0-9a-zA-Z]+\))*)` 同时捕获条号与款项。
> **本实现选择逐字对齐官方**，并在测试里固化真实行为，避免「测试通过但实现与官方不一致」。

### G12 · 图谱法名与法库篇名的中英不一致导致适用性误报

第二段自检用 `sameLaw`（名称互含）判定「是否落在图谱请求权基础范围内」。
图谱里的法名是中文（如「美国法典 Title 15 — 商业与贸易」），
而法库返回的篇名是英文（如 `United States Code, Title 15`），
两者互不包含 → **被误判为「超范围」**。

实测表现（本次端到端演示）：

```
本次引用法条 3 部，落在案由范围内的 2 部
以下引用不在本案由图谱范围内（可能仍然相关，请人工判断）：「United States Code, Title 15」
```

> 影响：这是**误报**而非漏报（安全方向），但会给用户带来噪音。
> 建议：给 `kg_node` 的 `name_alt` 字段填入英文别名（表结构里**已经有这个字段**，
> 只是种子没用），并让 `sameLaw` 同时比对 `name` 与 `name_alt`。

---

## 七、目录结构

```

├── faron_agentgroup/
│   ├── __init__.py            包入口与导出
│   ├── citation.py            ★ 引用解析 + 两段自检（逐条对齐 agent.ts）
│   ├── kg.py                  ★ 知识图谱（对齐 db.rs 种子与 kg.ts skeletonOf）
│   ├── tools_legal.py         法库 + 官方 5 个工具
│   ├── audit.py               两段自检与图谱工具（Agent 可调用）
│   ├── config.py              模型池 / 5 类任务 / 四角色提示词
│   └── group.py               ★ Agent Group 规格装配 + 门面
├── tests/
│   ├── test_citation_audit.py 31 组向量（对齐官方 + 反例 + 图谱）
│   ├── test_assembly.py       9 组装配防线（E1 回归）
│   └── verify_zero_dep.py     零依赖验证（屏蔽全部框架 import）
├── probe_build.py             最小构建探针
├── run_offline_demo.py        端到端演示（不需要模型）
├── run_online.py              在线运行（需要模型）
└── runtime/                   输出：交付物 .docx + 取证日志 .json
```

---

## 八、已知边界（如实说明）

1. **演示法库 15 条**：`source` 逐条标注官方出处。正式版 **152,940 条**位于
   桌面端安装包预置库 `legal_preload.db`（467–490 MB，**git 忽略不入库**，
   源码 README 第 158 行明确写了这一点）。**演示条文不作为法条原文引用依据。**
2. **模型 Key 不在仓库内**：在线运行需自备。开发机所用开放平台走校园 OIDC 登录，
   凭据由应用托管、不落在环境变量中。
3. **`translate_text` 是占位实现**：官方在 0.7.1 移除了内置免费接口，
   统一走 AI 接口；本实现如实返回 `not_configured`，不生成无依据译文。
4. **`spawn_mode=inprocess`**：单机部署（与法元本地优先定位一致）。
5. **`redis` 缺失**仅 WARNING，不影响构建与运行。
6. **正式接入桌面端**需把 `tools_legal.py` 接到 Rust 侧 SQLite + FTS5；
   `.docx` 导出仍走 `docx.rs`，不重写已经对的东西。

---

## 九、复现清单

| 项 | 命令 | 期望结果 |
|---|---|---|
| spec 可构建 | `python probe_build.py` | `build() 成功：TeamAgent role=leader` |
| 自检正确性 | `python tests/test_citation_audit.py` | `24 通过 / 0 失败` |
| 端到端交付 | `python run_offline_demo.py` | 生成 `runtime/deliverable_*.docx`（**2 张原生表格**） |
| 在线门槛 | `python run_online.py` | 无 Key 时返回 2 并给出离线替代路径 |

`runtime/runlog_*.json` 是全过程取证日志（含骨架 / 检索明细 / 两段自检 / 候选边），可供评审核验。
