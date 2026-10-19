#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地确定性 LLM 桩（OpenAI 兼容）—— 让 openJiuwen TeamAgent **真的跑起来**。

════════════════════════════════════════════════════════════════════════
⚠️ 这个桩是什么、不是什么（读完再用，边界比功能重要）
════════════════════════════════════════════════════════════════════════

**这是**：「编排跑通了」的证据 —— 框架的任务板、成员消息、HITL 闸门
         在这条链路上**真实流转**，任何人本地一条命令都能复现。

**这不是**：「真模型跑通了」的证据 —— 这里没有模型能力，也没有生成质量。
         它**不能替代** `run_online.py` 需要的真 Key，
         也**不能**用来说「已接入真实模型」。

对外表述必须是这一句（三处材料都这么写）：

    模型为本地确定性桩（stub），框架任务板与成员消息为真实流转。

════════════════════════════════════════════════════════════════════════
设计要点
════════════════════════════════════════════════════════════════════════

1. **零三方依赖**：只用标准库 `http.server`，不需要 flask/fastapi。
2. **确定性**：同输入 → 同输出。**不用随机数、不读时钟做决策**。
   唯一的"状态"从**请求自身**推导（消息条数 / 已有工具调用），
   因此服务端是无状态的 —— 重启、并发都不会改变行为。
3. **角色判定靠工具表**：openJiuwen 会把该角色的可用工具放进请求的 `tools`。
   - `tools` 里有 `create_task` → 这是 **leader**（主理，负责建单/分派/汇总）
   - `tools` 里有 `claim_task`  → 这是 **member**（成员，负责领活/交付）
   这样不需要猜 agent 是谁，也不需要维护会话表。
4. **只实现 `POST /v1/chat/completions`**：这是 OpenAI 兼容端点里唯一被调用的。
   另外提供 `GET /v1/models` 与 `GET /health` 便于探活。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# ---------------------------------------------------------------------------
# 控制台编码兜底（中文 Windows 默认 GBK，打印 ✅/❌ 会抛 UnicodeEncodeError）
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 口径常量
# ---------------------------------------------------------------------------

STUB_NOTE = "模型为本地确定性桩（stub），框架任务板与成员消息为真实流转。"

#: 请求计数（供 run_stub_online.py 打印，证明「真的被调用了」）
STATS: dict[str, Any] = {"requests": 0, "paths": [], "errors": []}


# ---------------------------------------------------------------------------
# 请求解析
# ---------------------------------------------------------------------------

def _tool_names(body: dict[str, Any]) -> set[str]:
    """取出本次请求里可用的工具名。"""
    names: set[str] = set()
    for t in body.get("tools") or []:
        fn = (t or {}).get("function") or {}
        n = fn.get("name")
        if isinstance(n, str):
            names.add(n)
    return names


def _assistant_turns(messages: list[dict[str, Any]]) -> int:
    """数一下「本对话里已经发生过多少次 assistant 回合」。

    用它做推进游标而不是服务端计数器：
    客户端每次都把完整历史回传，所以这个数天然反映进度，且**服务端无状态**。
    """
    return sum(1 for m in messages if (m or {}).get("role") == "assistant")


def _already_called(messages: list[dict[str, Any]]) -> set[str]:
    """本对话里已经被调用过的工具名（从 assistant.tool_calls 里收）。"""
    used: set[str] = set()
    for m in messages:
        if (m or {}).get("role") != "assistant":
            continue
        for tc in (m or {}).get("tool_calls") or []:
            fn = (tc or {}).get("function") or {}
            if isinstance(fn.get("name"), str):
                used.add(fn["name"])
    return used


def _call_counts(messages: list[dict[str, Any]]) -> dict[str, int]:
    """本对话里每个工具**被调用了几次**（不是"有没有调用过"）。

    用它做剧本推进游标。相比「assistant 回合数」的好处：
      - 框架偶尔多插一条 assistant 消息（如 `spawn_teammate` 之后）时不会错位；
      - 同一工具在剧本里出现多次（`view_task` / `send_message`）也能正确区分。
    """
    counts: dict[str, int] = {}
    for m in messages:
        if (m or {}).get("role") != "assistant":
            continue
        for tc in (m or {}).get("tool_calls") or []:
            fn = (tc or {}).get("function") or {}
            n = fn.get("name")
            if isinstance(n, str):
                counts[n] = counts.get(n, 0) + 1
    return counts


def _next_step(
    seq: list[tuple[str, dict[str, Any], float]],
    called: dict[str, int],
) -> tuple[int | None, float]:
    """在剧本里找出「下一步该做哪一条」。

    做法：顺序遍历剧本，累计每个工具名在剧本前缀里出现的次数；
    第一个「实际调用次数 < 剧本需要次数」的位置就是下一步。
    这样既能跳过已完成的，也能正确处理同名工具重复出现。

    Returns:
        (索引, 0.0)；剧本全部完成时返回 (None, 0.0)。
    """
    need: dict[str, int] = {}
    for i, (name, _args, _delay) in enumerate(seq):
        need[name] = need.get(name, 0) + 1
        if called.get(name, 0) < need[name]:
            return i, 0.0
    return None, 0.0


# ---------------------------------------------------------------------------
# 剧本
# ---------------------------------------------------------------------------

LANDING_Q = (
    "合资合同中日方出资延迟，是否构成违约？我方能否要求继续履行？"
    "请据本地法库检索结果起草《合同审查意见书》。"
)

TEAM_DESC = (
    "法元·小元文书团队：面向涉外法律文书交付的端到端协作。"
    "目标是把「委托」转成可交付的《合同审查意见书》，引用必须来自本地法库检索结果，"
    "并过两段确定性引用自检。"
)
LEADER_DESC_TXT = "涉外资深合伙人，负责规划、分派与汇总，对最终交付质量负责。"

#: 成员名（与 `config.py` 的 M_* 常量一致；从框架日志核对过）
M_LEADER = "team_leader"
M_RETRIEVER = "law_retriever"
M_DRAFTER = "drafter"
M_REVIEWER = "human_reviewer"
M_AUDITOR = "citation_auditor"

#: 运行层实测里**动态召唤**的检索员（R9 · P0-2）
#:
#: 为什么另起一个，而不是直接用预定义的 `law_retriever`：
#:   `build_team` 会把 `predefined_members` 全部建行并**立即 autostart**，
#:   那一刻看板还是空的 —— 成员首轮 poll 什么都看不到，随即
#:   `finalize_member: pausing`，之后再也叫不醒（R8 坑 5）。
#:
#:   而 `spawn_teammate` **只写库不启动**（`spawn_member` 的 docstring 明说：
#:   "Only persists the member data — does NOT start the member"），
#:   启动发生在 `create_task` 内部的 `_auto_start_members()`，
#:   且源码顺序是**先 add_graph 建单、再 _auto_start_members 启动**。
#:   ⇒ 只要「先 spawn、再 create_task」，成员的首轮 poll 就一定能看到任务。
#:
#:   实测源码位置：`agent_teams/tools/tool_task.py` TaskCreateTool.invoke
#:
#: ⚠️ 名字只能用 `[a-z][a-z0-9-]*`（**下划线非法**，实测被
#:    `_validate_member_name` 拒掉）。踩过：`law_retriever_r9` 直接被判无效，
#:    连带 `create_task` 的 assignee 校验也失败 —— 两个工具都"执行了但没落地"。
M_RETRIEVER_NEW = "law-retriever-r9"


#: 建单前先等成员把订阅挂上
#:
#: 为什么必须等（这是本轮最关键的时序发现）：
#:   `TaskBoardHandler._TEAMMATE_NUDGE_EVENTS = {TASK_CREATED, TASK_UNBLOCKED, TASK_RELEASED}`
#:   —— 空闲成员**只**被这三类事件唤醒。
#:   而 `_publish_task_created()` 把 `TASK_CREATED` 发到
#:   `TeamTopic.TASK.build(session_id, team_name)`；`InProcessMessager` **不补发历史事件**。
#:   实测时序：主理 5.4s 就 `create_task`，成员 8s 才 `coordination starting` 订阅 ——
#:   **事件在订阅之前就发出去了，成员永远收不到，于是静默等到超时。**
#:
#:   真实模型每轮几秒，通常自然错开；桩是毫秒级，必须显式等。
BUILD_TEAM_SETTLE_SECONDS = 14.0

#: 主理写完后进入「盯着看板」的轮询阶段；每轮等待秒数
LEADER_POLL_SECONDS = 6.0
#: 主理最多盯多少轮
LEADER_MAX_POLLS = 24


def _leader_script(called: dict[str, int]) -> tuple[dict[str, Any] | None, float]:
    """主理的行动序列（按"每个工具已调用几次"推进）。

    顺序依据框架规定：**`build_team` 之前不能调用任何其他团队工具**，
    且「创建任务前必须先 `view_task` 查看看板」。

    `called` 是「本对话里每个工具已调用几次」（见 `_call_counts`）。
    用调用次数而不是 assistant 回合数推进，理由见下方 `_next_step` 那段说明。

    返回 `(action, delay_seconds)`；`action` 为 None 表示本回合给最终文字答复。
    """
    seq: list[tuple[str, dict[str, Any], float]] = [
        (
            "build_team",
            {
                "display_name": "法元·小元文书团队",
                "team_desc": TEAM_DESC,
                "leader_display_name": "小元·主理",
                "leader_desc": LEADER_DESC_TXT,
                "enable_hitt": True,
            },
            0.0,
        ),
        # ⚠️ 这两步的延时是**必须的**，别删：等 5 个成员把事件订阅挂上。
        #    否则 `create_task` 发出的 TASK_CREATED 会落在订阅之前，
        #    成员永远收不到唤醒事件（InProcessMessager 不补发历史）。
        ("view_task", {"action": "list"}, BUILD_TEAM_SETTLE_SECONDS),
        ("view_task", {"action": "list"}, 0.0),
        # ── R9 · P0-2 关键时序：**先建单、后召唤** ──
        #    实测（12:45:51 那次）：`spawn_teammate` **本身**就会经由
        #    `on_teammate_created` → `spawning teammate` **立即启动**成员，
        #    并不等 `create_task` 的 `_auto_start_members()`。
        #    所以「先 spawn 后建单」会让成员早 55ms 醒来，仍然看不到任务。
        #
        #    反过来「先建单（**不指派**）后召唤」才对：成员首轮
        #    `on_initial_task_poll` 会看到一条 `status=pending` 且无 assignee 的任务，
        #    正是自主认领模式里「可被自主认领」的那种，于是 view_task → claim_task。
        #    指派放在后面用 `update_task` 补（这次实测 assignee 能正确落库）。
        (
            "create_task",
            {
                "tasks": [
                    {
                        "task_id": "task-1",
                        "title": "检索中日合资合同相关法条并溯源",
                        "content": (
                            "目标：锁定「股东出资义务 / 迟延履行 / 继续履行请求权」三条主线"
                            "在本地的可引用条文。\n"
                            "验收标准：每条引用都能给出来源法规与条文号，"
                            "且来自本地法库检索结果（不得臆造）。"
                        ),
                    },
                    {
                        "task_id": "task-2",
                        "title": "起草《合同审查意见书》",
                        "assignee": M_DRAFTER,
                        "content": (
                            "目标：产出可直接交付的《合同审查意见书》，含"
                            "①出资迟延是否违约、能否请求继续履行；②准据法与管辖约定效力；"
                            "③风险条款与修改建议。\n"
                            "约束：引用条文必须来自 task-1 的检索结果。"
                        ),
                        "depends_on": ["task-1"],
                    },
                ]
            },
            0.0,
        ),
        ("view_task", {"action": "list"}, 0.0),
        # ── 建单完成后再召唤成员：它的首轮 poll 就能看到任务 ──
        (
            "spawn_teammate",
            {
                "member_name": M_RETRIEVER_NEW,
                "display_name": "检索员·民商",
                "desc": "在内置日美法库中检索真实法条并回传溯源信息。",
                "model_name": "faron-stub-fast",
            },
            0.0,
        ),
        # ⚠️ 定向指派：`create_task.assignee` 实测会丢（库里 assignee=None），
        #    补一次 `update_task` 显式指派；这次实测 assignee 能正确落库。
        (
            "update_task",
            {"task_id": "task-1", "assignee": M_RETRIEVER_NEW,
             "title": "检索中日合资合同相关法条并溯源（指派检索员）"},
            0.0,
        ),
        (
            "send_message",
            {
                "to": "*",
                "content": (
                    "两张单已建好：task-1 检索溯源、task-2 起草意见书（依赖 task-1）。"
                    "请检索员先认领 task-1。"
                ),
            },
            0.0,
        ),
        # ⚠️ **定向**消息，不是广播。
        #    实测：广播（to="*"）只落库、不唤醒；框架在 `build_team` 之后会
        #    `finalize_member: pausing team member ...; marking READY for next assignment`
        #    —— 成员进入 paused，必须收到**指向自己**的消息才会被
        #    `MessageHandler` 走 `deliver_input` 拉起一轮。
        (
            "send_message",
            {
                "to": M_RETRIEVER_NEW,
                "content": (
                    "检索员请开工：task-1（检索中日合资合同相关法条并溯源）已指派给你，"
                    "用 view_task 看详情，claim_task 认领，做完 member_complete_task 交付。"
                ),
            },
            0.0,
        ),
        (
            "send_message",
            {
                "to": M_DRAFTER,
                "content": (
                    "起草员请待命：task-2（起草《合同审查意见书》）依赖 task-1，"
                    "task-1 交付后你会收到通知，届时 view_task → claim_task → 交付。"
                ),
            },
            0.0,
        ),
    ]

    # 推进游标：按「某个工具已经被调用过几次」判断，而不是按 assistant 回合数。
    #
    # ⚠️ 为什么不能用回合数（R9 实测踩到的真 bug）：
    #    `spawn_teammate` 之后框架会**多插一条 assistant 消息**，
    #    于是回合数一步跳 2，游标直接越过 `create_task` ——
    #    现象是「剧本里明明有 create_task，日志里却没执行」，
    #    而且看起来像"create_task 回归失败了"，极难归因。
    #    按调用次数比对则天然免疫：多插几条 assistant 都不影响。
    idx, default_delay = _next_step(seq, called)
    if idx is not None:
        name, args, delay = seq[idx]
        return ({"name": name, "arguments": json.dumps(args, ensure_ascii=False)}, delay)

    # 剧本走完了：盯看板（带延时，给成员留出作业窗口）
    scripted_views = sum(1 for n, _, _ in seq if n == "view_task")
    polls = called.get("view_task", 0) - scripted_views
    if polls < LEADER_MAX_POLLS:
        return ({"name": "view_task", "arguments": json.dumps({"action": "list"})},
                LEADER_POLL_SECONDS)
    return (None, 0.0)


LEADER_FINAL = (
    "已交付《合同审查意见书》要点：\n"
    "① 日方出资延迟构成违约（出资义务属主给付义务，不因迟延而消灭）；\n"
    "② 我方有权要求继续履行并主张迟延损害赔偿；\n"
    "③ 准据法与管辖依合同约定，未约定的按最密切联系原则确定；\n"
    "④ 风险与修改建议见随文清单。\n"
    "引用条文均取自本地法库检索结果，已过两段确定性自检。"
)

MEMBER_FINAL = "本单已完成，结果已交回主理。"
REVIEWER_FINAL = "已复核：两段自检结论一致，引用与出处核对无误，通过。"


def _reviewer_script(called: dict[str, int]) -> tuple[dict[str, Any] | None, float]:
    """人类复核员（HITL 闸门）的行动序列：看复审队列 → 通过。

    `called` 是「本对话里每个工具已调用几次」，见 `_call_counts` / `_next_step`
    —— 用次数推进而不是回合数，理由见 `_leader_script` 里的说明。
    """
    seq: list[tuple[str, dict[str, Any], float]] = [
        ("view_task", {"action": "in_review"}, 0.0),
        ("verify_task", {"task_id": "task-1", "decision": "approve",
                         "feedback": "两段自检结论一致，引用与出处核对无误，通过。"}, 0.0),
        ("send_message", {"to": "*", "content": "task-1 已复核通过。"}, 0.0),
    ]
    idx, _ = _next_step(seq, called)
    if idx is not None:
        name, args, delay = seq[idx]
        return ({"name": name, "arguments": json.dumps(args, ensure_ascii=False)}, delay)
    return (None, 0.0)


def _member_script(called: dict[str, int]) -> tuple[dict[str, Any] | None, float]:
    """成员的行动序列：查可领 → 领活 → 交付 → 汇报。"""
    seq: list[tuple[str, dict[str, Any], float]] = [
        ("view_task", {"action": "claimable"}, 0.0),
        # ⚠️ claim_task 必须同时给 task_id 与 status（实测框架 schema 要求）
        ("claim_task", {"task_id": "task-1", "status": "claimed"}, 0.0),
        (
            "member_complete_task",
            {
                "task_id": "task-1",
                "note": (
                    "检索完成：本地法库命中《中外合资经营企业法》出资义务相关条款与"
                    "《民法典》合同编迟延履行规则；条号与出处已登记，供起草员 task-2 引用。"
                ),
            },
            0.0,
        ),
        (
            "send_message",
            {
                "to": "*",
                "content": "task-1 已交付：条文命中与出处已登记，task-2 可以开工。",
            },
            0.0,
        ),
    ]
    idx, _ = _next_step(seq, called)
    if idx is not None:
        name, args, delay = seq[idx]
        return ({"name": name, "arguments": json.dumps(args, ensure_ascii=False)}, delay)
    return (None, 0.0)


def _pick_action(body: dict[str, Any]) -> tuple[dict[str, Any] | None, float]:
    """根据「请求里有哪些工具」判定角色，再按其剧本给出下一步动作。"""
    tools = _tool_names(body)
    messages = body.get("messages") or []
    called = _call_counts(messages)

    # 角色判定顺序有讲究：
    #   主理 = 能建队/建单；复核员 = 有 verify_task 但**没有** create_task；
    #   成员 = 能领活/交付。
    if "build_team" in tools or "create_task" in tools:
        return _leader_script(called)
    if "verify_task" in tools:
        return _reviewer_script(called)
    if "claim_task" in tools or "member_complete_task" in tools:
        return _member_script(called)
    return (None, 0.0)


def _text_for(body: dict[str, Any]) -> str:
    tools = _tool_names(body)
    if "build_team" in tools or "create_task" in tools:
        return LEADER_FINAL
    if "verify_task" in tools:
        return REVIEWER_FINAL
    if "claim_task" in tools or "member_complete_task" in tools:
        return MEMBER_FINAL
    return "已复核：两段自检结论一致，可以放行。"


# ---------------------------------------------------------------------------
# HTTP 处理
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    server_version = "FaronStubLLM/1.0"

    # 关掉默认的逐请求访问日志（噪音；需要时用 --verbose）
    verbose = False

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if self.verbose:
            super().log_message(fmt, *args)

    # ---- 公共响应工具 ----

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _openai_error(self, code: int, msg: str) -> None:
        self._send(code, {"error": {"message": msg, "type": "invalid_request_error"}})

    # ---- 路由 ----

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/health", "/v1/health"):
            self._send(200, {"ok": True, "stub": True, "note": STUB_NOTE})
            return
        if path in ("/v1/models", "/models"):
            self._send(200, {
                "object": "list",
                "data": [
                    {"id": "faron-stub-strong", "object": "model", "owned_by": "local"},
                    {"id": "faron-stub-fast", "object": "model", "owned_by": "local"},
                ],
            })
            return
        self._openai_error(404, f"unknown path: {self.path}")

    # ---- SSE 流式响应 ----
    #
    # ⚠️ **必须支持流式**：openjiuwen 的模型客户端发请求时带 `"is_stream": true`，
    # 期望收到 `text/event-stream`（`data: {...}` 行 + 结尾 `data: [DONE]`）。
    # 若这里返回普通 JSON，框架的 SSE 解析器什么也拿不到，日志会显示
    #     [LLM] <<< response: content_len=0, tool_call_count=0
    # 于是 ReAct 循环**直接空闲退出**，看起来像"卡住"。
    # （本轮实测踩过：只返回 JSON 时整个 run 静默超时。）

    def _sse_open(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _sse_send(self, obj: dict[str, Any]) -> None:
        self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _stream_response(self, model: str, message: dict[str, Any], finish: str) -> None:
        base = {
            "id": "chatcmpl-stub",
            "object": "chat.completion.chunk",
            "created": 0,           # 固定值：确定性优先于真实性
            "model": model,
        }
        tool_calls = message.get("tool_calls")
        content = message.get("content")

        if tool_calls:
            # 工具调用分块：先给 role，再一次性给完整 tool_calls
            self._sse_send({**base, "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": None}, "finish_reason": None},
            ]})
            self._sse_send({**base, "choices": [
                {"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None},
            ]})
        else:
            self._sse_send({**base, "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": content or ""},
                 "finish_reason": None},
            ]})

        self._sse_send({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
        self._sse_send({"stub": {"stub": True, "note": STUB_NOTE}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        STATS["requests"] += 1
        if len(STATS["paths"]) < 50:
            STATS["paths"].append(path)
        if path not in ("/v1/chat/completions", "/chat/completions"):
            STATS["errors"].append(f"404 {path}")
            self._openai_error(404, f"unknown path: {self.path}")
            return

        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception as exc:  # noqa: BLE001
            self._openai_error(400, f"bad json: {exc}")
            return

        model = body.get("model") or "faron-stub"
        action, delay = _pick_action(body)
        message: dict[str, Any] = {"role": "assistant", "content": None}

        if action is not None:
            message["content"] = None
            message["tool_calls"] = [{
                "id": f"call_stub_{abs(hash((action['name'], action['arguments']))) % 10**12}",
                "type": "function",
                "function": {"name": action["name"], "arguments": action["arguments"]},
            }]
            finish = "tool_calls"
        else:
            message["content"] = _text_for(body)
            finish = "stop"

        STATS.setdefault("actions", []).append(
            message.get("tool_calls", [{}])[0].get("function", {}).get("name", "text")
        )

        # 主理轮询看板时故意等一会儿：这是给子成员留出被唤醒并作业的窗口。
        # 真实模型每轮也要几秒；桩是毫秒级，不补延时成员就抢不到执行机会。
        if delay > 0:
            time.sleep(delay)

        # 流式请求走 SSE；非流式仍返回普通 JSON（两种都支持）
        if body.get("stream"):
            self._sse_open()
            self._stream_response(model, message, finish)
            return

        self._send(200, {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,               # 固定值：确定性优先于真实性
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "stub": {"stub": True, "note": STUB_NOTE},
        })


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def serve(port: int, *, once: bool = False, verbose: bool = False) -> None:
    _Handler.verbose = verbose
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    srv.daemon_threads = True
    print(f"[stub] listening on http://127.0.0.1:{port}/v1  (chat/completions)", flush=True)
    print(f"[stub] {STUB_NOTE}", flush=True)
    try:
        if once:
            # --once：只服务一个连接就退（便于 CI / 单次验证）
            srv.handle_request()
        else:
            srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        print("[stub] stopped", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="本地确定性 OpenAI 兼容 LLM 桩")
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--once", action="store_true", help="服务一个请求后退出")
    ap.add_argument("--verbose", action="store_true", help="打印访问日志")
    ap.add_argument("--selftest", action="store_true", help="不监听端口，只自检剧本逻辑")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    serve(args.port, once=args.once, verbose=args.verbose)
    return 0


def _walk_script(body: dict[str, Any], limit: int = 40) -> list[str]:
    """把一个剧本从头到尾空走一遍，返回依次会调用的工具名列表。

    这是自检的核心手法：不猜「第 N 步应该是什么」，而是**真的模拟框架的推进方式**
    —— 每次拿到一个动作，就把它当作 assistant.tool_calls 追加进历史，再问下一步。
    这样能一次性发现剧本里的死循环、跳步、以及 `_next_step` 的推进错误。
    """
    cur = json.loads(json.dumps(body))
    out: list[str] = []
    for i in range(limit):
        action, _delay = _pick_action(cur)
        if action is None:
            out.append("(text)")
            break
        name = action["name"]
        out.append(name)
        cur["messages"].append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"w{i}", "type": "function",
                            "function": {"name": name, "arguments": action["arguments"]}}],
        })
    return out


def _selftest() -> int:
    """不依赖网络的自检：验证确定性、角色判定、剧本推进。"""
    leader_body = {
        "model": "m",
        "messages": [{"role": "system", "content": "你是主理"},
                     {"role": "user", "content": LANDING_Q}],
        "tools": [{"type": "function", "function": {"name": "build_team"}},
                  {"type": "function", "function": {"name": "create_task"}},
                  {"type": "function", "function": {"name": "spawn_teammate"}},
                  {"type": "function", "function": {"name": "send_message"}}],
    }
    member_body = {
        "model": "m",
        "messages": [{"role": "user", "content": "领活"}],
        "tools": [{"type": "function", "function": {"name": "claim_task"}},
                  {"type": "function", "function": {"name": "member_complete_task"}}],
    }
    reviewer_body = {
        "model": "m",
        "messages": [{"role": "user", "content": "复核"}],
        "tools": [{"type": "function", "function": {"name": "view_task"}},
                  {"type": "function", "function": {"name": "verify_task"}}],
    }

    a1, _ = _pick_action(leader_body)
    a2, _ = _pick_action(json.loads(json.dumps(leader_body)))
    ok_rows: list[tuple[bool, str]] = []
    ok_rows.append((a1 == a2, "同输入同输出（确定性）"))
    ok_rows.append((a1 is not None and a1["name"] == "build_team", "主理第一步 = build_team"))

    m1, _ = _pick_action(member_body)
    ok_rows.append((m1 is not None and m1["name"] == "view_task", "成员第一步 = view_task"))

    # 主理剧本必须包含全部关键动作，且 spawn_teammate 必须在 create_task 之前
    # （这是 R9 P0-2 的时序要求：先召唤、后建单，成员首轮才能看到任务）
    lead_seq = _walk_script(leader_body)
    for need in ("build_team", "spawn_teammate", "create_task", "send_message", "view_task"):
        ok_rows.append((need in lead_seq, f"主理剧本含 {need}"))
    ok_rows.append((
        "create_task" in lead_seq and "spawn_teammate" in lead_seq
        and lead_seq.index("create_task") < lead_seq.index("spawn_teammate"),
        f"create_task 在 spawn_teammate 之前（{lead_seq[:7]}…）",
    ))
    ok_rows.append((lead_seq.count("create_task") == 1,
                    f"create_task 只出现一次（实际 {lead_seq.count('create_task')} 次）"))

    # 成员剧本必须真的领活并交付（R9 P0-2 的验收目标）
    mem_seq = _walk_script(member_body)
    ok_rows.append(("claim_task" in mem_seq, f"成员剧本含 claim_task（{mem_seq}）"))
    ok_rows.append(("member_complete_task" in mem_seq,
                    f"成员剧本含 member_complete_task（{mem_seq}）"))
    ok_rows.append((
        "claim_task" in mem_seq and "member_complete_task" in mem_seq
        and mem_seq.index("claim_task") < mem_seq.index("member_complete_task"),
        "成员先 claim 后 complete",
    ))

    # 复核员走 verify_task（HITL）
    rev_seq = _walk_script(reviewer_body)
    ok_rows.append(("verify_task" in rev_seq, f"复核员剧本含 verify_task（{rev_seq}）"))

    # 主理写完后应进入「盯看板」并带延时（给成员留窗口）
    #
    # 构造方式：把**剧本部分**走完（遇到带延时的动作说明已进入盯看板阶段，停），
    # 再问下一步 —— 这正好对应真实运行时"剧本结束、活还在成员手里"的那一刻。
    late = json.loads(json.dumps(leader_body))
    for i in range(40):
        action, delay = _pick_action(late)
        # 剧本里的延时只有 0.0 与 BUILD_TEAM_SETTLE_SECONDS；
        # 出现 LEADER_POLL_SECONDS 就说明已经进入盯看板阶段，停在这里正好。
        if action is None or delay == LEADER_POLL_SECONDS:
            break
        late["messages"].append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"s{i}", "type": "function",
                            "function": {"name": action["name"],
                                         "arguments": action["arguments"]}}],
        })
    a4, d4 = _pick_action(late)
    ok_rows.append((a4 is not None and a4["name"] == "view_task" and d4 > 0,
                    f"剧本走完后进入盯看板且带延时（action={a4 and a4['name']}, delay={d4}s）"))

    # 盯够 LEADER_MAX_POLLS 轮后应收尾（给最终文字答复，不再无限轮询）
    for i in range(LEADER_MAX_POLLS + 2):
        late["messages"].append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"p{i}", "type": "function",
                            "function": {"name": "view_task", "arguments": "{}"}}],
        })
    a5, _ = _pick_action(late)
    ok_rows.append((a5 is None, f"盯满 {LEADER_MAX_POLLS} 轮后收尾（得到 {a5 and a5['name']}）"))

    print("=" * 66)
    print("stub LLM 自检（不监听端口）")
    print("=" * 66)
    bad = 0
    for ok, label in ok_rows:
        print(f"  {OK if ok else NG} {label}")
        if not ok:
            bad += 1
    print("=" * 66)
    print(f"结果：{len(ok_rows) - bad} 通过 / {bad} 失败 / 共 {len(ok_rows)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
