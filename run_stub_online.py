#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用**本地确定性桩**把 openJiuwen 的编排层真跑一遍，并落一份协同轨迹。

════════════════════════════════════════════════════════════════════════
这个脚本证明什么、不证明什么（三处材料都按这个口径写，别改）
════════════════════════════════════════════════════════════════════════

证明：**编排跑通了** —— openJiuwen `TeamAgent` 真的被驱动，
      框架的**任务板**（建单 / 领活 / 交付）、**成员消息**、**HITL 复审闸门**
      在这条链路上**真实流转**，任何人本地一条命令可复现。

不证明：**模型能力**。这里没有真模型 —— 推理来自 `tools/stub_llm_server.py`
        的确定性桩，因此它也**不能替代** `run_online.py` 需要的真 Key。

一句话（本文件与轨迹头部、README、技术方案三处必须一致）：

    模型为本地确定性桩（stub），框架任务板与成员消息为真实流转。

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════

    python run_stub_online.py                  # 自起桩 + 跑一轮 + 落轨迹
    python run_stub_online.py --port 8802      # 换端口
    python run_stub_online.py --external-stub  # 复用已在跑的桩（不自己起）
    python run_stub_online.py --timeout 240    # 单轮上限秒数

产物：`runtime/coordination_<ts>.json`（含头部口径字段 + 事件流 + 汇总）
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE / "tools"))

# 控制台编码兜底（中文 Windows 默认 GBK）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

try:
    "✅".encode(sys.stdout.encoding or "utf-8")
    OK, NG = "✅", "❌"
except Exception:
    OK, NG = "[OK]", "[FAIL]"

from stub_llm_server import STATS as STUB_STATS  # noqa: E402
from stub_llm_server import STUB_NOTE, serve as stub_serve  # noqa: E402

COMMISSION = (
    "我方（中国某制造企业）与日本某商社设立合资公司，合资合同履行中出现出资迟延与"
    "经营分歧。请出具《合同审查意见书》：①日方出资迟延是否构成违约、我方能否请求"
    "继续履行；②准据法与管辖约定是否有效；③风险条款与修改建议。"
    "引用法条必须来自本地法库检索结果。"
)


# ---------------------------------------------------------------------------
# 事件记录器：在**框架执行侧**打点
# ---------------------------------------------------------------------------
#
# 为什么不记录「桩收到了什么请求」：
#   那只证明 LLM **请求**了某个工具，不证明框架**真的执行**了它。
#   要证明「任务板真流转」，必须挂在框架自己的 manager 上。
#
# 打点对象（openjiuwen.agent_teams.tools）：
#   TeamTaskManager.add            → 主理建单
#   TeamTaskManager.claim          → 成员领活
#   TeamTaskManager.complete       → 成员交付
#   TeamTaskManager.verify_task    → HITL 复审闸门
#   TeamMessageManager.send_message / broadcast_message → 成员间通信

class Recorder:
    """收集协同事件（线程安全、保序）。"""

    #: 方法名 → (事件名, 归类)
    #:
    #: ⚠️ 两个实测踩出来的坑：
    #:  ① `create_task` 工具**不是**调 `TeamTaskManager.add`，而是 `add_graph`
    #:     （任务图/依赖走这条路）。只挂 `add` 时 create_task 明明执行了、钩子一次没响。
    #:  ② `update_task(assignee=...)` 会把任务推到成员并置 `in_progress`，
    #:     走的是 `assign` / `start_task` / `update_task`，不是 `claim`。
    #:     所以「成员开始干活」与「成员自己 claim」是两条不同的路径，都要看。
    HOOKS = {
        "add_graph": ("create_task", "task_board"),
        "add": ("create_task", "task_board"),
        "claim": ("claim_task", "task_board"),
        "complete": ("member_complete_task", "task_board"),
        "assign": ("assign_task", "task_board"),
        "start_task": ("start_task", "task_board"),
        "update_task": ("update_task", "task_board"),
        "reassign": ("reassign_task", "task_board"),
        "reset": ("reset_task", "task_board"),
        "cancel": ("cancel_task", "task_board"),
        "verify_task": ("hitl_verify", "hitl"),
        "settle_review": ("hitl_verify", "hitl"),
        "send_message": ("send_message", "message"),
        "broadcast_message": ("broadcast_message", "message"),
        # 成员动态召唤（R9 · P0-2）。它在 TeamBackend 上，不在 TaskManager 上。
        "spawn_member": ("spawn_member", "member"),
    }

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._t0 = time.time()
        self._patched: list[tuple[Any, str, Any]] = []

    # ---- 记录 ----

    def _record(self, name: str, kind: str, args: list[Any], kwargs: dict[str, Any],
                result: Any, error: str | None) -> None:
        with self._lock:
            self.events.append({
                "seq": len(self.events) + 1,
                "t_ms": int((time.time() - self._t0) * 1000),
                "event": name,
                "kind": kind,
                "args": _brief(args),
                "kwargs": _brief(kwargs),
                "result": _brief(result),
                "error": error,
            })

    # ---- 打点 ----

    def patch(self) -> list[str]:
        """给框架的 manager 挂上记录钩子，返回已挂载的列表。"""
        try:
            from openjiuwen.agent_teams.tools.message_manager import TeamMessageManager
            from openjiuwen.agent_teams.tools.task_manager import TeamTaskManager
        except Exception as exc:  # noqa: BLE001
            print(f"{NG} 无法导入框架 manager：{exc}")
            return []

        # TeamBackend.spawn_member 在另一个模块（R9 · P0-2 需要看它成没成）
        TeamBackend = None
        try:
            from openjiuwen.agent_teams.tools.team import TeamBackend as _TB
            TeamBackend = _TB
        except Exception:  # noqa: BLE001
            pass

        targets = [
            (TeamTaskManager, "add_graph"),
            (TeamTaskManager, "add"),
            (TeamTaskManager, "claim"),
            (TeamTaskManager, "complete"),
            (TeamTaskManager, "assign"),
            (TeamTaskManager, "start_task"),
            (TeamTaskManager, "update_task"),
            (TeamTaskManager, "reassign"),
            (TeamTaskManager, "reset"),
            (TeamTaskManager, "cancel"),
            (TeamTaskManager, "verify_task"),
            (TeamTaskManager, "settle_review"),
            (TeamMessageManager, "send_message"),
            (TeamMessageManager, "broadcast_message"),
        ]
        if TeamBackend is not None:
            targets.append((TeamBackend, "spawn_member"))

        mounted: list[str] = []
        for cls, meth in targets:
            orig = getattr(cls, meth, None)
            if orig is None or not callable(orig):
                continue
            name, kind = self.HOOKS[meth]

            def make(orig_fn: Any, ev: str, kd: str, mname: str):
                is_async = inspect.iscoroutinefunction(orig_fn)

                if is_async:
                    async def awrapper(*a: Any, **kw: Any) -> Any:
                        try:
                            res = await orig_fn(*a, **kw)
                            self._record(ev, kd, list(a), kw, res, None)
                            return res
                        except Exception as exc:  # noqa: BLE001
                            self._record(ev, kd, list(a), kw, None,
                                         f"{type(exc).__name__}: {exc}")
                            raise
                    return awrapper

                def wrapper(*a: Any, **kw: Any) -> Any:
                    try:
                        res = orig_fn(*a, **kw)
                        self._record(ev, kd, list(a), kw, res, None)
                        return res
                    except Exception as exc:  # noqa: BLE001
                        self._record(ev, kd, list(a), kw, None,
                                     f"{type(exc).__name__}: {exc}")
                        raise
                return wrapper

            setattr(cls, meth, make(orig, name, kind, meth))
            self._patched.append((cls, meth, orig))
            mounted.append(f"{cls.__name__}.{meth}")
        return mounted

    def unpatch(self) -> None:
        for cls, meth, orig in self._patched:
            with contextlib.suppress(Exception):
                setattr(cls, meth, orig)
        self._patched.clear()

    # ---- 汇总 ----

    def summary(self) -> dict[str, Any]:
        by_event: dict[str, int] = {}
        for e in self.events:
            by_event[e["event"]] = by_event.get(e["event"], 0) + 1
        failed = [e for e in self.events if e.get("error")]
        return {
            "total_events": len(self.events),
            "by_event": by_event,
            "failed_events": len(failed),
            "required": {
                "create_task": by_event.get("create_task", 0),
                "claim_task": by_event.get("claim_task", 0),
                "member_complete_task": by_event.get("member_complete_task", 0),
                "send_message": by_event.get("send_message", 0)
                + by_event.get("broadcast_message", 0),
                "hitl_verify": by_event.get("hitl_verify", 0),
            },
        }


def _brief(v: Any, depth: int = 0) -> Any:
    """把参数/返回值压成可 JSON 序列化的简报（不塞完整对象）。"""
    if depth > 2:
        return "…"
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v if len(v) <= 300 else v[:300] + f"…(+{len(v) - 300})"
    if isinstance(v, (list, tuple)):
        return [_brief(x, depth + 1) for x in list(v)[:6]]
    if isinstance(v, dict):
        return {str(k): _brief(x, depth + 1) for k, x in list(v.items())[:8]}
    # 框架的结果对象：优先取它自己的 __dict__ / 常见字段
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(v, attr, None)
        if callable(fn):
            with contextlib.suppress(Exception):
                return _brief(fn(), depth + 1)
    d = getattr(v, "__dict__", None)
    if isinstance(d, dict):
        return {"_type": type(v).__name__,
                **{k: _brief(x, depth + 1) for k, x in list(d.items())[:8]}}
    return f"<{type(v).__name__}>"


# ---------------------------------------------------------------------------
# 桩生命周期
# ---------------------------------------------------------------------------

def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _start_stub(port: int) -> threading.Thread:
    th = threading.Thread(target=stub_serve, args=(port,), kwargs={"once": False},
                          daemon=True, name="stub-llm")
    th.start()
    # 等它真的 listen 上
    for _ in range(50):
        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return th
        time.sleep(0.1)
    return th


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _sanitize_proxy_env() -> list[str]:
    """修正代理环境变量，避免 `httpx2` 在构造客户端时崩溃。

    ── 这是一个真实踩到的环境级 bug（必须修，且值得写进材料）──────────
    `openai` 3.x 改用 `httpx2`，而 `httpx2` 在 `AsyncClient.__init__` 里会把
    **代理映射的每个键**当作 URL 模式解析：

        self._mounts = { URLPattern(key): ... for key in proxy_map }

    代理映射来自 `_get_proxy_map()`，它会把 `NO_PROXY` 的**每一项**变成键。
    于是只要 `NO_PROXY` 里出现**带方括号的 IPv6**（例如 `[::1]`），
    解析就会得到非法端口并抛异常：

        httpx2.InvalidURL: Invalid port: ':1]'

    **后果**：`openai.AsyncOpenAI(...)` 根本无法构造 —— 与 base_url 无关，
    与 Key 无关，**任何** OpenAI 兼容端点都发不出请求。

    本机实测（四组对照）：
        NO_PROXY=...,::1,[::1]   → ❌ InvalidURL: Invalid port: ':1]'
        NO_PROXY=...,::1         → ✅
        NO_PROXY=(清空)           → ✅
        NO_PROXY=localhost,127.0.0.1 → ✅

    > 这条同时解释了「`run_online.py` 零成功记录」：在有这个 `NO_PROXY` 的机器上，
    > **即使配上真 Key 也发不出请求**。所以那件事的根因可能不是 Key，
    > 而是环境变量。修法就是去掉 `[::1]`。

    Returns:
        被改动的变量名列表（全部为"已修正"的，便于打印）。
    """
    fixed: list[str] = []
    for name in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(name)
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        kept = [p for p in parts if not (p.startswith("[") and p.endswith("]"))]
        if len(kept) != len(parts):
            os.environ[name] = ",".join(kept)
            fixed.append(name)
    # 本地回环永远不该走代理（正确性要求，与上面的 bug 无关）
    for name in ("NO_PROXY", "no_proxy"):
        cur = os.environ.get(name, "")
        need = [h for h in ("127.0.0.1", "localhost") if h not in cur]
        if need:
            os.environ[name] = ",".join([x for x in (cur, *need) if x])
    return fixed


async def _diagnose_board(group: Any) -> dict[str, Any]:
    """运行中直接问框架：任务板有哪些任务、成员各是什么状态。

    为什么需要：`create_task` 返回 `TaskGraphResult` 对象，光看返回值判断不了
    「任务是否真落库」。直接读框架自己的 manager 才是硬证据。
    另外成员静默时，这里能看到它是 `ready` 还是在等审批。
    """
    out: dict[str, Any] = {}
    try:
        backend = group.agent._configurator.team_backend  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return {"error": f"取不到 team_backend：{type(exc).__name__}: {exc}"}

    # 任务板
    try:
        res = await backend.task_manager.list_tasks_with_deps()
        tasks = getattr(res, "tasks", None) or getattr(res, "data", None) or res
        rows = []
        for t in tasks or []:
            d = t if isinstance(t, dict) else getattr(t, "__dict__", {}) or {}
            rows.append({
                "task_id": d.get("task_id"),
                "title": d.get("title"),
                "status": d.get("status"),
                "assignee": d.get("assignee"),
                "reviewer": d.get("reviewer"),
            })
        out["tasks"] = rows
    except Exception as exc:  # noqa: BLE001
        out["tasks_error"] = f"{type(exc).__name__}: {exc}"

    # 成员状态
    try:
        from openjiuwen.agent_teams.tools.team_dao import TeamDao  # 可能不存在，容错
        out["dao"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        members = await backend.list_members()  # 常见命名
    except Exception:  # noqa: BLE001
        members = None
        for meth in ("get_members", "list_team_members"):
            fn = getattr(backend, meth, None)
            if callable(fn):
                try:
                    members = await fn()
                    break
                except Exception:  # noqa: BLE001
                    continue
    if members is not None:
        rows = []
        for m in members:
            d = m if isinstance(m, dict) else getattr(m, "__dict__", {}) or {}
            rows.append({
                "name": d.get("member_name") or d.get("name"),
                "status": d.get("status"),
                "role": str(d.get("role_type") or d.get("role") or ""),
            })
        out["members"] = rows
    return out


async def _drive(group: Any, timeout: float, rec: Recorder) -> tuple[int, list[str], str | None, dict]:
    """真的驱动 TeamAgent；把流式分片收集成文本摘要。

    ⚠️ **必须传一个真实的团队 session**。
    先前传 `session=None` 的实测后果（已踩过，记下来省得再踩）：

        ExecutionError: [123023] deepagent runtime error,
                        reason: NativeHarness not started. Call start() first.
        Callback execution failed: on_poll_task - no such table: team_task_<suffix>

    机制：`TeamAgent.stream()` → `_coordination.start(session)` 会用
    `session.get_session_id()` 推导**按会话后缀**的动态表名
    （`team_task_<suffix>` / `team_message_<suffix>`）。
    session 为 None 时没有 session_id，这些表不会被创建，
    协调轮询（`on_poll_task`）随即撞上 `no such table`；
    而 harness 也因同样的生命周期缺失报 "not started"。

    ── 为什么还要「叫醒成员」──────────────────────────────────────
    成员是 `inprocess` 起的 asyncio 任务，起来后进入协调循环**等待事件**
    （新消息 / 任务状态变化）。而主理的 `create_task` 与 `broadcast` 往往
    在成员**尚未开始监听**时就发出了 —— 实测这一版就是：
    7 次模型请求全在 6 秒内跑完，成员到第 8 秒才 `coordination starting`，
    于是它启动后无事可做，静默等到超时。

    所以这里用框架**自己的** `TeamAgent.broadcast()`（主理 → 全员）主动推一把。
    这不是伪造：走的仍是 `TeamMessageManager.broadcast_message`，
    与主理手动发消息同一条路径，记录里能看到。
    """
    chunks: list[str] = []
    err: str | None = None

    # 会话 id 用固定值：确定性优先，且便于复现同一套表
    try:
        from openjiuwen.core.session.agent_team import Session as TeamSession
        session = TeamSession(session_id="faron-stub-session", team_id="faron_wenshu_team")
    except Exception as exc:  # noqa: BLE001
        return 3, chunks, f"无法创建团队 session：{type(exc).__name__}: {exc}", {}

    async def collect() -> None:
        async for chunk in group.run(COMMISSION, session=session):
            text = getattr(chunk, "content", None) or str(chunk)
            if text:
                chunks.append(str(text))

    async def nudge_loop(deadline: float) -> None:
        """成员可能错过唤醒事件；按需用主理广播把它们叫起来。"""
        nudges = 0
        while time.time() < deadline:
            await asyncio.sleep(6)
            req = rec.summary()["required"]
            if req["claim_task"] >= 1 and req["member_complete_task"] >= 1:
                return
            if nudges >= 6:  # 别无限推
                continue
            nudges += 1
            msg = (
                f"提醒（{nudges}）：看板上有 task-1（检索溯源）与 task-2（起草意见书）。"
                "被指派的成员请 view_task 后 claim_task 开工，完成后 member_complete_task 交付。"
            )
            try:
                await group.broadcast(msg)
            except Exception:  # noqa: BLE001
                pass

    try:
        await asyncio.wait_for(
            asyncio.gather(collect(), nudge_loop(time.time() + timeout)),
            timeout=timeout + 5,
        )
        diag = await _diagnose_board(group)
        return 0, chunks, None, diag
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            diag = await _diagnose_board(group)
        return 3, chunks, "超时", diag
    except Exception as exc:  # noqa: BLE001
        return 4, chunks, f"{type(exc).__name__}: {exc}", {}


def verify_trace(path: str) -> int:
    """只读一份已有轨迹，打印 summary / checks / 是否与期望一致。

    为什么需要（R9 · P1-2）：
        复核方第一眼通常用 `grep claim_task` 数次数 —— 会**严重高估**，
        因为 "claim_task" / "member_complete_task" 这些词会出现在
        **主理自己的提示语**里（"请 view_task 后 claim_task 开工…"）。
        实测被误导过一次：grep 数出 claim_task=10、member_complete_task=9，
        而真值是 0。

        唯一可信的是轨迹自带的 `summary.by_event` / `summary.required` / `checks`
        —— 那是记录器按**框架 manager 的真实调用**计数的，不是文本匹配。

    用法：
        python run_stub_online.py --verify runtime/coordination_<ts>.json
    """
    import json as _json

    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    if not p.exists():
        print(f"  ❌ 轨迹文件不存在：{p}")
        return 2

    data = _json.loads(p.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    required = summary.get("required") or {}
    checks = data.get("checks") or {}
    by_event = summary.get("by_event") or {}

    print("=" * 70)
    print(f" 轨迹复核：{p.name}")
    print("=" * 70)
    print(f" 生成时间：{data.get('generated_at')}")
    print(f" 耗时    ：{data.get('elapsed_sec')}s")
    print(f" 口径    ：{data.get('_口径')}")
    print(f" has_real_model：{data.get('_has_real_model')}")
    print(f"   ↳ {data.get('_注意_has_real_model')}")
    print()
    print(" 事件计数（summary.by_event，**框架 manager 真实调用**）：")
    for k in sorted(by_event):
        print(f"   {k:24} {by_event[k]:4}")
    print()
    print(" 四项验收（checks）：")
    all_ok = True
    for k, v in checks.items():
        mark = "✅" if v else "❌"
        if not v:
            all_ok = False
        print(f"   {mark} {k}")
    print()
    print(" required 细节：")
    for k in ("create_task", "claim_task", "member_complete_task", "send_message", "hitl_verify"):
        if k in required:
            print(f"   {k:24} {required[k]:4}")
    print()
    print(" ⚠️ 不要用 `grep claim_task` 数次数 —— 工具名会出现在主理的提示语里，")
    print("    那种数法会严重高估（实测 grep 得 10，真值 0）。以上面的数字为准。")
    print("=" * 70)
    if all_ok:
        print(" 结论：四项验收全部通过。")
        return 0
    print(" 结论：有未通过项（这是当前真实水平，不修饰）。")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="用本地桩把 openJiuwen 编排层真跑一遍")
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--external-stub", action="store_true", help="复用已在跑的桩")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--out-dir", default="runtime")
    ap.add_argument("--verify", metavar="JSON",
                    help="只读复核一份已有轨迹（不跑模型），打印 summary/checks")
    # ---- R11 诊断开关（默认值与 R10 完全一致，不改变默认行为）----
    ap.add_argument("--members", type=int, default=0, metavar="N",
                    help="只保留前 N 个预定义成员（0=全部）。"
                         "用于判定成员侧卡死是否由多成员并发初始化引起。")
    ap.add_argument("--dispatch-mode", default="autonomous",
                    choices=["autonomous", "scheduled"],
                    help="框架派发模式。scheduled 由 scheduler 逐个起成员，"
                         "是另一条唤醒链（不依赖 assignee 与 member_name 字符串相等）。")
    args = ap.parse_args(argv)

    if args.verify:
        return verify_trace(args.verify)

    port = args.port
    print("=" * 74)
    print("法元 · Faron —— 用本地桩驱动 openJiuwen 编排层")
    print("=" * 74)
    print(f"{STUB_NOTE}")
    print()

    # ① 桩
    if args.external_stub:
        print(f"  桩：复用外部 {port}（未自起）")
    else:
        if not _port_free(port):
            print(f"{NG} 端口 {port} 已被占用；换 --port 或用 --external-stub")
            return 2
        _start_stub(port)
        print(f"  {OK} 桩已启动：http://127.0.0.1:{port}/v1")

    # ② 环境注入（模型端点完全可注入，见 config.py）
    # ⚠️ 先修代理环境变量：否则 httpx2 会在构造客户端时就崩（见 _sanitize_proxy_env）
    fixed = _sanitize_proxy_env()
    if fixed:
        print(f"  {OK} 已修正代理变量 {fixed}（去掉方括号 IPv6，否则 httpx2 报 InvalidURL）")
    os.environ["FARON_LLM_API_BASE"] = f"http://127.0.0.1:{port}/v1"
    os.environ["FARON_LLM_API_KEY"] = "sk-stub-local"      # 非 sk-placeholder → has_model=True
    os.environ["FARON_LLM_PROVIDER"] = "openai"
    os.environ.setdefault("FARON_LLM_MODEL_STRONG", "faron-stub-strong")
    os.environ.setdefault("FARON_LLM_MODEL_FAST", "faron-stub-fast")
    # 用**专用工作区**，避免框架 bootstrap 写文件时与 runtime/ 里的取证物抢 Windows 文件锁
    ws = (_HERE / "runtime" / "stub-workspace").resolve()
    ws.mkdir(parents=True, exist_ok=True)
    # ── R11-B 关键修复：预置工作区已初始化标记 ────────────────────────
    #
    # `DeepAgent.init_workspace()` 的第一句是：
    #     if (root / ".workspace").exists(): return
    #     ... await DirectoryBuilder(...).build(directories)
    #
    # 实测（R11-B 探针 INIT_PROBE）：主理 k2→k3 通过，**5 个成员全部卡在 k2 之后**，
    # 也就是卡在 `DirectoryBuilder.build()` 里（6 个 agent 对**同一个**工作区根
    # 反复建目录/写模板文件，Windows 文件锁争用）。
    #
    # 而框架自己**从不创建这个顶层标记**（只给各子目录建 `.workspace`），
    # 所以那个 `exists()` 短路永远不会命中 —— 每个 agent 都重跑一次 build。
    #
    # 预置这个标记后，所有 agent 在 `exists()` 处直接返回，build 只跑 0 次。
    # 这不是绕过检查：框架把这个文件当作"工作区已初始化"的正式约定
    # （子目录用的就是同一套约定，内容为 1 字节）。
    marker = ws / ".workspace"
    if not marker.exists():
        marker.write_text("1", encoding="utf-8")
        print(f"  {OK} 预置工作区标记 {marker.name}（否则 6 个 agent 会重复跑 DirectoryBuilder → 卡死）")
    os.environ["FARON_WORKSPACE"] = str(ws)
    # R11 诊断开关：显式打印，避免"以为加了参数其实没生效"
    os.environ["FARON_DISPATCH_MODE"] = args.dispatch_mode
    if args.members > 0:
        os.environ["FARON_MAX_MEMBERS"] = str(args.members)
    else:
        os.environ.pop("FARON_MAX_MEMBERS", None)
    print(f"  诊断开关：成员上限 = {args.members or '全部（默认）'}；"
          f"派发模式 = {args.dispatch_mode}（默认 autonomous）")

    from faron_agentgroup import FaronAgentGroup
    from faron_agentgroup import config as cfg

    conf = cfg.load_config_from_env()
    print(f"  实际生效：dispatch_mode = {conf.dispatch_mode}，"
          f"max_members = {conf.max_members}（0=全部）")
    print(f"  has_model = {conf.has_model}（桩让它为 True，**但这不是真模型**）")
    for e in conf.endpoints:
        print(f"    [{e.tier:6}] {e.model_name:20} @ {e.api_base_url}")

    # ③ 装配 + 打点
    group = FaronAgentGroup(conf)
    print(f"  工具注册：{group.tool_registration['ok']}/{group.tool_registration['total']}  ok")

    rec = Recorder()
    mounted = rec.patch()
    print(f"  框架打点：{len(mounted)} 处 —— {', '.join(mounted) if mounted else '（无）'}")
    print()
    print("-" * 74)
    print("开始执行委托（驱动真实 TeamAgent 流）")
    print("-" * 74)

    t0 = time.time()
    diag: dict[str, Any] = {}
    try:
        code, chunks, run_err, diag = asyncio.run(_drive(group, args.timeout, rec))
    finally:
        rec.unpatch()
    elapsed = time.time() - t0

    print(f"  流式分片：{len(chunks)}    耗时：{elapsed:.1f}s    exit={code}")
    print(f"  桩收到请求：{STUB_STATS['requests']} 次   路径样本：{STUB_STATS['paths'][:5]}")
    acts = STUB_STATS.get("actions") or []
    print(f"  桩依次返回的动作：{acts}")
    if STUB_STATS["errors"]:
        print(f"  {NG} 桩侧路径错误：{STUB_STATS['errors'][:5]}")
    if run_err:
        print(f"  {NG} 运行错误：{run_err}")

    # ④ 轨迹
    sm = rec.summary()
    req = sm["required"]
    checks = [
        ("主理建单 create_task ≥1", req["create_task"] >= 1),
        ("成员领活 claim_task ≥1", req["claim_task"] >= 1),
        ("成员交付 member_complete_task ≥1", req["member_complete_task"] >= 1),
        ("成员消息 send_message ≥1", req["send_message"] >= 1),
    ]
    print()
    print("=" * 74)
    print("协同事件（框架执行侧实测）")
    print("=" * 74)
    for e in rec.events:
        mark = NG if e.get("error") else OK
        print(f"  {mark} #{e['seq']:02d} {e['t_ms']:>7}ms  {e['event']}")
    print()
    # 框架任务板 / 成员的实测状态（不是从我的记录推的，是直接问框架）
    if diag:
        print("  任务板（直接读框架 manager）：")
        for t in diag.get("tasks") or []:
            print(f"    · {t.get('task_id')}  status={t.get('status')}  assignee={t.get('assignee')}")
        if not diag.get("tasks"):
            print(f"    （空）{diag.get('tasks_error', '')}")
        if diag.get("members"):
            print("  成员状态：")
            for m in diag["members"]:
                print(f"    · {m.get('name')}  status={m.get('status')}")
        print()
    for label, ok in checks:
        print(f"  {OK if ok else NG} {label}")
    print(f"  提示 HITL（hitl_verify）计数：{req['hitl_verify']}")

    # ⑤ 落盘
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (_HERE / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"coordination_{ts}.json"

    payload = {
        # ---- 头部口径（不得删改）----
        "_口径": STUB_NOTE,
        "_本轨迹证明": "openJiuwen TeamAgent 的任务板 / 成员消息 / HITL 闸门真实流转",
        "_本轨迹不证明": "模型能力。推理来自本地确定性桩，不能替代真实模型 Key",
        "_has_real_model": conf.has_model,
        "_注意_has_real_model": (
            "此值为 True 仅因注入了非占位的桩 Key；"
            "它**不表示**已接入真实模型。材料中不得据此声称已接入真实模型。"
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 1),
        "stub": {
            "note": STUB_NOTE,
            "api_base": os.environ["FARON_LLM_API_BASE"],
            "models": [conf.endpoints[0].model_name] if conf.endpoints else [],
        },
        "commission": COMMISSION,
        "team": {
            "tools_registered": group.tool_registration,
            "enable_hitt": getattr(group.spec, "enable_hitt", None),
            "describe": _brief(group.describe()),
        },
        "summary": sm,
        "checks": {label: ok for label, ok in checks},
        "events": rec.events,
        "stream_chunks": len(chunks),
        "stream_tail": (chunks[-3:] if chunks else []),
        "exit": code,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"  轨迹已写出：{out_path.relative_to(_HERE)}")

    all_ok = all(ok for _, ok in checks) and code == 0
    print()
    print("=" * 74)
    print(f"结论：{'全部通过' if all_ok else '未全部通过'}")
    print("=" * 74)
    if all_ok:
        print("  编排层已真实跑通（任务板 / 成员消息真实流转）。")
        print("  模型为本地确定性桩 —— 不代表模型能力，也不替代真实 Key。")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
