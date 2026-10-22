# faron-openjiuwen-agentgroup

> **法元 · Faron × openJiuwen** —— 面向涉外法律文书交付的多智能体协同编排
> 参赛作品：首届 **openJiuwen 智能体创新大赛**（主题「智体共生 · 创新无限」）
> 承载框架：**openJiuwen `agent-core`（`openjiuwen.agent_teams`）原生 AgentGroup**
> 版本：v0.2 ｜ 2026-10-15

---

## 👋 先看这几份（按你的身份选）

| 文档 | 给谁 | 作用 |
|---|---|---|
| [**`交付说明.md`**](交付说明.md) | **接收交付的人**（队友 / 评委） | 这交付是什么 / 怎么零 Key 跑起来 / **目前做不到什么** / 桌面端补丁怎么打 |
| [**`决策摘要.md`**](决策摘要.md) | **给建议的人**（指导老师 / 合作方） | **一页纸**。现状 + 我们要请教的 5 个问题 + 需要你投入什么。**不必读仓库** |
| [**`接手必读.md`**](接手必读.md) | **人**（同伴） | 现在做到哪里 / 距比赛成品还差多少 / 待办 T1–T8 / 需要你拍板的 5 个方向 |
| [**`AI工作须知.md`**](AI工作须知.md) | **AI 助手** | 仓库布局 / 7 个技术事实 / **23 条硬性纪律（D1–D23）** / 验证命令与「什么算绿」/ 已踩过的坑 |
| [**`任务台账.md`**](任务台账.md) | **双方** | 工单交换板：领活、交活、下指令（含指令模板） |
| [**`答辩Q&A预案.md`**](答辩Q&A预案.md) | **要上台讲的人** | 10 个必答题的标准答（每答 ≤150 字）+ 5 条「不要踩」 |

> 你是被叫来接手工作的 AI？**请先读 `AI工作须知.md`，再去 `任务台账.md` 领一条活。**
> 不要凭猜测改这个仓库——里面有两条「踩了就是事故」的纪律（不得虚报、不得弱化「第9999条」反例）。
>
> 你是来做技术指导或判断要不要投资的？**只读 `决策摘要.md` 那一页就够了。**

---

## 🚀 一条命令复现全部验证

```bash
python tools/run_all_checks.py     # 期望：9 通过 / 0 未通过
```

> 不需要网络、不需要 API Key、不需要 openJiuwen 即可跑完 **9 项**（含 46 组 Python 测试、
> Skill 规范 14 条断言、提交物清单一致性）。**任何机器上结果一致。**

---

## 这是什么

「[法元 · Faron](https://github.com/lin612320/Legal-Workspace)」是一个跑在律师本机的
涉外法律文书智能体。本仓库承载它的**两块**：

1. **编排层** —— 用 openJiuwen `agent_teams` 原生 AgentGroup 承载 6 成员 / 12 工具的团队协同；
2. **可信层** —— 法元自研的**两段确定性引用自检**（不调用模型），作为框架之上的可信保障。

> **一句话主线**：openJiuwen 的 AgentGroup 解决「一起干活」；法元补上「干得可信」。

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
>
> ⚠️ **P1-4 修订**：本表严格区分「已装配（代码中存在）」与「规划中（代码中不存在）」。
> 赛事「参赛须知」把「提交任何虚假信息」列为取消资格项，
> 因此凡未落地的一律标注为规划中，**不计入已使用能力**。
> 同类标注也已加入 `docs/03-AgentGroup方案.md` 与 `docs/01-贴合度评估与整改建议.md`。

### 已装配（代码中可核验）

| openJiuwen 组件 | 在本项目中的用途 | 代码位置 |
|---|---|---|
| `TeamAgentSpec` / `LeaderSpec` / `TeamMemberSpec` | 团队与成员规格装配（6 成员 / 12 工具） | `src/faron_agentgroup/group.py` |
| `TeamRole`（`LEADER`/`TEAMMATE`/`HUMAN_AGENT`） | 角色体系，人员与真人统一建模 | `group.py` |
| `AgentCard` / `DeepAgentSpec` | 成员身份卡与私有工作约定（`desc` 公开 / `prompt` 私有） | `group.py` |
| `enable_hitt`（Human-in-the-Team） | 人类复核员成员（审批闸门） | `group.py`（值 `True`） |
| `model_pool` + `ModelPoolEntry` + `model_pool_strategy="by_model_name"` | 按能力档位给成员分配模型（强模型 / 轻量模型） | `group.py` |
| `ModelClientConfig` / `ModelRequestConfig` / `TeamModelConfig` | 模型端点配置 | `group.py` |
| `StorageSpec`（sqlite） | 团队与任务持久化 | `group.py` |
| `TransportSpec`（inprocess） | 成员间消息总线（单机） | `group.py` |
| `enable_permissions` | 权限收敛开关（法务场景） | `group.py` / `config.py` |
| `openjiuwen.core.foundation.tool.tool` | 把法元 12 个工具声明为 `LocalFunction` | `src/faron_agentgroup/tools_legal.py` / `audit.py` |
| `Runner.resource_mgr.add_tool()` | 工具注册（按 `Result` 判定成败） | `group.py` |
| `TeamAgentSpec.build()` / `model_dump_json()` / `model_validate_json()` | 构建与跨进程分发/恢复 | `probe_build.py` |
| `TeamAgent.stream()` / `interact()` / `human_agent_say()` | 运行、介入、人审发言接口 | `group.py` 门面 |

### 规划中（代码中**不存在**，不计入已使用能力）

| 组件 | 当前状态 | 说明 |
|---|---|---|
| `create_task`（任务板建单） | ✅ **已真实驱动** | 经 `TeamTaskManager.add_graph` 真实落库；见「运行层现状」 |
| `spawn_teammate`（动态召唤成员） | ✅ **已真实驱动**（R9） | 经 `TeamBackend.spawn_member`；成员名须匹配 `[a-z][a-z0-9-]*`（**下划线非法**） |
| `update_task` / `assign`（指派） | ✅ **已真实驱动**（R9） | assignee 能正确落库到 `team_task_*` |
| `send_message` / `broadcast_message`（成员消息） | ✅ **已真实驱动** | 经 `TeamMessageManager` 真实流转；见「运行层现状」 |
| `claim_task` / `member_complete_task`（成员领活/交付） | 🚧 **未跑通** | 成员 round 从未启动（`[NativeHarness] round_id` 只对主理出现；消息 `is_read=0` 一直未读），**尚无运行事实** |
| HITL 审批（`verify_task`） | 🚧 **未跑通** | 依赖上一条，未触发 |
| `dispatch_mode="scheduled"` | 🚧 **规划中** | 当前实例为 `autonomous`（默认值） |
| `enable_swarmflow` | 🚧 **规划中** | 未启用 |
| `model_router` / `model_intelli_router` | 🚧 **规划中** | 未配置；当前用 `model_pool` |
| 跨进程传输 `pyzmq` / `hybrid` | 🚧 **规划中** | 当前为 `inprocess` 单机 |
| `openjiuwen.symphony` | ❌ **未采用** | 仅方案评估阶段提及，代码中零引用 |
| `openjiuwen.agent_teams.memory` / `reliability` | ❌ **未采用** | 未配置 |

### 运行层现状（如实说明）

> **模型为本地确定性桩（stub），框架任务板与成员消息为真实流转。**

**装配层是真的；运行层只跑通「主理侧」的一半，成员侧未跑通。**

- **装配层**：`probe_build.py` 逐成员验证——5 个 agent 成员各自解析到
  **自己的 spec 与工具集**（不同 spec 对象数 5/5），`build()` 成功构造 `TeamAgent`。
  这条有测试防线：`tests/test_assembly.py`（9 组）。
- **运行层（已跑通的部分）**：`run_stub_online.py` 用**本地确定性 OpenAI 桩**
  （`tools/stub_llm_server.py`，零三方依赖）驱动**真实 `TeamAgent`**：
  主理 `build_team` 组队（6 成员全部创建成功）→ `create_task` 建单
  → `spawn_teammate` 动态召唤成员 → `update_task`/`assign` 指派
  → `send_message` 通知，全部经框架自己的 manager **真实执行**。
  实测任务落库为 `team_task_*.task-1 status=pending`（assignee 也正确落库），
  轨迹见 `runtime/coordination_*.json`。
- **运行层（未跑通的部分）**：成员侧的 `claim_task` / `member_complete_task`
  **一次都没发生**。已定位到具体位置（不是没试）：整个 run 里
  `[NativeHarness] round_id` 只为**主理**启动过，成员只有
  `invoke start → coordination starting`，**从未开启任何模型回合**；
  因此发给成员的定向消息在库里一直是 `is_read=0`，事件也无处落地。
  参考：R8 曾归因于「事件错过」，R9 用 `spawn_teammate` 绕开该时序后仍是 0，
  说明**更根本的问题是成员的 round 没启动**。**结论：成员协同闭环未验证。**
- **在线运行**：`run_online.py` 已就绪但**零成功运行记录**，不得声称已跑通多智能体协同。
  本轮另查明一个**环境级故障**：本机 `NO_PROXY` 含带方括号的 IPv6（`[::1]`），
  会让 `openai` 3.x 依赖的 `httpx2` 在构造客户端时报
  `InvalidURL: Invalid port: ':1]'` —— **任何** OpenAI 兼容端点都无法发请求，
  与 Key 无关。详见 `docs/08-运行层实测记录.md`。

> ⚠️ **复核轨迹时别用 `grep claim_task` 数事件次数** —— 工具名会出现在主理自己的
> 提示语里，实测 grep 得 10/9，真值是 0/0。用
> `python run_stub_online.py --verify runtime/coordination_<ts>.json`。

> 这条边界在「技术方案」正文中同样如实标注。
> 我们宁可把「主理侧已跑通、成员侧未跑通」写清楚，
> 也不虚报一次不存在的协同运行。

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

### 四步复现（不需要任何模型 Key）

> **最省事：一条命令跑完全部**（9 项，含 Skill 自证与清单一致性）
> ```bash
> python tools/run_all_checks.py
> ```

```bash
# 0. 零依赖验证：证明两段自检不需要 openJiuwen、也不需要 Key（修 E12）
python tests/verify_zero_dep.py
#    期望：6 项全 ✓，末行「结论：两段确定性自检不需要 openJiuwen、不需要 API Key 即可复现」

# 1. 装配正确性：逐成员解析到各自声明的 spec 与工具集（E1 防线）
python probe_build.py
#    期望：末行「结论：Agent Group 装配正确 —— 全部成员解析到各自的 spec 与工具集」
#          输出含「不同 spec 对象数：5 / 5」

# 2. 测试向量（31 + 9 组，含反例点名与装配防线）
python tests/test_citation_audit.py     # 期望：31 通过 / 0 失败
python tests/test_assembly.py           # 期望：9 通过 / 0 失败

# 3. 离线端到端：图谱定案由 → 检索 → 起草 → 两段自检 → 导出 .docx
python run_offline_demo.py
#    期望：STEP 1–6 全部执行完毕，退出码 0，
#          runtime/ 下生成新的 deliverable_*.docx 与 runlog_*.json
#
#    ⚠️ 注意（修 E8）：本演示**故意**在起草稿里埋了一个库外条号「第9999条」，
#       所以第一段自检的结论**本来就是 ok=false**（这正是要展示的能力）。
#       因此判据是「是否走完全部 6 步」，**不是**「自检通过」。
#       第二段自检（适用性）在 G12 修复后应报「全部引用均落在范围内」。
```

> **修 E8 说明**：原 README 写「期望：6 步全绿」，容易被误读为「自检应通过」。
> 实际 STEP 5 第一段必然 `ok=false`（埋雷被点名），脚本仍返回 0 —— 这是**设计意图**，
> 不是失败。现已在上面写清判据。

### 运行层实测（桩模型 + 真实 TeamAgent，**不需要 Key**）

```bash
# 4. 桩自检（不监听端口、不联网、零三方依赖）
python tools/stub_llm_server.py --selftest   # 期望：5 通过 / 0 失败

# 5. 驱动真实 TeamAgent（约 5 分钟），产出 runtime/coordination_*.json
python run_stub_online.py --timeout 340
#   诊断开关（R11）：--members N 只保留前 N 个成员；--dispatch-mode scheduled 换派发模式
#   python run_stub_online.py --members 1
#   python run_stub_online.py --dispatch-mode scheduled
#    期望：create_task ✅ / send_message ✅ / claim_task ❌ / member_complete_task ❌
#    👆 最后两项是**当前真实水平**，没有修饰。原因见 docs/08-运行层实测记录.md

# 6. 直查框架库，验证任务板/消息真的落库了
python tools/inspect_team_db.py
```

> **口径**（对外只用这一句）：**模型为本地确定性桩（stub），框架任务板与成员消息为真实流转。**
> `has_real_model` 为 `true` 仅表示注入了非占位符的桩 Key，**不表示**已接入真实模型。

### 一键验证（等同 CI 的「每次提交前全绿」）

```bash
./verify.ps1    # Windows
./verify.sh     # Linux / macOS
```

内部调 `tools/run_all_checks.py`（10 步，含**工作区干净闸门**）。
**exit 0 = 全绿；非 0 并指出是哪一项。** 本项目**未启用 GitHub Actions**，原因见 `提交包/README.md`。

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

`runtime/` 下**最新**的 `deliverable_*.docx`（**文件名随时间戳变化，请以实际生成的文件为准**）
的「四、引用自检」段：

> 识别到条文号引用 2 处（去重）
> 与「本次工具真实返回」法条对应：1/2
> 以下引用未在工具返回中找到对应条文（可能来自用户材料原文或模型笔误，请人工核实后再采用）：
> **「第9999条」**

`第9999条` 是**故意埋进起草稿的库外条号**，被代码级规则当场点名——不是模型自查。
文末附 **2 张 Word 原生表格**：第一段逐条判定 + 第二段适用性校验。

> **修 E7 说明**：原 README 此处硬编码了 `deliverable_20261013-232806.docx`
> 这个**并不存在于仓库中**的文件名（仓库里的是另一次运行的时间戳）。
> 取证文件名会随每次运行变化，因此改为引用「最新文件」并说明判据，
> 不再硬编码一个会过期的字符串。

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
├── 接手必读.md                    ★ 同伴与同伴的 AI 优先读（现状/差距/待办）
├── AI工作须知.md                  ★ 给 AI：布局/技术事实/硬性纪律/验证命令
├── 任务台账.md                    ★ 工单交换板（领活/交活/下指令）
├── README.md                      ← 本文件
├── LICENSE                        Apache-2.0（与 openJiuwen 生态一致）
├── requirements.txt
├── .gitignore  .gitattributes  .env.example  conftest.py
│
├── 提交包/                        ★ 官方六项清单归档
│   ├── README.md                  六项对位表 + 一页纸叙事 + 最短验证路径
│   ├── 01-作品名称.md
│   ├── 02-项目简介.md
│   ├── 03-应用场景说明.md
│   ├── 04-技术方案.md              架构 / 6 成员 / 组件两表 / 两段自检 / 运行层现状
│   ├── 05-DEMO演示视频.md          ⚠️ 待制作（现 7:13，超 2.4 倍）
│   └── 06-项目文档.md              项目文档索引 + 待补齐项
│
├── docs/                          ★ 评估、方案与实现说明
│   ├── 01-贴合度评估与整改建议.md   12 项整改清单（G1–G12）+ 17 天路线图
│   ├── 02-源码级复核补充.docx       源码级复核发现的上游问题
│   ├── 03-AgentGroup方案.md        框架设计 / 通信协议 / 接口定义 / 模型选型
│   ├── 04-AgentGroup实现说明.md
│   ├── 05-零Key复现路径.md         哪部分零依赖可复现、哪部分需要框架
│   ├── 06-进度与交接记录.md        逐项验收证据（证据流水，非接手入口）
│   ├── 07-JiuwenSwarm接入评估.md   JiuwenSwarm/SkillHub 评估与未验证项
│   └── 08-运行层实测记录.md        ★ 第八轮：跑通什么/没跑通什么 + 5 个坑 + 环境级故障
│
├── src/faron_agentgroup/          ★ Agent Group 实现
│   ├── __init__.py
│   ├── citation.py                引用解析 + 两段自检（逐条对齐 agent.ts）
│   ├── kg.py                      知识图谱（对齐 db.rs 种子与 kg.ts）
│   ├── tools_legal.py             法库 + 官方 12 个工具
│   ├── audit.py                   两段自检与图谱工具（Agent 可调用）
│   ├── config.py                  模型池 / 5 类任务 / 四角色提示词
│   └── group.py                   Agent Group 规格装配 + 门面
│
├── tests/                         ★ 40 组验证
│   ├── test_citation_audit.py     31 组测试向量（自动发现）
│   ├── test_assembly.py           9 组装配防线（E1 回归）
│   └── verify_zero_dep.py         零依赖验证（屏蔽全部框架 import）
├── probe_build.py                 最小构建探针（逐成员 spec 解析）
├── run_offline_demo.py            端到端演示（不需要模型）
├── run_online.py                  在线运行（需要真模型；**零成功记录**）
├── run_stub_online.py             运行层实测：桩模型 + 真实 TeamAgent（生成 coordination_*.json）
├── verify.ps1 / verify.sh         ★ 一键验证薄包装（exit 0 = 全绿；非 0 并指出哪项）
├── tools/
│   ├── stub_llm_server.py         本地确定性 OpenAI 桩（零三方依赖，支持 SSE）
│   ├── inspect_team_db.py         直查框架团队库（任务板/成员/消息的真实状态）
│   ├── reset_team_db.py           清空团队库数据（保留表结构；别直接删 team.db）
│   ├── apply_wake_probes.py       给框架打/撤唤醒链探针（只加日志；--apply/--revert 往返**逐字节一致**）
│   ├── gen_manifest.py            生成 资料/提交物清单.json
│   └── run_all_checks.py          全部验证（10 步，含工作区干净闸门）
├── runtime/                       产出：交付物 .docx + 取证日志 .json + coordination_*.json
│
├── skill/citation-audit/          ★ 零依赖 Skill 包（SkillHub 可分发）
│   ├── SKILL.md                   触发词 / 参数 / 返回 / 已知边界
│   └── scripts/
│       ├── audit_citations.py     自包含 CLI（零三方依赖）
│       └── verify_no_deps.py      零依赖自验证
│
├── 交付补丁/                       ★ Legal-Workspace 的 10 个提交（D9：无 BOM；含 ALL-IN-ONE 一步到位）
│   ├── 0001-fix-P0-6-P0-7-UI.patch
│   ├── 0002-test-EV7-evolution.ts-41-jsonBytes.patch
│   ├── 0003-feat-EV2.patch
│   ├── 0004-fix-R3-P1-2-P1-3-P1-4-vite-test-10s-JSX.patch
│   ├── 0005-feat-R4-P0-1-P0-2-1.patch
│   ├── 0006-feat-R4-P0-3-P0-4.patch
│   ├── 0007-refactor-R4-P0-5-Evolution.tsx-926-74.patch
│   ├── 0008-feat-R3-P1-6-auditPassFloor-minSamples-100.patch
│   ├── 0009-fix-R5-P0-1-P0-2-docs-12.patch
│   ├── 0010-feat-R6-P0-1-P0-2-P1-P2.patch
│   ├── ALL-IN-ONE.patch            ★ 10 提交 mbox，一步到位
│   ├── 应用说明.md                  ★ 基线 + 两种方式 + 每个提交在做什么
│   ├── 改动概览.txt
│   └── recipe.ts / recipe.test.ts / evolutionStore.ts / evolution.test.ts
│
│   └── 应用方式（两种，任选）：
│         一步到位：  git am 交付补丁/ALL-IN-ONE.patch
│         按序可诊断：for p in 交付补丁/0*.patch; do git am "$p" || break; done
│       ⚠️ 基线 = 远端 feature/赛事版 的 a9344c1；远端前进后需先 rebase 再重生成
│       ✅ 两种方式均已在干净 clone 上实测：9 提交全落盘 → 75 passed / 83 modules / 6-6
│
├── 资料/                          ★ 参赛材料（提交包整理版）
│   ├── README.md                  材料导航
│   ├── 版本清单.json               ★ 校验值单一来源（各文档引用此处）
│   ├── 大文件说明.md               两个超限大文件的体积、校验值与获取方式
│   ├── README-评委先读.md           建议最先读
│   ├── 01-演示视频-分镜与素材/       分镜 + 3套字幕 + 2套配音稿 + 品牌素材
│   ├── 02-产品介绍PPT/
│   ├── 03-项目计划书/
│   ├── 04-产品演示站/               demo.html（单文件零依赖，双击离线可开）
│   ├── 05-移动端与安装说明/
│   └── 06-用户调研/                 107 份问卷 + 结果 PDF
│
└── 源码/                          ★ 上游内部文档与仓库元信息
    ├── README.md                  文档导航 + 对齐依据说明
    ├── Legal-Workspace/           上游 README / CHANGELOG / package.json
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

> 数字由 `tests/test_citation_audit.py` 的自动发现结果回跑取得（纪律 **D10**：
> 任何数字类断言改完必须回跑取真值，不得沿用旧文）。
> 分组登记数与自动发现数在运行器里**互相断言**，不一致会直接红。

### `tests/test_citation_audit.py` —— 31 组

| 组 | 用例数 | 内容 |
|---|---|---|
| 一、token 抽取 | 5 | 中日文条号 / 日文 `の·之·ノ` 分条 / 美国法典 `§NN` 变体（**含 G11 字母款项修订**）/ 去重保序 / 边界 |
| 二、覆盖判定 | 4 | 归一化 / 前缀覆盖语义 / **E9 前缀收紧 9 组** / 候选单元生成 |
| 三、第一段自检 | 10 | 正向 / **反例点名** / 美国法典反例 / **G11 款项区分** / 款项独立判定 / 前缀用途保留 / 部分命中 / 确定性 / 零返回 / **E3 登记时序** |
| 四、第二段自检 | 4 | `sameLaw` / 在范围与超范围 / 未命中案由跳过 / **E11 两侧断言** |
| 五、知识图谱 | 6 | 种子案由 / 案由匹配 / 骨架结构 / **法条节点无条号约束** / 候选边确认 / 候选边拒绝 |
| 六、端到端 | 1 | 图谱 → 检索 → 起草 → 两段自检 |
| 七、可复现性 | 1 | **E5** 跨进程 `Article.id` 稳定（三种 hash seed） |
| **小计** | **31** | |

### `tests/test_assembly.py` —— 9 组（E1 回归防线）

| 组 | 用例数 | 内容 |
|---|---|---|
| 装配正确性 | 9 | `agents` 字典完备性 / 逐成员 spec 解析 / 无共享 spec 对象 / prompt 隔离 / 动态兜底 / HITL 一致性 / 保留名 / JSON 往返 / 自动发现自检 |
| **小计** | **9** | |

### `tests/verify_zero_dep.py` —— 6 项

| 项 | 内容 |
|---|---|
| 零依赖验证 | 按文件路径加载两个纯函数模块 / 图谱可用 / 第一段自检 / 第二段自检 / 报告渲染 / **断言全程零框架 import** |

### 合计

| 套件 | 用例数 |
|---|---|
| `test_citation_audit.py` | 31 |
| `test_assembly.py` | 9 |
| `verify_zero_dep.py`（检查项） | 6 |
| **合计** | **46** |

> **另有一侧**：`Legal-Workspace`（TypeScript）有 **75 组**（`vitest`），
> 见该仓库 `tests/evolution.test.ts`（41）与 `tests/recipe.test.ts`（34）。
> 两侧合计 **121 组**。

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
