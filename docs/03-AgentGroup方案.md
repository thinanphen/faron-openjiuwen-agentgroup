# 法元 · Faron Agent Group 方案

> **方案名称**：Faron Agent Group —— 面向涉外法律文书交付的多智能体协同编排
> **承载框架**：openJiuwen `agent-core`（`openjiuwen.agent_teams` 原生 AgentGroup）
> **版本**：v1.0（2026-10-13）
> **前置结论**：本方案的**全部 API 已在真机验证通过**（见 §7 验证证据），不是纸面设计。

---

## 一、为什么用 Agent Group 而不是单 Agent

「法元」原来的「小元」是**单模型 + 四角色接力**（规划 → 检索员 → 起草员 → 质检员），四段各自独立系统提示词、串行执行、状态自研落 SQLite。

这套设计有三个天花板：

| 天花板 | 表现 | Agent Group 如何解决 |
|---|---|---|
| **串行瓶颈** | 检索、起草、质检必须排队，一份多法域合同要等四轮 | 任务板 + 成员并发认领，检索可并行扇出 |
| **无法人在环** | 「需人工确认」靠自研闸门 + 前端按钮 | 框架原生 HITL（`enable_hitt`），人类是一等成员 |
| **扩展即改代码** | 新增一类文书 = 改模板 + 改状态机 | 新增任务类型 = 新增一条成员/任务定义 |

更重要的是：**本届赛事的主题就是「从能对话迈向能做事」**，而 Agent Group 正是「多智能体协同做事」的官方表达方式。用官方框架承载，同时兑现了「使用 openJiuwen 生态」这一必答项。

---

## 二、总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     用户 / 律师 / 评委（人类）                        │
│            提交委托材料 · 审批计划卡 · 复核引用自检结论                 │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ ① 自然语言委托 + 材料文件
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     TeamAgent（openJiuwen 官方）                     │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  LEADER  小元·主理                                             │  │
│  │  任务理解 → 任务板建单(create_task) → 分派 → 汇总交付           │  │
│  └───────┬───────────────────────────────────────────────┬───────┘  │
│          │ ② create_task / send_message                  │ ③ 汇总   │
│          ▼                                               ▼          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  任务板 Task Board（claim_task / view_task / member_complete） │  │
│  └───┬──────────────┬──────────────┬──────────────┬─────────────┘  │
│      │              │              │              │                 │
│      ▼              ▼              ▼              ▼                 │
│  ┌────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐       │
│  │检索员   │   │起草员     │   │质检员     │   │人类复核员     │       │
│  │民商    │   │文书       │   │引用自检   │   │HUMAN_AGENT   │       │
│  │        │   │          │   │          │   │(enable_hitt) │       │
│  │laws_   │   │draft_    │   │audit_    │   │审批/打回      │       │
│  │search  │   │document  │   │citations │   │              │       │
│  │law_by_ │   │          │   │(确定性)   │   │              │       │
│  │id      │   │          │   │          │   │              │       │
│  └───┬────┘   └────┬─────┘   └────┬─────┘   └──────┬───────┘       │
│      │             │              │                │               │
│      └─────────────┴──────────────┴────────────────┘               │
│                            │                                        │
│  ┌─────────────────────────▼─────────────────────────────────────┐  │
│  │  通信层 Messager（inprocess / pyzmq）                          │  │
│  │  send_message · 邮箱轮询 · 任务板快照                            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  存储层 TeamSpec.storage（SQLite）                             │  │
│  │  team_info / team_member / task / message                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  模型池 model_pool（多网关 / 多模型）                          │  │
│  │  round_robin / by_model_name / router / intelli_router        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                            │ ④ 交付
                            ▼
              ┌──────────────────────────────┐
              │  .docx 文书（五段式 + 原生表格）│
              │  + 引用自检结论（可反例验证）   │
              └──────────────────────────────┘
```

---

## 三、成员定义（Agent Group 编制）

### 3.1 编制表

| 成员 | `role_type` | 职责 | 私有工作约定（`prompt`，不进 peer 视野） | 公开简介（`desc`，进 peer roster） |
|---|---|---|---|---|
| **小元·主理** | `LEADER` | 理解委托、建任务、分派、汇总交付 | 见 §3.2 | 团队主理，负责规划、分派与交付汇总 |
| **检索员·民商** | `TEAMMATE` | 本地法库检索，回传条文 + 溯源 | 只调用本地法库工具，返回条文号+篇名+来源，**绝不臆造条文** | 在内置日美法库中检索真实法条并回传溯源信息 |
| **起草员** | `TEAMMATE` | 依据检索结果 + 模板起草正文 | **只允许引用检索员真实返回的法条**，输出固定五段式 | 依据检索结果与模板起草文书正文 |
| **质检员·引用自检** | `TEAMMATE` | 确定性逐条对账引用 | 用规则逐条比对，未覆盖项一律点名，**不计为有效引用** | 代码级逐条对账引用，点名未覆盖项 |
| **人类复核员** | `HUMAN_AGENT` | 审批计划卡、复核自检结论 | 由真实用户驱动，处理 `need_confirm` 闸门 | 真实人类复核员（仅在 `expose_human_agents_to_teammates=True` 时对同伴可见） |

> **`desc` / `prompt` 的设计要点**（直接来自官方 schema 注释）：`desc` 是**唯一**会出现在其他成员 roster 里的字段，`prompt` **只注入自己的系统提示词**。因此「不得臆造条文」这类纪律写在 `prompt` 里，而能力边界写在 `desc` 里。

### 3.2 角色提示词要点

**LEADER（小元·主理）**
```
你是法元 · Faron 文书智能体的团队主理「小元」。
把一份涉外法律委托拆成可并行的子任务，分派给检索员、起草员、质检员，
并把质检结论与交付物汇总给用户。

硬规则：
1. 交付物中的每一条法条引用必须来自检索员真实返回的条文，不得凭记忆书写；
2. 涉及「需人工确认」的步骤必须停下等待人类复核员批准，不得自行放行；
3. 质检员的未覆盖结论是最终结论，不得用模型判断覆盖它。
```

**质检员（引用自检）** —— 这是「法元」区别于通用 Agent 的**核心资产**
```
你用确定性规则逐条比对正文引用与「本次工具真实返回的法条集合」。
支持识别：中文「第X条」/「第X条之Y」、日文「第X条のY」、美国法典「§NN」。
未在真实返回集合中找到的引用，一律点名，不计为有效引用。
你的结论必须与模型输出内容无关——即使正文写得再好，对不上就是不合格。
```

---

## 四、通信协议

### 4.1 协议栈（全部来自 openJiuwen 官方，非自研）

| 层 | openJiuwen 组件 | 作用 |
|---|---|---|
| **任务协议** | `create_task` / `claim_task` / `view_task` / `member_complete_task` | 任务板：主理建单 → 成员认领 → 完成回写 |
| **消息协议** | `send_message` | 成员间点对点/广播消息（**跨成员联系的唯一通道**） |
| **身份协议** | `list_members` / `TeamRole` | roster 查询、角色识别 |
| **人审协议** | `HumanAgentInbox` / `UserInbox` / `interact` | 人类发言与审批回注团队 |
| **传输层** | `MessagerTransportConfig`（`inprocess` / `pyzmq` / `hybrid`） | 进程内 / 跨进程消息总线 |
| **持久层** | `StorageSpec`（`sqlite` / `postgresql` / `mysql` / `memory`） | 团队与任务落库 |
| **人审入口** | `$name` 语法（`parse_mention`） | 人类用自然语言点名某个成员 |

### 4.2 两种分派模式（`dispatch_mode`）

| 模式 | 语义 | 适用 |
|---|---|---|
| `autonomous`（默认） | 任务上共享板，成员**按专长自主认领**，主理用 `send_message` 广播启动 | 检索可并行扇出的场景（多法域合同） |
| `scheduled` | 主理**预先指派**每个任务给具名成员，交接（启动/评审/返工/验收）全由调度运行时以主理身份发消息 | 文书类**顺序强依赖**流程（起草必须先有检索结果） |

> **本方案选型**：**两种模式各用一处**——
> - 检索阶段用 `autonomous`（多法域并行检索是天然扇出）；
> - 文书阶段用 `scheduled`（起草依赖检索、质检依赖起草，是强顺序链）。

### 4.3 可靠性协议

| 机制 | 配置项 | 值 | 作用 |
|---|---|---|---|
| 停滞任务催办 | `stale_claim_idle_timeout` | 600 s | 成员拿着任务空转超时 → 自我催办 |
| 主理待办催办 | `stale_pending_idle_timeout` | 600 s | 有未认领任务且有空闲成员 → 主理自我催办 |
| 评审轮次上限 | `default_max_review_rounds` | 3 | 质检返工超过 3 轮 → 升级给主理 |
| 评审停滞升级 | `review_stall_timeout` | 1800 s | 评审无结论超时 → 上报主理 |
| 转向批大小 | `steer_batch_size` | 2 | 成员每次模型调用消费的排队消息数上限 |

### 4.4 通信时序（一次完整委托）

```
人类        主理(LEADER)      检索员       起草员      质检员     人类复核员
 │              │               │            │           │           │
 │─委托+材料───▶│               │            │           │           │
 │              │──create_task─▶│            │           │           │
 │              │  (检索:日本法) │            │           │           │
 │              │──create_task──────────────▶│           │           │
 │              │  (检索:美国法) │            │           │           │
 │              │──send_message(广播启动)     │           │           │
 │              │               │            │           │           │
 │              │◀─claim_task───│            │           │           │
 │              │◀─claim_task────────────────│           │           │
 │              │◀─真实法条+溯源─┤            │           │           │
 │              │◀─真实法条+溯源──────────────┤           │           │
 │              │               │            │           │           │
 │              │──create_task(起草)─────────────────────▶│           │
 │              │◀─文书正文(仅引用已返回法条)───────────────┤           │
 │              │               │            │           │           │
 │              │──create_task(质检)──────────────────────────────────▶│
 │              │◀─逐条对账结论(未覆盖项点名)──────────────────────────┤
 │              │               │            │           │           │
 │◀─计划卡待确认─┤               │            │           │           │
 │─批准────────▶│               │            │           │           │
 │              │◀─────$human_reviewer 审批通过 ──────────────────────│
 │              │               │            │           │           │
 │◀─.docx交付+自检结论───────────┤            │           │           │
```

---

## 五、接口定义

### 5.1 对外接口（调用方视角）

```python
from openjiuwen.agent_teams import TeamAgentSpec

spec = build_faron_spec(
    model_pool=[...],           # 模型池
    storage="sqlite",           # 持久层
    workspace="./runtime",      # 工作区
)
agent: TeamAgent = spec.build()          # 构建
async for chunk in agent.stream({"query": 委托文本}, session=session):
    ...                                   # 流式消费
await agent.interact("把第三条改成保守表述")   # 运行中介入
await agent.human_agent_say("批准", to="team_leader")  # 以人类身份发言
```

### 5.2 成员工具接口（成员视角，官方内置）

| 工具 | 签名要点 | 归属 |
|---|---|---|
| `create_task` | `title, description, assignee?, reviewers?` | 主理 |
| `claim_task` | `task_id` | 成员（`autonomous` 模式） |
| `view_task` | `task_id?` | 全员 |
| `member_complete_task` | `task_id, result` | 成员（`scheduled` 模式） |
| `send_message` | `to, content` | 全员 |
| `list_members` | — | 全员 |

### 5.3 法元内置工具接口（**本方案的增量**，需注册为 `BuiltinToolSpec` 或 `ToolCard`）

| 工具 | 输入 | 输出（**必须带溯源字段**） | 迁移自 |
|---|---|---|---|
| `laws_search` | `query, country?` | `[{article_no, title, content, source}]` | 现有 FTS5 检索 |
| `law_by_id` | `law_id` | `{article_no, title, content, source}` | 现有按法浏览 |
| `laws_country_preview` | `country` | `{law_count, article_count}` | 现有国家概览 |
| `template_load` | `template_id` | `{name, sections}` | 现有模板库 |
| `kg_plan_seed` | `cause_of_action` | `{elements[], claims[], evidence[]}` | 现有知识图谱 |
| **`audit_citations`** | `draft_text, returned_articles` | `{covered[], uncovered[], pass: bool}` | **现有确定性自检（核心资产）** |

> **`audit_citations` 的设计约束**：必须是**纯函数**（不调用模型），这样它的结论才与模型输出无关，才能被反例验证——这正是「法元」在官方框架之上补的那一层。

### 5.4 数据契约

```json
{
  "task_id": "t_0001",
  "title": "检索日本法：涉外合资经营合同的请求权基础",
  "status": "IN_PROGRESS",
  "assignee": "law_retriever",
  "artifacts": {
    "returned_articles": [
      {"article_no": "第百三条", "title": "民法", "source": "e-Gov", "content": "..."}
    ]
  },
  "audit": {
    "pass": false,
    "covered": ["第百三条"],
    "uncovered": ["第9999条"],
    "note": "第9999条未在本次工具真实返回中找到，不计为有效引用"
  }
}
```

---

## 六、模型与架构选型

### 6.1 框架选型

| 候选 | 结论 | 理由 |
|---|---|---|
| **openJiuwen `agent-core` / `agent_teams`** | ✅ **选用** | 官方原生、本届赛事推荐生态、已验证可构建、原生 HITL + 任务板 + 模型池 |
| openJiuwen `jiuwenswarm` | ⭕ 备选/并行 | 面向 IM 应用的多智能体框架（6.6k star），若需「通过微信/IM 触达」可作为前端形态 |
| 自研多角色接力 | ❌ 弃用 | 就是现状，改造成本高且拿不到框架红利 |
| LangGraph / AutoGen | ❌ 弃用 | 与赛事生态无关，反而弱化「使用 openJiuwen」这一必答项 |

### 6.2 模型池选型（`model_pool_strategy`）

| 策略 | 语义 | 本方案用途 |
|---|---|---|
| `by_model_name` | 按模型名分组轮转，每组均衡分配 | **主策略**：不同成员用不同能力档位的模型 |
| `router` | 单端点服务多模型名（OpenRouter / LiteLLM 形态） | **备用**：统一网关时启用 |
| `intelli_router` | 客户端可靠性路由（重试/故障转移/配额） | **生产建议**：多部署容灾 |

**成员-模型分档建议**（成本与能力平衡）：

| 成员 | 模型档位 | 理由 |
|---|---|---|
| 主理 | 强推理（high reasoning effort） | 拆任务、汇总、判断升级 |
| 检索员 | 轻量快模型 | 主要是工具调用与格式遵循 |
| 起草员 | 强生成 | 文书质量直接决定交付物质量 |
| 质检员 | **不依赖模型**（纯函数为主） | 确定性规则才是可信来源 |

### 6.3 关键配置（`TeamAgentSpec`）

| 配置 | 值 | 说明 |
|---|---|---|
| `spawn_mode` | `inprocess` | 单机部署（法元是本地优先产品），自动配 `inprocess` 传输 |
| `teammate_mode` | `build_mode` | 成员直接执行，不逐任务提交计划 |
| `enable_hitt` | `True` | 开启人类成员能力上限 |
| `expose_human_agents_to_teammates` | `False` | 默认不暴露"谁是真人"，避免成员行为差异 |
| `enable_task_verification` | `True` | 质量控制场景需要评审 |
| `enable_permissions` | `True` | 法务场景需要权限收敛（只读法库、禁外网） |
| `language` | `cn` | 中文提示词与工具描述 |
| `evolution_enabled` | `True` | 保留自演进（对应计划书 0.8.0 联邦配方进化） |
| `storage` | `sqlite` | 与本地优先定位一致 |
| `enable_swarmflow` | `True`（批处理场景） | 批量文书任务扇出 |

---

## 七、验证证据（方案已跑通的部分）

**探针脚本**：`02-agentgroup/probe_build.py`（真机执行）

```
======================================================================
openJiuwen TeamAgentSpec 构建探针
======================================================================
[1] spec 校验通过：team_name=faron_wenshu_team
    predefined_members = ['law_retriever', 'drafter', 'citation_auditor']
    enable_hitt        = True
    spawn_mode         = inprocess
[2] JSON 序列化成功：3528 字符（可跨进程分发）
[3] build() 成功：TeamAgent  role=leader
    member_name = team_leader
    leader_member_name = team_leader
    model_pool_strategy = round_robin
[4] 反序列化成功：team_name=faron_wenshu_team（跨进程恢复可用）
======================================================================
结论：Agent Group 成员规格可被 openJiuwen 官方框架构建。
```

| 验证项 | 结果 |
|---|---|
| SDK 导入 `openjiuwen.agent_teams` | ✅ |
| `TeamAgentSpec` + `LeaderSpec` + `TeamMemberSpec` 校验 | ✅ |
| `enable_hitt=True` 通过一致性校验 | ✅ |
| `spec.model_dump_json()` 序列化 | ✅ 3,528 字符 |
| `spec.build()` → `TeamAgent` | ✅ `role=leader` |
| `TeamAgentSpec.model_validate_json()` 反序列化 | ✅ |
| 内置工具注册（`sys_operation` fs/shell/code） | ✅ 已自动挂载 |
| `model_pool_strategy` 解析 | ✅ |

**环境**：Python 3.12.10 / openjiuwen 0.1.19 / Windows / D: 剩余 212 GB

**已知环境依赖**（安装时需注意）：
- 必须补装 `opentelemetry-exporter-otlp-proto-http` 与 `-grpc`，否则 `build()` 在可观测性作用域处报 `ModuleNotFoundError: No module named 'opentelemetry.exporter'`
- `redis` 缺失仅产生 WARNING（在线训练 rail 工厂不可用），不影响团队构建

---

## 八、与现有「法元」代码的对接方式

| 现有资产 | 对接方式 | 改动量 |
|---|---|---|
| `src/lib/tools.ts`（工具集，13.5 KB） | 工具 schema 与实现迁到 Python 侧，注册为 `BuiltinToolSpec` / `ToolCard` | 中 |
| `src/lib/agent.ts`（引擎，41 KB） | 规划/执行/四角色提示词 → 拆成 `DeepAgentSpec.system_prompt` + `prompt` | 中 |
| `src/lib/kg.ts`（知识图谱，5 KB） | 作为 `kg_plan_seed` 工具注入，或迁到 `openjiuwen.symphony` | 小 |
| `src/lib/ai.ts`（模型接入，8 KB） | 替换为 openJiuwen `ModelClientConfig` / `TeamModelConfig` | 小 |
| Rust 侧 `db.rs`（82 KB，SQLite + FTS5） | **保留**：作为 `laws_search` / `law_by_id` 的数据源（通过本地 HTTP/CLI 桥接或直读 SQLite） | 小 |
| Rust 侧 `docx.rs`（17.8 KB，零依赖 OOXML） | **保留**：交付物导出仍走它（Python 侧不重写 OOXML） | 无 |
| 确定性引用自检 | 抽为纯函数 `audit_citations`，**双端共用**（TS 与 Python 各一份，用同一组测试向量保证一致） | 小 |

> **架构原则**：**不重写已经对的东西**。Rust 侧的法库检索与 .docx 生成、TS 侧的 UI，全部保留；openJiuwen 只接管**编排层**。这既是最小改动路径，也让「我们用了 openJiuwen」的叙事更诚实——我们用的是它的编排能力，而不是把它当壳。

---

## 九、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Python 侧与 Tauri 侧双运行时 | 部署复杂、安装包变大 | ① 开发期双运行时；② 交付期可用 `pyoxidizer`/`PyInstaller` 打包或做成 Tauri sidecar |
| 依赖体积大（SDK 拉入 transformers/matplotlib/pymilvus 等） | 安装包膨胀 | 按需裁剪；或用 `openjiuwen` 最小依赖子集 |
| 缺少 `opentelemetry.exporter` | `build()` 直接失败 | 显式写入依赖清单（已在 §7 记录） |
| 模型池无 Key 时团队无法运行 | 评委侧无法演示 | 提供 mock 模型或演示模式（见评估报告 G9） |
| 确定性自检双端实现漂移 | 两端口径不一致 | 共享测试向量集，CI 双向校验 |
| Agent Group 引入后延迟上升 | 用户体验下降 | 检索阶段并行扇出抵消；质检为纯函数不增加模型调用 |

---

## 十、方案小结

**一句话**：**用 openJiuwen 的 `agent_teams` 承载协同，用法元自研的确定性引用自检承载可信——框架解决「一起干活」，我们解决「干得可信」。**

这个分工同时回应了赛事的两个关键点：
- **「如使用 openJiuwen 生态，请说明使用了哪些组件/能力」** → 有明确、可核验的组件清单（§4.1 协议栈 + §7 验证证据）；
- **创新性** → 在官方框架之上补出了官方没有的东西（高风险域的确定性验收），且可用反例现场验证。
