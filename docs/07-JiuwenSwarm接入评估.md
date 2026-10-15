# P1-3 · JiuwenSwarm / SkillHub 接入评估

> 赛事页面注明「**推荐使用 openJiuwen 社区的 AgentOS 平台：JiuwenSwarm**」。
> 本文是对「要不要接、怎么接、接到什么程度」的评估结论与已落地成果。
>
> **一句话结论**：JiuwenSwarm 本体（多智能体协同框架）与法元的定位重叠，
> **不宜替换**；但它生态里的 **SkillHub（Agent 资产托管与分发）** 是一个
> 真实、低成本、有价值的接入点 —— **已落地一个零依赖 Skill 包**。

---

## 一、先把生态看清楚（2026-10-15 实查）

来源：[openJiuwen 组织主页](https://gitcode.com/openJiuwen) 的官方 README。
openJiuwen 采用分层架构，公开仓库如下：

| 层 | 仓库 | 定位 |
|---|---|---|
| **Deep Agents** | [`jiuwenswarm`](https://gitcode.com/openJiuwen/jiuwenswarm) | 多智能体协同框架与**官方旗舰应用**，支持复杂任务协作与 Skill 自演进 |
| | [`jiuwensymbiosis`](https://gitcode.com/openJiuwen/jiuwensymbiosis) | 面向具身智能的 Agent 框架 |
| | [`deepsearch`](https://gitcode.com/openJiuwen/deepsearch) | 知识增强深度检索，片段级引用与溯源推理 |
| **SkillHub** | [`skillhub`](https://gitcode.com/openJiuwen/skillhub) | **Agent 资产托管与分发**：Skill、SwarmSkill、插件、连接器、专家、专家团 |
| **Agent Studio** | [`agent-studio`](https://gitcode.com/openJiuwen/agent-studio) | 零码/低码可视化开发与工作流编排 |
| **Agent Framework** | [`agent-core`](https://gitcode.com/openJiuwen/agent-core) | Python Agent SDK（**本项目当前使用的就是它**） |
| | `agent-core-java` / `agent-memory` / `agent-protocol` | Java SDK / 长期记忆 / MCP+A2A 协议 SDK |
| **Distributed Runtime** | `agent-runtime` / `agent-runtime-java` / `agent-dx` | Agent 服务化运行与分布式执行 |
| | `agent-infer` | 基于 vLLM 的 agentic 推理框架 |
| **System Service** | `agent-gateway`（Opening Soon） | Channel、消息、定时任务、心跳 |

> **关键事实**：**JiuwenSwarm 不在 `agent-core` 之内，而是建立在它之上的旗舰应用**。
> 也就是说 —— 法元与 JiuwenSwarm 是**同一层的两个应用**，不是「框架与插件」的关系。
> 这决定了接入策略。

---

## 二、评估：JiuwenSwarm 本体该不该接

### 结论：**不替换，不复刻**

| 维度 | JiuwenSwarm | 法元 | 判断 |
|---|---|---|---|
| 形态 | 把 LLM 能力延伸到**日常通讯应用** | 本机桌面应用（Tauri） | **不同渠道，不冲突** |
| 协同 | 多智能体协同框架 | openJiuwen `agent_teams` 原生 AgentGroup | **同层**，替换无收益 |
| 差异化能力 | Skill 自演进 | **两段确定性引用自检** + 本地 15 万条法库 | 法元的价值在后者 |
| 数据边界 | 通讯应用链路 | **数据不出本机**（律所合规准入项） | 法元的定位**拒绝**走通讯链路 |

**不接的理由（三条）**：

1. **同层替换无收益**。把 6 成员编排从 `agent_teams` 换到 jiuwenswarm 的协同框架，
   是换一个同类实现，不产生新能力，只消耗 17 天里最宝贵的工时。
2. **形态冲突**。JiuwenSwarm 的核心价值是「通过你日常使用的各类通讯应用把能力延伸到指尖」；
   而法元的卖点之一恰好是**涉密文书不出内网**。把办案链路接到通讯应用上，
   与已有用户验证（107 份问卷）里的合规诉求方向相反。
3. **答辩风险**。若为了「用了官方推荐平台」而仓促替换编排层，
   会出现「装配层没验证完、运行层更没跑通」的双重未完成状态 —— 比不接更糟。

### 但**必须**在技术方案里说清楚

不接不等于不提。已在本目录 `04-技术方案.md` 中如实说明：
使用 `agent-core`（`openjiuwen.agent_teams`），并给出与 JiuwenSwarm 的关系判断，
而不是回避赛事页面的推荐。

---

## 三、接入落点：把确定性自检做成 Skill（**已落地**）

### 为什么是 Skill 而不是别的

SkillHub 的官方描述是「openJiuwen 生态中 **Agent 资产（Skill、SwarmSkill、插件、连接器、
专家、专家团）的托管与分发开源实现**，供团队在自有环境中部署使用」。

而法元的「两段确定性引用自检」恰好具备一个好 Skill 的全部特征：

| Skill 应有的特征 | 法元自检 |
|---|---|
| 单一职责、边界清晰 | ✅ 「判引用是否成立」，不越界判实体 |
| 可独立调用 | ✅ 纯函数，输入 (正文, 工具返回集合) → 输出判定 |
| 有明确触发场景 | ✅ 校验 AI 生成法律文书的法条引用 |
| **不绑定宿主实现** | ✅ **零三方依赖**，只用 Python 标准库 |
| 可被别的 Agent 复用 | ✅ 任何需要「引用可信」的 Agent 都能用 |

**最关键的是最后一条**：法元自检**不依赖大模型、不依赖 openJiuwen**。
这意味着它可以被**任意** Agent 当作一个可信度校验层复用 ——
这正是「资产」而非「应用内功能」的定义。

### 已交付的 Skill 包

```
skill/citation-audit/
├── SKILL.md                      Skill 描述（触发词、参数、返回、边界声明、已知限制）
└── scripts/
    ├── audit_citations.py        自包含 CLI（零三方依赖，可直接运行）
    └── verify_no_deps.py         零依赖验证（拦截非标准库 import 后重跑）
```

### 实测证据

```bash
# ① 演示：故意埋一个库外条号，看它被当场点名
python skill/citation-audit/scripts/audit_citations.py --demo
```
```
正文引用 3 处（去重），命中 2 处
- 以下引用未在工具返回中找到对应条文（…请人工核实后再采用）：
  「第9999条」
结论：1 处引用**未获凭证**，请人工核实或删除后再采用：
  · 第9999条
```
> 退出码 **1** —— 可直接在 CI 里当闸门用。

```bash
# ② 零依赖验证：屏蔽全部非标准库 import 后重跑
python skill/citation-audit/scripts/verify_no_deps.py
```
```
[1] citation.py: ['__future__', 'dataclasses', 're', 'typing'] → ✅ 全在标准库内
    kg.py:       ['__future__', 'dataclasses', 're', 'typing'] → ✅ 全在标准库内
[2] ✅ CLI 正常运行（exit=1）
       total=3 covered=2 ok=False
       unmatched=['第9999条']
       ✅ 库外条号「第9999条」被正确点名
结论：本 Skill **不需要任何三方依赖**（含 openJiuwen）即可运行。
```

**补一句**：这个 Skill 事实上还可以被**通用 Agent 工具链**直接调用 ——
`SKILL.md` 的格式与 Claude Skills / DSH Skills 的约定一致
（`SKILL.md` + `scripts/`），因此它同时是一份可移植的资产，不锁定在某一个平台。

---

## 四、如实标注：**未验证**的部分

| 项 | 状态 | 说明 |
|---|---|---|
| Skill 包本身可运行 | ✅ **已实测** | 上面的命令与输出都是真跑出来的 |
| 零三方依赖 | ✅ **已实测** | `verify_no_deps.py` 用 import 拦截 + 断言 |
| **SkillHub 上传 / 注册流程** | ❌ **未验证** | 未在真实 SkillHub 实例上注册过。需要：一个可访问的 SkillHub 部署（或社区实例）+ 账号。**上传格式是否与 `SKILL.md` 约定一致，未经核对** |
| **被 JiuwenSwarm 作为 Skill 装载并调用** | ❌ **未验证** | 未在 jiuwenswarm 里装载过。需要：jiuwenswarm 可运行环境 + 模型 Key |
| jiuwenswarm 的 Skill 装载规范 | ❌ **未查阅** | 本次未取到 jiuwenswarm 的 Skill 接口文档，故未按其规范裁剪 |

**因此本文不声称「已完成 JiuwenSwarm 接入」。**
准确表述是：**已完成一个可被 SkillHub 分发的 Skill 资产，并实测其零依赖可运行；
上传与装载环节未验证。**

---

## 五、下一步（若要把未验证部分补上）

| # | 动作 | 需要什么 | 预估 |
|---|---|---|---|
| 1 | 取 jiuwenswarm 的 Skill 装载文档，按其规范补 `skill.yaml` / manifest | 能访问 `gitcode.com/openJiuwen/jiuwenswarm`（本次未取到相关章节） | 1 小时 |
| 2 | 在 SkillHub 实例上注册该 Skill | SkillHub 部署 + 账号 | 2 小时 |
| 3 | 在 jiuwenswarm 里装载并调用一次 | jiuwenswarm 环境 + 模型 Key | 半天 |
| 4 | 把 Skill 的返回值接入 jiuwenswarm 的编排（作为质检步骤） | 同 3 | — |

> 若时间不足，**只做第 1 步**（按其规范补 manifest）即可让「可分发」这一步在形式上也成立，
> 成本最低、收益最直接。

---

## 六、给答辩用的一段话

> 官方推荐 JiuwenSwarm。我们评估后**没有**替换编排层，理由有三：
> 一是 JiuwenSwarm 与法元同在 `agent-core` 之上的应用层，替换不产生新能力；
> 二是 JiuwenSwarm 的渠道是通讯应用，而法元的合规卖点恰是涉密文书不出内网，方向相反；
> 三是仓促替换会让装配层与运行层同时处于未验证状态。
>
> 我们把接入点选在 **SkillHub** —— 法元的「两段确定性引用自检」是一个
> **零三方依赖**（只用 Python 标准库）的可复用资产，任何需要「引用可信」的 Agent 都能调用。
> 该 Skill 包已交付并**实测**零依赖可运行、库外条号能被当场点名；
> 上传 SkillHub 与在 jiuwenswarm 中装载这两个环节**我们尚未验证，如实标注**。
