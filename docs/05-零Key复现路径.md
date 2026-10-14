# 核心判定（零依赖复现）

> **本文件解决的问题（编号 E12）**：原来「评委零 API Key 复现核心判定」这个承诺
> 实际上做不到——因为 `faron_agentgroup/__init__.py` 会连带 import
> `tools_legal.py`（其中 `from openjiuwen.core.foundation.tool import tool`），
> 于是**在没装 openJiuwen 的机器上，连纯函数自检都跑不起来**。

---

## 一、零安装复现：两段确定性自检

`citation.py` 与 `kg.py` 是**纯函数模块**——只用标准库，不依赖 openJiuwen、不调用任何模型。

> ⚠️ **必须按文件路径加载，不能走包名 import。**
> 因为 `faron_agentgroup/__init__.py` 会连带 import `tools_legal.py`
> （其中 `from openjiuwen.core.foundation.tool import tool`），
> 于是 `from faron_agentgroup.citation import ...` 在干净机器上会直接报
> `ModuleNotFoundError: No module named 'openjiuwen...'`。
> 这条已由 `tests/verify_zero_dep.py` 实测确认（它用 import hook 屏蔽全部
> openjiuwen* 来模拟评委机器）。

```bash
python - <<'PY'
import importlib.util, sys

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

cit = load("cit", "src/faron_agentgroup/citation.py")   # 纯函数，零依赖
kgm = load("kgm", "src/faron_agentgroup/kg.py")         # 纯函数，零依赖

# 1) 图谱定案由 → 取骨架（要件 / 请求权基础 / 证据 / 争点）
sk = kgm.KG.skeleton("涉外合资经营合同纠纷")
print("构成要件：", [e["name"] for e in sk["elements"]])

# 2) 第一段自检：正文引用 vs「工具真实返回集合」
refs = [{"title": "民法", "article_no": "第五百二十二条", "source": "e-Gov", "excerpt": ""}]
body = "依据第五百二十二条与第9999条，本案应支持原告请求。"
a = cit.audit_citations(body, refs)
print(a.unmatched)            # → ['第9999条']
print(cit.audit_report(a))    # → 含「第9999条」被点名的完整报告
PY
```

**期望输出**：`unmatched` 为 `['第9999条']` —— 故意埋进去的库外条号被代码级规则当场点名。

> **一键验证**（推荐，比手抄更可靠）：
> ```bash
> python tests/verify_zero_dep.py
> ```
> 它会屏蔽全部 openjiuwen import 后重跑上述流程，
> 并在最后断言「全程零框架 import」，把这条承诺变成可执行证据。

> 这就是「零 API Key、本地可复现」的**真实适用范围**：
> **两段确定性自检**（不依赖模型、不依赖框架）。
> 而不是「整个 Agent Group 都能零依赖跑」。

---

## 二、完整装配验证：需要 openJiuwen

`group.py` / `audit.py` / `tools_legal.py` 依赖 openJiuwen 的工具与团队原语，
以及完整运行需要 `pip install -r requirements.txt`：

```bash
pip install -r requirements.txt

# ① 装配正确性（逐成员解析到自己的 spec 与工具集）
python probe_build.py

# ② 测试向量（31 组，含反例点名与 E1 装配防线）
python tests/test_citation_audit.py
python tests/test_assembly.py

# ③ 端到端（图谱 → 检索 → 起草 → 两段自检 → 导出 .docx）
python run_offline_demo.py
```

### 每一步是否真的需要框架？

| 步骤 | 需要 openJiuwen？ | 说明 |
|---|---|---|
| 两段确定性自检（`citation.py`） | ❌ **不需要** | 纯函数 |
| 知识图谱（`kg.py`） | ❌ **不需要** | 纯函数 + 内存结构 |
| 工具注册与调用（`tools_legal.py` / `audit.py`） | ✅ 需要 | `@tool` 装饰器来自 SDK |
| 团队装配（`group.py`） | ✅ 需要 | `TeamAgentSpec` 等来自 SDK |
| `probe_build.py` / `test_assembly.py` | ✅ 需要 | 要走 SDK 真实解析路径 |
| `run_offline_demo.py` | ✅ 需要 | 经工具层 |
| `run_online.py` | ✅ 需要 + 模型 Key | 另需 `aiohttp`（已列入 requirements） |

---

## 三、这个范围划分是刻意的

我们没有给包加「没框架也能 import」的兼容层——**为参加 openJiuwen 大赛的作品
引入「不依赖 openJiuwen 也能跑」的兜底，是反向叙事，也掩盖了真实依赖关系**。

取而代之的是：**如实划出「哪部分零依赖可复现」的边界**，并把这条路径放在
README 顶部作为评委的第一屏。

赛事「参赛须知」把「提交任何虚假信息」列为取消资格项，
所以把承诺**收窄到它真正成立的范围**，比用一个兼容层硬撑大承诺要稳妥得多。
