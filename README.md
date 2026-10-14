# faron-openjiuwen-agentgroup

> **法元 · Faron × openJiuwen** —— 面向涉外法律文书交付的多智能体协同编排
> 参赛作品：首届 **openJiuwen 智能体创新大赛**（主题「智体共生 · 创新无限」）
> 承载框架：**openJiuwen `agent-core`（`openjiuwen.agent_teams`）原生 AgentGroup**
> 版本：v0.2 ｜ 2026-10-13

---

## 这是什么

本仓库把「[法元 · Faron](https://github.com/lin612320/Legal-Workspace)」文书智能体的**编排层**
迁移到 openJiuwen 官方 AgentGroup 框架，并保留法元自研的**两段确定性自检**作为框架之上的可信层。

```
┌──────────────────────────────────────────────────────────────────┐
│  openJiuwen agent_teams   →   解决「一起干活」                     │
│                               任务板 / 成员协同 / HITL 人在环 /      │
│                               模型池 / 跨进程消息总线                │
├──────────────────────────────────────────────────────────────────┤
│  法元两段确定性自检        →   解决「干得可信」                     │
│    第一段 audit_citations：引用是否真实存在（能否在工具真实返回中命中）│
│    第二段 audit_applicability：是否落在案由图谱请求权基础范围内       │
└──────────────────────────────────────────────────────────────────┘
```

**一句话**：框架解决协同与编排，我们解决可信与可验收。

---

## 为什么这件事值得做

通用 Agent 会说「我查过了」。在高风险域（法律、医疗、金融），
**「模型自称查过」不是证据**。

本仓库把「引用是否成立」变成一个**代码级规则判定**：

- 不调用任何模型；
- 结论只依赖 `(正文, 工具真实返回集合, 案由图谱)`；
- 同样输入永远得到同样输出。

因此它**可以用反例现场验证**——这正是本仓库可被评审独立复现的原因。

---

## 团队编制（6 成员 / 12 工具）

| 成员 | `role_type` | 职责 | 挂载工具 |
|---|---|---|---|
| **小元·主理** | `LEADER` | 定案由 → 取骨架 → 建单分派 → 汇总交付 | `kg_find_case` `kg_query` `audit_citations` `audit_applicability` `returned_refs_summary` |
| **检索员·民商** | `TEAMMATE` | 本地法库真实检索 + 溯源 | `laws_search` `law_by_id` `laws_country_preview` |
| **图谱策展** | `TEAMMATE` | 案由匹配 / 骨架 / 候选边登记 | `kg_find_case` `kg_query` `kg_add_candidate` `kg_confirm_edge` |
| **起草员** | `TEAMMATE` | 依模板与可引用范围起草 | `template_load` `returned_refs_summary` `translate_text` |
| **质检员·两段自检** | `TEAMMATE` | 引用真实性 + 适用性 | `audit_citations` `audit_applicability` `returned_refs_summary` |
| **人类复核员** | `HUMAN_AGENT` | 审批计划卡 / 复核自检结论 | — |

**`desc` / `prompt` 语义**（来自 openJiuwen 官方 schema）：
`desc` = 公开简介，是唯一进入同伴 roster 的字段；
`prompt` = 私有工作约定，只注入自己的系统提示词。

---

## 使用的 openJiuwen 组件与能力

> 对应赛事答题要求：「如使用 openJiuwen 生态，请说明使用了哪些组件/能力」。

| openJiuwen 组件 | 在本项目中的用途 | 收益 |
|---|---|---|
| `openjiuwen.agent_teams.TeamAgentSpec` | 团队与成员规格装配 | 声明式定义，JSON 可序列化、可跨进程分发 |
| `LeaderSpec` / `TeamMemberSpec` | 主理与成员身份（`desc` 公开 / `prompt` 私有） | 官方 schema 原生表达身份隔离 |
| `TeamRole` | 角色体系（`LEADER` / `TEAMMATE` / `HUMAN_AGENT`） | 人员与真人统一建模 |
| `enable_hitt`（Human-in-the-Team） | 计划卡「需人工确认」闸门 | 框架级人审，替代自研闸门 |
| 任务板工具 `create_task` / `claim_task` / `view_task` / `member_complete_task` | 任务分派与认领 | 官方协同协议，替代自研状态机 |
| 消息工具 `send_message` | 成员间唯一联系通道 | 官方通信协议 |
| `list_members` | roster 查询 | 成员自查同伴 |
| `model_pool` / `model_pool_strategy`（`by_model_name`） | 按能力档位给成员分配模型 | 多端点分摊，兑现「多模型编排」 |
| `StorageSpec`（sqlite） | 团队与任务持久化 | 与本地优先定位一致 |
| `TransportSpec`（inprocess） | 成员间消息总线 | 单机零依赖 |
| `TeamAgent.stream()` / `interact()` / `human_agent_say()` | 运行、介入、人审发言 | 官方运行接口 |
| `openjiuwen.core.foundation.tool.tool` | 把法元工具声明为 `LocalFunction` | 官方工具协议 |
| `Runner.resource_mgr.add_tool()` | 工具注册 | 官方资源管理 |

---

## 快速开始

### 环境

```bash
pip install openjiuwen==0.1.19
pip install opentelemetry-exporter-otlp-proto-http opentelemetry-exporter-otlp-proto-grpc
```

> ⚠️ `build()` 需要 `opentelemetry-exporter-otlp-proto-*`，否则在可观测性作用域处报
> `ModuleNotFoundError: No module named 'opentelemetry.exporter'`。

Python 3.11–3.13（在 3.12.10 上验证）。

### 三步复现（不需要任何模型 Key）

```bash
# 1. 验证 spec 可被 openJiuwen 官方框架构建
python probe_build.py
#    期望：build() 成功：TeamAgent role=leader

# 2. 引用自检与知识图谱的测试向量（24 组，含反例点名）
python tests/test_citation_audit.py
#    期望：24 通过 / 0 失败

# 3. 离线端到端：图谱定案由 → 检索 → 起草 → 两段自检 → 导出 .docx
python run_offline_demo.py
#    期望：6 步全绿，runtime/ 下生成新的 deliverable_*.docx
```

### 在线运行（需要模型接口）

```bash
export FARON_LLM_API_BASE="https://api.deepseek.com/v1"
export FARON_LLM_API_KEY="sk-xxxx"
export FARON_LLM_MODEL_STRONG="deepseek-chat"
export FARON_LLM_MODEL_FAST="deepseek-chat"

python run_online.py --probe   # 先探测连通性
python run_online.py           # 由 6 个成员自主完成一次委托
```

---

## 最该看的一条证据

`runtime/deliverable_20261013-232806.docx` 的「四、引用自检」段：

> 识别到条文号引用 2 处（去重）
> 与「本次工具真实返回」法条对应：1/2
> 以下引用未在工具返回中找到对应条文（可能来自用户材料原文或模型笔误，请人工核实后再采用）：
> **「第9999条」**

`第9999条` 是**故意埋进起草稿的库外条号**，被代码级规则当场点名——不是模型自查。
文末附 **2 张 Word 原生表格**：第一段逐条判定 + 第二段适用性校验。

---

## 与上游实现的对齐

本仓库的 Python 实现**逐条对齐**法元桌面端的 TypeScript/Rust 实现，
避免 TS/Python 双端行为漂移：

| 对齐项 | 上游源码位置 |
|---|---|
| 引用抽取正则 | [`Legal-Workspace/src/lib/agent.ts`](https://github.com/lin612320/Legal-Workspace) 第 610–611 行 |
| 归一化与覆盖判定 | `agent.ts` 第 625–635 行 |
| 两段自检 | `agent.ts` 第 599–717 行 |
| 四角色系统提示词 | `agent.ts` 第 351–357 行 |
| 5 类任务与交付物骨架 | `agent.ts` 第 95–140 行 |
| 图谱种子与 5 种固定关系 | `src-tauri/src/db.rs` 第 1267–1337 行 |
| 图谱骨架抽取 | `src/lib/kg.ts` `skeletonOf()` |
| 节点/边契约与候选边阈值 0.8 | `src/lib/kgTypes.ts` |
| 5 个工具契约 | `src/lib/tools.ts` |

**对齐基线**：`feature/赛事版` @ `e8dd45c`（0.7.2）

### 复核中发现的 2 个上游问题

| # | 问题 | 说明 |
|---|---|---|
| **G11** | 引用正则漏掉字母款项 `§1125(a)` | 正则里 `(?:\(\d+\))?` 只允许纯数字款项（`(1)`），而美国法典实务多为 `(a)`。后果：`§1125(a)` 与 `§1125` 归一化后相同、被合并为 1 处。**一行修复**：`\(\d+\)` → `\([0-9a-zA-Z]+\)` |
| **G12** | 图谱法名（中）与法库篇名（英）不一致 | 图谱「美国法典 Title 15 — 商业与贸易」vs 法库 `United States Code, Title 15`，`sameLaw` 名称互含判不出 → 适用性误报。`kg_node.name_alt` 字段已存在但种子未填 |

详见 [`docs/02-源码级复核补充.docx`](docs/02-源码级复核补充.docx) 与
[`docs/01-贴合度评估与整改建议.md`](docs/01-贴合度评估与整改建议.md) §八。

---

## 目录结构

```
faron-openjiuwen-agentgroup/
├── README.md                     ← 本文件
├── LICENSE                       Apache-2.0（与 openJiuwen 生态一致）
├── requirements.txt
├── .gitignore  .gitattributes  .env.example  conftest.py
│
├── docs/                         ★ 评估、方案与实现说明
│   ├── 01-贴合度评估与整改建议.md   11 项整改清单（G1–G12）+ 17 天路线图
│   ├── 02-源码级复核补充.docx      源码级复核发现的 2 个上游问题
│   ├── 03-AgentGroup方案.md       框架设计 / 通信协议 / 接口定义 / 模型选型
│   └── 04-AgentGroup实现说明.md
│
├── src/faron_agentgroup/         ★ Agent Group 实现
│   ├── __init__.py
│   ├── citation.py               引用解析 + 两段自检（逐条对齐 agent.ts）
│   ├── kg.py                     知识图谱（对齐 db.rs 种子与 kg.ts）
│   ├── tools_legal.py            法库 + 官方 5 个工具
│   ├── audit.py                  两段自检与图谱工具（Agent 可调用）
│   ├── config.py                 模型池 / 5 类任务 / 四角色提示词
│   └── group.py                  Agent Group 规格装配 + 门面
│
├── tests/test_citation_audit.py  24 组测试向量
├── probe_build.py                最小构建探针
├── run_offline_demo.py           端到端演示（不需要模型）
├── run_online.py                 在线运行（需要模型）
├── runtime/                      产出：交付物 .docx + 取证日志 .json
│
├── 资料/                          ★ 参赛材料（提交包整理版）
│   ├── README.md                 材料导航
│   ├── 大文件说明.md              两个超限大文件的 SHA256 与获取方式
│   ├── README-评委先读.md          建议最先读
│   ├── 01-演示视频-分镜与素材/      分镜 + 3套字幕 + 2套配音稿 + 品牌素材
│   ├── 02-产品介绍PPT/
│   ├── 03-项目计划书/
│   ├── 04-产品演示站/              demo.html（单文件零依赖，双击离线可开）
│   ├── 05-移动端与安装说明/
│   └── 06-用户调研/                107 份问卷 + 结果 PDF
│
└── 源码/                          ★ 上游内部文档与仓库元信息
    ├── README.md                 文档导航 + 对齐依据说明
    ├── Legal-Workspace/          上游 README / CHANGELOG / package.json
    └── Legal-Workspace-docs/      docs/01–12 内部文档（技术架构/数据库/路线图/联邦配方进化）
```

---

## 协作与推送

仓库公开，`main` 分支。使用 **Git Credential Manager** 授权，无需 PAT：

```bash
git clone https://github.com/thinanphen/faron-openjiuwen-agentgroup.git
cd faron-openjiuwen-agentgroup

# 首次 push 会弹浏览器，点 Authorize 即可；凭据存进系统凭据管理器
git add -A
git commit -m "your message"
git push
```

> 大文件（477 MB 演示视频、135 MB 安装包）**不在仓库里**，见
> [`资料/大文件说明.md`](资料/大文件说明.md) —— 含 SHA256 校验值与三种获取方式。

---


## 测试覆盖

| 组 | 用例数 | 内容 |
|---|---|---|
| 一、token 抽取 | 5 | 中日文条号 / 日文 `の·之·ノ` 分条 / 美国法典 `§NN` 变体 / 去重保序 / 边界 |
| 二、覆盖判定 | 2 | 归一化 / 前缀覆盖语义 |
| 三、第一段自检 | 7 | 正向 / **反例点名** / 美国法典反例 / 官方粒度 / 部分命中 / 确定性 / 零返回 |
| 四、第二段自检 | 3 | `sameLaw` / 在范围与超范围 / 未命中案由跳过 |
| 五、知识图谱 | 6 | 种子案由 / 案由匹配 / 骨架结构 / **法条节点无条号约束** / 候选边确认 / 候选边拒绝 |
| 六、端到端 | 1 | 图谱 → 检索 → 起草 → 两段自检 |
| **合计** | **24** | |

---

## 如实说明的边界

1. **演示法库仅 15 条**。正式版的 **152,940 条**位于法元桌面端安装包的预置库
   `legal_preload.db`（约 467–490 MB）。该库在[上游仓库](https://github.com/lin612320/Legal-Workspace)
   中**明确标注 git 忽略、不入库**，本仓库因体积与版权合规未复制。
   演示条文的 `source` 字段逐条标注官方出处（e-Gov / govinfo / 国家法律法规数据库），
   **不作为法条原文引用依据**。
2. **模型接口凭据不在仓库内**。在线运行需自备 `FARON_LLM_API_KEY`。
   开发环境所用开放平台走校园 OIDC 登录，凭据由应用托管、不落在环境变量中，
   因此本仓库默认以**离线路径**交付可复现结论。
3. **`translate_text` 是占位实现**。上游 0.7.1 起已移除内置免费翻译接口、统一走 AI 接口；
   本实现如实返回 `not_configured`，不生成无依据译文。
4. **`spawn_mode=inprocess`**：单机部署形态，与法元「本地优先」定位一致。
5. **`redis` 缺失**仅产生 WARNING（在线训练 rail 工厂不可用），不影响团队构建与运行。

---

## 许可与出处

- 本仓库代码：**Apache-2.0**（与 openJiuwen 生态一致）
- openJiuwen SDK：`openjiuwen` 0.1.19 ｜ [gitcode.com/openJiuwen/agent-core](https://gitcode.com/openJiuwen/agent-core)
- 参赛项目源码：[github.com/lin612320/Legal-Workspace](https://github.com/lin612320/Legal-Workspace)
- 赛事页：[developer.huaweicloud.com/competition/information/1300000328](https://developer.huaweicloud.com/competition/information/1300000328/introduction)

> 本仓库为参赛作品的一部分，知识产权按赛事规则由出题单位、参赛者、官方竞赛平台三方共享。
