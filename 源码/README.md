# 上游源码与内部文档（源码）

> 本目录收录 **[法元 · Faron](https://github.com/lin612320/Legal-Workspace)** 的内部文档与仓库元信息。
> 源码本体（约 9.2k 行 TS + 5.1k 行 Rust）**未复制进来** —— 上游仓库本就公开，
> 复制会产生两份可能漂移的副本。本仓库的 Python 实现**逐条对齐**该仓库的
> `feature/赛事版` 分支（@ `e8dd45c` = 0.7.2），对齐关系见根目录 README。

---

## 目录内容

### `Legal-Workspace/` —— 上游仓库元信息

| 文件 | 说明 |
|---|---|
| `README.md` | 上游仓库说明（23.9 KB）：技术栈、功能一览、运行模式、目录结构、文档索引、已知缺口 |
| `CHANGELOG.md` | 0.1.0 → 0.7.3 演进记录（43.7 KB） |
| `package.json` | 版本号与依赖（可核对版本口径） |

### `Legal-Workspace-docs/` —— 内部文档（`docs/01`–`docs/12`）

这些是理解产品的关键材料，**原先只在团队内部维护、未随提交包对外提供**。

| 文件 | 内容 |
|---|---|
| `01-技术架构.md` | 技术架构、前后端通信、双环境降级、窗口管理 |
| `02-功能模块.md` | 各版块功能明细与完成状态 |
| `03-数据库设计.md` | **表结构、种子数据、备份与还原** ← 对齐 OpenJiuwen 版图谱时的依据 |
| `04-开发与构建指南.md` | 环境准备、开发构建、打包、常见问题 |
| `05-优化路线图.md` | P0–P3 优化建议、技术债与发布里程碑 |
| `06-参赛改进方案.md` | openJiuwen 大赛改进方案：端到端闭环、工具调用、交付与里程碑 |
| `07-真机验收清单.md` | 真机验收清单、评审演示关键词对照、中文法库接入方案 |
| `08-参赛材料包.md` | 参赛创意描述、LLM 流程、五维自评、竞品与商业模式、演示脚本、答辩 Q&A |
| `09-真机验收执行指引.md` | 真机逐项执行清单与记录模板 |
| `11-赛事版改动说明.md` | 赛事版相对主版本的改动清单与差异说明 |
| `12-联邦配方进化方案.md` | **0.8.0 规划 · 方案稿**：联邦配方进化（FRE）——动机、架构、信号与奖励、隐私合规、里程碑 |
| `功能演示报告.md` / `.docx` | 演示路径、话术与口径 |
| `项目计划书.md` / `.docx` | 项目计划书（交付版） |
| `Project-Plan-EN.md` / `.docx` | 英文项目计划书（对应 0.6.0 基线） |
| `Feature-Demo-Report-EN.md` / `.docx` | 英文功能演示报告 |
| `README.md` | 文档索引 |

> ⚠️ **口径提醒**：`06`/`08`/`Project-Plan-EN` 等文档里写着
> 「首届 openJiuwen 智能体创新大赛」——那是**上一场比赛**。
> 投本届 openJiuwen 大赛前需要全量重写赛事口径，见
> [`../docs/01-贴合度评估与整改建议.md`](../docs/01-贴合度评估与整改建议.md) 的 **G4**。

---

## 为什么这些文档值得放进本仓库

本仓库的 Python 实现要与上游 TypeScript/Rust 实现**行为一致**（否则交付物口径会自相矛盾）。
对齐时我主要依据的就是这些文档与源码：

| 对齐项 | 依据 |
|---|---|
| 引用抽取正则 | `src/lib/agent.ts` 第 610–611 行 |
| 归一化与覆盖判定 | `src/lib/agent.ts` 第 625–635 行 |
| 两段自检 | `src/lib/agent.ts` 第 599–717 行 |
| 四角色系统提示词 | `src/lib/agent.ts` 第 351–357 行 |
| 5 类任务与交付物骨架 | `src/lib/agent.ts` 第 95–140 行 |
| 知识图谱种子与 5 种固定关系 | `src-tauri/src/db.rs` 第 1267–1337 行 |
| 图谱骨架抽取 | `src/lib/kg.ts` `skeletonOf()` |
| 节点/边契约与候选边阈值 0.8 | `src/lib/kgTypes.ts` |
| 5 个工具契约 | `src/lib/tools.ts` |
| 表结构（`kg_node` 的 `name_alt` 字段等） | `docs/03-数据库设计.md` + `src-tauri/src/db.rs` |

---

## 获取源码本体

```bash
git clone --branch feature/赛事版 https://github.com/lin612320/Legal-Workspace.git
```

仓库结构：

```
Legal-Workspace/
├── src/                    React 18 + TS（约 9,248 行）
│   ├── lib/                agent.ts(41KB) / tools.ts / kg.ts / evolution.ts(48KB) ...
│   ├── views/              Agent.tsx(45KB) / Evolution.tsx(38KB) / Laws.tsx ...
│   └── components/         KnowledgeGraph.tsx / Layout / Sidebar / Topbar
├── src-tauri/              Rust 桌面壳（约 5,142 行）
│   └── src/                db.rs(82KB) / lib.rs(56KB) / office.rs(40KB) / docx.rs(18KB) / ball.rs(19KB)
├── floating-ball/          Electron 33 悬浮球（独立应用）
├── 官网演示/index.html      产品演示站源码（单文件，527 KB）
└── docs/                   本目录的原始来源
```

> 📌 **预置法库不在仓库里**：`src-tauri/preload/legal_preload.db`（约 467–490 MB，含 152,940 条法条）
> 被上游 `README.md` 第 158 行明确标注为 **git 忽略、不入库**，随安装包分发。
