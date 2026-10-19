# runtime/ — 取证产物

本目录存放**运行产生**的取证物，用于「提交材料可核验」。

| 文件 | 来源 | 说明 |
|---|---|---|
| `deliverable_<时间戳>.docx` | `run_offline_demo.py` | 五段式文书 + **2 张 Word 原生表格** |
| `runlog_<时间戳>.json` | `run_offline_demo.py` | 六步全过程取证日志 |
| `coordination_<时间戳>.json` | `run_stub_online.py` | 运行层实测轨迹：框架任务板 / 成员消息 / HITL 的**真实调用**记录 |
| `skills-visibility.json` | 运行时 | openJiuwen 技能可见性快照（小文件，随仓库保留） |

---

## ⚠️⚠️ 看 `coordination_*.json` 时最容易犯的错：**别用 grep 数事件次数**

`claim_task` / `member_complete_task` 这些**工具名会出现在主理自己的提示语里**
（比如「请 view_task 后 claim_task 开工，完成后 member_complete_task 交付」）。

用 `grep -c claim_task` 数出来的数字**严重高估**：

| 数法 | `claim_task` | `member_complete_task` |
|---|---|---|
| `grep claim_task` | **10** ❌ | **9** ❌ |
| 轨迹里的 `summary.by_event` / `summary.required` | **0** ✅ | **0** ✅ |

**唯一可信的是轨迹自带的 `summary.by_event`、`summary.required`、`checks` 三段**
—— 那是记录器挂在框架 manager 方法上按**真实调用**计数的，不是文本匹配。

不想自己解析 JSON，直接：

```bash
python run_stub_online.py --verify runtime/coordination_<时间戳>.json
```

> 这条教训是复盘方（`lin612320` 一侧）第一眼用 grep 差点报「全过了」得来的。
> 写在这里，免得下一个接手的人踩同一个坑。

---

## ⚠️ 约定：**本目录只保留「最新一组」产出**

`run_offline_demo.py` **每次运行都会生成一对新的带时间戳文件**。
如果不清理，`runtime/` 会随每次验证不断膨胀，而且：

- `资料/提交物清单.json` 会随之变化 → 清单在两次运行之间「不一致」
- 提交包里堆着多份内容相同、只有时间戳不同的文书，**看起来像噪音**

**因此每次跑完验证后，保留最新一组，删掉其余：**

```powershell
# 只保留最新一组（按文件名时间戳排序）
Get-ChildItem runtime -Filter 'deliverable_*.docx' | Sort-Object Name | Select-Object -SkipLast 1 | Remove-Item
Get-ChildItem runtime -Filter 'runlog_*.json'      | Sort-Object Name | Select-Object -SkipLast 1 | Remove-Item
```

```bash
# bash / Git Bash
ls runtime/deliverable_*.docx | sort | head -n -1 | xargs -r rm
ls runtime/runlog_*.json      | sort | head -n -1 | xargs -r rm
```

或者直接跑本仓库的收敛脚本：

```bash
python tools/gen_manifest.py        # 会先提醒清单是否已过期
```

> **为什么要保留一组而不是全删**：`.docx` 与 `runlog` 是「两段自检」的**物证** ——
> 评委可以打开 `.docx` 看到「第9999条」被点名的原文，
> 这比任何文字声明都硬。所以**必须有一组在仓库里**。

---

## 为什么 `runtime/` 整体在 `.gitignore` 里，却又提交了部分文件

`.gitignore` 只忽略**运行期临时文件**：

```
runtime/*.tmp
runtime/*.lock
runtime/.skills-visibility.json*
runtime/skills-visibility.json
```

`.docx` 与 `runlog_*.json` **不在忽略范围内**，是**有意保留的取证物**。
（`skills-visibility.json` 虽被忽略，但已跟踪的版本不受影响。）

---

## 关于「同输入同输出」的核验

`run_offline_demo.py` 是确定性的：**同一份代码 + 同一份演示法库 → 内容一致的产出**。
两次运行的文件**只有时间戳不同**（`.docx` 内部也嵌了生成时间，故字节数可能差 ±2 字节）。

我们在 `docs/06-进度与交接记录.md` 里记录过一次跨机器的对照：
**38,519 B vs 38,521 B，差 2 字节（时间戳），内容一致** ——
这正是「确定性」的实测证据。
