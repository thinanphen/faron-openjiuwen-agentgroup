# AI 工作须知（接手第一站）

> **给谁**：任何被叫来接手 `faron-openjiuwen-agentgroup` 这个仓库的 AI 助手。
> **目的**：读完这一份，你就具备了在此仓库安全、正确地动手的全部前提。
> **配套**：[`接手必读.md`](接手必读.md) 是给人看的现状与待办；
> 本文是给 AI 看的**布局、事实、纪律与陷阱**。
> **最后更新**：2026-10-15（对应远端 HEAD `0425763` + 本轮交接文档提交）

---

## 〇、你可以立刻做的三件事

```bash
git clone https://github.com/thinanphen/faron-openjiuwen-agentgroup.git
cd faron-openjiuwen-agentgroup

python tests/verify_zero_dep.py          # 零依赖：不需要 Key、不需要框架
pip install -r requirements.txt          # 之后才能跑下面这些
python tests/test_citation_audit.py      # 31 组
python tests/test_assembly.py            # 9 组
python probe_build.py
python run_offline_demo.py
```

**在动手改任何东西之前**，先跑一遍上面全部命令，确认基线是绿的。
**如果你拿到的结果与本文描述不符，先报告差异，不要开始改。**

---

## 一、这个仓库是什么

**它不是一个产品，是产品「法元 Faron」的「可信层」与「openJiuwen 承载层」的实现 + 参赛材料归档。**

```
┌─────────────────────────────────────────────────────┐
│ 法元 Faron（真实产品，在另一个仓库）                    │
│ github.com/lin612320/Legal-Workspace @ feature/赛事版 │
│ Windows 桌面端：Tauri 2 + React + Rust + SQLite       │
└──────────────────────┬──────────────────────────────┘
                       │ 本仓库承载其中两块：
                       ▼
┌─────────────────────────────────────────────────────┐
│ ① 编排层：openJiuwen `agent_teams` 原生 AgentGroup     │
│    6 成员 / 12 工具（src/faron_agentgroup/）           │
│ ② 可信层：两段确定性引用自检（不调用模型）               │
│    这是本产品区别于通用 Agent 的核心                    │
└─────────────────────────────────────────────────────┘
```

**对外唯一叙事主线**（不得改）：

> openJiuwen 的 AgentGroup 解决「一起干活」；法元补上「干得可信」。

---

## 二、仓库布局（105 文件 / 45.2 MB）

| 路径 | 内容 | 能改吗 |
|---|---|---|
| `src/faron_agentgroup/` | **实现**（7 模块，约 97 KB） | ✅ 可改 |
| `tests/` | 40 组验证（3 文件） | ✅ 可改 |
| `probe_build.py` / `run_offline_demo.py` / `run_online.py` | 探针与演示 | ✅ 可改 |
| `skill/citation-audit/` | 零依赖 Skill 包 | ✅ 可改 |
| `docs/` | 方案、实现说明、评估、交接记录（7 文件） | ⚠️ **`docs/01` 是审计记录，历史结论不得抹** |
| `提交包/` | 官方六项清单归档（7 文件） | ✅ 可改 |
| `资料/` | 参赛材料（PPT 38.79 MB、计划书、演示站、分镜素材、用户调研） | ⚠️ 见下方纪律 |
| `源码/` | 上游 `Legal-Workspace` 的**文档快照**（24 文件，非代码） | ⚠️ 见下方纪律 |
| `runtime/` | **产出**：`.docx` + `runlog.json`（取证物） | ✅ 会随运行变化 |
| `交付补丁/` | Legal-Workspace 三个提交的补丁 | ⚠️ 由导出流程生成 |
| `_hold/` | 本机暂存（已 gitignore 内容） | ❌ 别管 |

### `src/faron_agentgroup/` 各模块职责

| 模块 | 大小 | 职责 |
|---|---|---|
| `citation.py` | 17.9 KB | **两段自检核心**（抽取 / 覆盖判定 / 适用性）。纯函数，零依赖 |
| `kg.py` | 17.2 KB | 知识图谱（案由 → 要件 → 请求权基础/证据/争点）。纯函数，零依赖 |
| `tools_legal.py` | 18.7 KB | 12 个工具中的法库类（`laws_search` 等）。**依赖 openJiuwen** |
| `group.py` | 17.3 KB | AgentGroup 装配（`TeamAgentSpec` / 成员 / 工具注册） |
| `audit.py` | 8.9 KB | 自检工具封装（`audit_citations` / `audit_applicability`） |
| `config.py` | 14.0 KB | 配置与模型池 |
| `__init__.py` | 3.5 KB | 包导出 |

> ⚠️ **`__init__.py` 会连带 import `tools_legal`（进而 import openJiuwen）。**
> 所以「零依赖复用 `citation.py` / `kg.py`」**必须按文件路径加载，不能走包名 import**。
> 这一条已由 `tests/verify_zero_dep.py` 实测确认。

---

## 三、必须知道的 7 个技术事实（踩过坑的）

### 1. openJiuwen 成员 spec 解析顺序 —— 不按此写会静默失效

`openjiuwen/agent_teams/agent/agent_configurator.py:965-973`：

```python
if member_name and member_name in spec.agents:
    return spec.agents[member_name]
return spec.agents.get(role.value) or spec.agents.get("teammate") or spec.agents["leader"]
```

**含义**：`agents` 字典必须**按 `member_name` 建键**，否则未登记的成员会**静默兜底**到
`teammate`，最后落到 `leader` —— **不报错**。

这就是审计编号 **E1** 的 bug：修前 `kg_curator` / `drafter` / `citation_auditor`
三个成员拿到的都是检索员的 spec 与工具集，「两段自检」在运行时根本不存在。

**回归防线**：`tests/test_assembly.py`（9 组，断言 5 个成员各自解析到不同的 spec 对象）。
**动 `group.py` 的 `agents` 字典后，必须跑这个测试。**

### 2. `DeepAgentSpec.tools` 不接受 `LocalFunction`

联合类型是 `ToolCard | BuiltinToolSpec`。`@tool` 装饰器产出的是 `LocalFunction`，
必须传 `.card`，否则报：
```
Input should be a valid dictionary or instance of ToolCard … input_type=LocalFunction
```

### 3. `LocalFunction.invoke` 是 **async**

忘了 `await` 会拿到协程，然后在下游报
`TypeError: the JSON object must be str…not coroutine`。

### 4. `build()` 需要 OTLP exporter

缺了会报 `ModuleNotFoundError: No module named 'opentelemetry.exporter'`。
`requirements.txt` 已固定 `opentelemetry-exporter-otlp-proto-http` 与 `-grpc`。
（openjiuwen 的 `[observability]` extra **只带 api/sdk，不带 exporter**。）

### 5. `Runner.resource_mgr.add_tool()` **不抛异常**，返回 `Result`

用 `try/except` 计成功数会得到「恒等于工具总数」的假数字（审计编号 E6）。
要判 `Result.is_ok`，再兜底看 `error` / `err` 字段是否存在。

### 6. 工具的「真实返回」登记必须发生在**截断之后**（E3）

`REGISTRY.record()` 若在 `limit` 截断前执行，登记集合会包含**并未返回给模型**的法条，
自检口径被放宽。

### 7. 改了「抽取正则」必须同时检查「覆盖判定」

这两件事的口径不能分裂。本仓库有两个函数：

| 函数 | 用途 |
|---|---|
| `extract_citation_tokens()` | 从正文**抽取**引用（用 `CITATION_RE_EXTRACT`） |
| `article_covers()` | 判定某引用是否被工具返回**覆盖** |

`norm_article_no()` **会吃掉括号**（对齐上游），因此**不能用于结构比较**——
`norm("§1125(") == norm("§1125") == "§1125"`。
比较一律用 `norm_for_compare()`（保留半角括号）。
**这一条是我上一轮修 G11 时踩出来的：改了正则但用例仍红，就是因为规范化把结构吃了。**

---

## 四、硬性纪律（每条都有具体代价，不是风格偏好）

### D1. 不得虚报 —— 这条有取消资格的风险

赛事「参赛须知」把「**提交任何虚假信息**」列为**取消资格**项。

- 未落地的能力 → 标「**规划中**」
- 未验证的结论 → 标「**未验证**」
- 具体示范：`提交包/04-技术方案.md` 把 openJiuwen 组件拆成
  **「已装配（带代码位置）」** 与 **「规划中（代码中不存在）」** 两张表

**当前必须维持的诚实标注**（不得删改措辞）：

| 位置 | 内容 |
|---|---|
| `提交包/04-技术方案.md` §5 | 「运行层现状」：装配层真、**运行层尚未跑通**（`run_offline_demo` 的工具调用是顺序 `await tool.invoke()`，未驱动任务板与成员消息） |
| `提交包/04-技术方案.md` §3.2 | 「规划中」组件表（`symphony` / `dispatch_mode=scheduled` / `enable_swarmflow` / `model_router` / `pyzmq`） |
| `docs/07` §4 | SkillHub 上传与 jiuwenswarm 装载**未验证** |
| `资料/版本清单.json` | 0.7.3 安装包 SHA256 `disputed` |

### D2. 「第9999条」这个反例不得弱化

它是「自检不是模型自述」的**唯一**证据。出现在：
`run_offline_demo.py`、`tests/test_citation_audit.py`、
`skill/citation-audit/scripts/audit_citations.py --demo`、多份文档。

### D3. 对外主线不得改

✅ **openJiuwen 的 AgentGroup 解决「一起干活」；法元补上「干得可信」。**
❌ 「我们把编排层迁移到了 openJiuwen 框架」（这是工程叙事，不能当主线）

### D4. UI 文案写给律师，不写给评委和开发者

判定标准：**把这段字给一个不写代码的律师看，他需要知道吗？不需要 → 移出 UI。**

- ⚠️ 但**是「移出 UI」，不是「删除」** —— 边界声明在文档里**一条都不能少**
- `Legal-Workspace` 侧的验收：`src/views` + `src/components` 下 grep
  `方案稿|docs/12|未实现|不是梯度下降|纯仿真|0.8.0 规划` = **0 命中**

### D5. 改测试期望前，先确认真实语义

我上一轮**三次**把自己的错误猜测当成实现 bug，结果**都是我的期望错了**：

| 我以为 | 实际 |
|---|---|
| `applyDpNoise(向量, ε, seed)` | `applyDpNoise(counts: Record<string,number>, ε, rng)` —— 收的是**计数字典** |
| 一项指标改善即可采纳 | `adopt = 无显著回归 AND 同向改善数 >= 2` —— **只改一项不够** |
| 回归阈值是差值 | 是**乘性**的：`b < a*(1-tolerance)` |

**流程**：先 `read` 实现 → 再改期望。**不要把测试改绿当成目标。**

### D6. 改完必须回读确认

我上一轮有**两次** `edit` 的 `old_string` 实际不存在却**报成功**
（`README.md` 与 `Agent.tsx`），靠后续核实才发现。
**凡改关键文件，改完 `read` 一眼。**

### D7. 「两份记录不一致」时，先问是不是同一个对象

G7 的教训：我一度写下「说明文档正确、计划书写错」，
复核发现两个体积登记是同一量级（141,735,028 字节 = 135.17 MiB），
**没有体积矛盾**，且计划书记载该包**当天重打过** —— 两份记录可能对应不同构建产物。
**先问「是否描述同一个对象」，再判谁对谁错。**

### D8. 不要加「脱离 openJiuwen 也能跑」的兼容层

这是**参加 openJiuwen 大赛的作品**，加这种兜底是**反向叙事**。
正确做法（已采用）：**把承诺收窄到真正成立的范围** ——
`citation.py` / `kg.py` 是纯函数可用；完整装配需要 `pip install -r requirements.txt`。

### D9. 补丁必须无 BOM

`git am` 遇 BOM 直接 `Patch format detection failed`。
用 `git format-patch <base>..HEAD -o <dir>`（git 自己写盘），
**不要** `--stdout | Out-File -Encoding UTF8`（PowerShell 会加 BOM）。

### D10. 数字类断言必须**回跑取真值**

不要凭记忆写「74 行」「21 处」「40 组」——**回跑，然后把结果抄下来**。
本轮（第五轮）就因此改了 3 处：`Evolution.tsx` 行数、`docs/12` 边界表述计数、
测试组数。**数字错一次，整份材料的可信度都要打折。**

### D11. 隐式 ≠ 删除

把功能从 UI 撤下时，**原实现与边界表述必须另有着落**，不能随 UI 一起消失。
落点通常是两处：**代码里的实验台 + 文档里的机制节**。
撤下的每一句都要能在别处找到 ⇒ 才叫「分层」，否则叫「删除」。

### D12. 无数据不得渲染

没有数据时**不渲染**，而不是渲染一个「0」或「暂无」。
例：首页状态行与计划卡标注都设空值门 —— 未采纳配方时**整行/整句不出现**。

### D13. 隐私开关默认不参与

参与意愿是**三态**（`unset` / `on` / `off`），不是布尔 ——
让「没选过」与「明确选了不参与」在数据上可区分，UI 才能真做到「首次询问」。
**读取失败一律按 `unset`（偏向不上行）。只有明确 `on` 才算参与。**

### D14. 🆕 **注释不得断言未发生的动作**

**这条是第五轮踩出来的，性质与 D1 相同。**

当时 `src/views/Evolution.tsx` 的注释写着：

```
// · 全部机制与边界表述已归档到 `docs/12-联邦配方进化方案.md`
```

**而 `docs/` 一字未改。** 净效果是「机制内容既不在文档里、也不可达」——
实验台也没有路由、`0` 处 import，是孤儿。

**为什么隐蔽**：`grep docs/12` 能查到引用，**看起来像是做了**。
只有 `git show --stat` 逐补丁查、或比对两侧字节数，才能证伪。

> **动作要求**：写完「已归档 / 已完成 / 已同步」这类注释后，
> **立刻用一条命令去证明它**（`git show --stat`、字节数比对、`grep` 命中数）。
> 证不出来，就把注释改成「未做」。
> **注释也是一种对外声明，同样受 D1 约束。**

### D15. 🆕 **界面文案不得出现源码路径**

判据同 D4：**把这段字给一个不写代码的律师看，他需要知道吗？不需要 → 移出 UI。**

反例（第五轮修掉的）：

```tsx
<code>src/evolution-lab/</code> —— 完整实验台（内部研究 / 答辩直达）
```

正例：改成**站内深链** `<Link to="/evolution-lab">打开完整实验台</Link>`，
或只写「完整实验台（内部研究用）」，**不带路径**。

### D16. 🆕 **grep 判据必须排除注释，否则会误判**

**这条是复核方主动认的锅，写下来是为了不让下一轮被钝判据误导。**

第五轮给的验收命令是：

```bash
grep -rnE '方案稿|docs/12|纯仿真|差分隐私|K 匿名|加权平均|棱镜口径' src/views src/components
# 期望：0 命中
```

但实际剩余的命中**全是注释**（解释归档去向），**不是 UI 文案**，
实现本身是达标的。**钝判据会把合格实现判成不合格。**

**正确写法（排除整行注释与块注释）：**

```bash
grep -rnE '方案稿|docs/12|纯仿真|差分隐私|K 匿名|加权平均|棱镜口径' src/views src/components \
  | grep -vE '^\S+:[0-9]+:\s*(//|\*|/\*)'
# 期望：0 命中
```

**并注意一个副作用**：若为了「让 grep 归零」而在注释里引述被禁的词
（例如「此前误称已归档到 docs/12」），**注释本身会再次命中**。
处理方式是**换措辞**（如「此前误称已另行落地」），而不是删掉反思。
仓库里已有精确脚本 `scripts/check-ui-copy.mjs`（6 项，先剔注释再判定），**优先用它**。

---

## 五、验证命令与「什么算绿」

### 本仓库（Python）

```bash
python tests/verify_zero_dep.py          # 期望：6 项全 ✓，exit=0
python tests/test_citation_audit.py      # 期望：31 通过 / 0 失败
python tests/test_assembly.py            # 期望：9 通过 / 0 失败
python probe_build.py                    # 期望：末行「装配正确…全部成员解析到各自的 spec 与工具集」
python run_offline_demo.py               # 期望：exit=0，runtime/ 下出现新的 .docx + .json
python skill/citation-audit/scripts/verify_no_deps.py   # 期望：exit=0
```

> ⚠️ `run_offline_demo.py` **故意**在起草稿里埋了「第9999条」，
> 所以第一段自检的结论**本来就是 `ok=false`**（这正是要展示的能力）。
> **判据是「是否走完全部 6 步」+ exit=0，不是「自检通过」。**

### `Legal-Workspace`（TypeScript / Rust）

```bash
npm test              # 期望：75 passed (75)（evolution 41 + recipe 34）
npm run build         # 期望：exit=0，80 modules
cargo check           # 期望：exit=0（在 src-tauri 下）
```

> ⚠️ `cargo check` 需要两个构建产物存在，否则构建脚本会在配置阶段退出
> （**报错信息看起来像代码错，其实是缺文件**）：
> - `floating-ball/dist-060/win-unpacked`（悬浮球打包产物）
> - `src-tauri/preload/legal_preload.db`（预置法库）
>
> 只为过 check 的话，可以建空目录/空文件占位，**但用完必须清理**。

---

## 六、本地环境（我这轮建好的）

| 工具 | 版本 | 位置 |
|---|---|---|
| Python | 3.12.10 | 系统 |
| openjiuwen | 0.1.19 | site-packages |
| **Node.js** | **v24.22.0** | `D:\Matchs\openjiuwen\_tools\node-v24.22.0-win-x64`（已写入用户 PATH） |
| npm | 11.19.1 | 同上 |
| cargo | 1.98.0 | 系统 |
| vitest | ^2.1.9 | `Legal-Workspace` devDependency |

> **vitest 特意选 2.x**：5.x 要求 `vite>=6`，而 `Legal-Workspace` 是 `vite@5.4`。
> 用 `--legacy-peer-deps` 强装 5.x 会造成版本不匹配（**别这么做**）。

---

## 七、任务台账（怎么领活）

**完整待办与验收标准在 [`接手必读.md`](接手必读.md) 第四节（T1–T8）。**
这里只列「哪些 AI 能做、哪些必须人做」：

| 任务 | 谁做 | 阻塞在哪 |
|---|---|---|
| T1 生成仓库提交物 SHA256 清单 | ✅ **AI 可独立做** | 无 |
| T2 按 jiuwenswarm 规范补 Skill manifest | ✅ AI 可做 | 需先取到 jiuwenswarm 的 Skill 接口文档 |
| T3 接入 `auditPassFloor` / `minSamples` | ✅ AI 可做 | 需 `Legal-Workspace` 写权限或走补丁 |
| T4 真机端到端验证 EV1/EV2 | ⚠️ 需人点一次 | 需能跑 `npm run tauri dev` |
| **T5 重剪 DEMO 视频 ≤180s** | 🔴 **只能人做** | 录屏 + 配音 + 剪辑 |
| T6 提交包裁剪 ≤500 MB | ⚠️ 需人决策 | 依赖 T5 |
| T7 队伍名核对 + SHA256 复核 | ⚠️ 需人 | 赛事平台登录 + 安装包实体 |
| **T8 提供模型 Key 跑通协同** | 🔴 **需人** | 模型 Key |

### 领活时的规矩

1. **一次只领一条**，做完跑对应验收命令，把**真实输出**贴回。
2. **改动不得削弱任何已有测试**。如果测试红了，先判断是「我的改动错了」还是
   「测试期望该更新」—— 按 **D5** 的流程确认，并在提交信息里写明理由。
3. **提交信息要写清**：做了什么 / 为什么 / **附验收命令与输出** / 未做或未验证的部分。
   本仓库历史提交都是这个格式，可以 `git log -3` 看范例。
4. **不确定就问**，不要猜着改。尤其是 D1（虚报）与 D2（反例）踩了就是事故。

---

## 八、当前状态快照（截至 2026-10-15）

| 项 | 值 |
|---|---|
| 远端 HEAD | `0425763` + 本轮交接文档提交 |
| 工作区 | 干净 |
| Python 测试 | 31 + 9 + 6 = **46 组全绿** |
| `Legal-Workspace` 测试 | **75 组全绿** |
| `Legal-Workspace` 远端 | 🔴 **落后 3 个提交**（推送被 403 拒，`thinanphen` 无 Write 权限） |
| 硬性不合规 | ① DEMO 视频 432.5s（限 180s）② 提交包 657.4 MB（限 500 MB） |
| 距截止 | **15 天**（2026-10-30，扣 2 天缓冲实际 13 天） |

---

## 九、如果你只想记一句话

> **这个项目不缺想法，缺的是「把已做的做成可信证据」和「把硬性不合规项消掉」。**
> 前者已有 46 + 75 组测试和可复现命令兜底；
> 后者（**视频、体积、队名、模型 Key**）**只能由人做**。
> **不要为了显得在干活而加新功能。**
