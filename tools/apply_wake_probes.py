#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 openJiuwen 框架打「唤醒链探针」——**只加日志，不改行为**（R10 · T9）。

═══════════════════════════════════════════════════════════════════════════
为什么要有这个脚本，而不是手改 site-packages
───────────────────────────────────────────────────────────────────────────
* **可复现**：同伴在自己的机器上一条命令就能打上，不用对着文档抄代码。
* **可撤销**：`--revert` 精确还原，不会在 site-packages 里留下说不清的改动。
* **可对抗环境漂移**：先 `--dry-run` 看锚点是否仍在，锚点变了会明确报错，
  而不是静默改错地方。
* **纪律 D1**：探针只 `team_logger.info(...)`，不碰任何分支与返回值。

═══════════════════════════════════════════════════════════════════════════
要回答的三个问题（R10 工单 §1）
───────────────────────────────────────────────────────────────────────────
探针 A（最高嫌疑）——`task_board.py` 的 teammate 分支里，`board_tasks` 可能是空的。
    代码里那一步是**静默 return，一行日志都没有**：
        board_tasks = [t for t in incomplete
                       if (t.status == "pending" and not t.assignee)
                       or t.assignee == member_name]
        if not board_tasks:
            return            # ← 七轮的盲点
    若 `assignee` 字符串与 `member_name` 不完全相等（下划线/大小写/前后空格），
    或任务已进 terminal 集合，成员就永远收不到 nudge，**全链路无痕**。

探针 B —— `TeamAgent.deliver_input` 里 `harness is None` 时**无声 return**。
    若成员 runtime 压根没建起来，nudge 会静默丢弃，问题在 configurator 而非协调层。

探针 C —— 不需要改代码：grep 运行日志里的 `error in wake_callback for`。
    handler 抛的异常被 `event_bus._run_loop` 的 `except Exception` 吞掉了。

═══════════════════════════════════════════════════════════════════════════
用法
───────────────────────────────────────────────────────────────────────────
    python tools/apply_wake_probes.py --dry-run     # 只看锚点在不在
    python tools/apply_wake_probes.py --apply       # 打探针
    python tools/apply_wake_probes.py --show        # 打印当前探针状态
    python tools/apply_wake_probes.py --revert      # 还原

打完探针后跑一次 `python run_stub_online.py`，然后：
    python tools/apply_wake_probes.py --grep        # 从日志里捞出探针输出

═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: 探针标记（幂等判定 + grep 用）
MARK_A = "NUDGE_PROBE"
MARK_B = "DELIVER_PROBE"
MARK_C = "INITPOLL_PROBE"
MARK_D = "DISPATCH_PROBE"
MARK_E = "BUS_PROBE"
MARK_F = "_PROBE"
MARK_G = "TH_PROBE"
MARK_H = "NH_PROBE"
MARK_I = "INIT_PROBE"

#: 全部探针标记（--revert 的判据）
MARKS = (
    MARK_A, MARK_B, MARK_C, MARK_D, MARK_E, MARK_F,
    "STEP1_PROBE", "STEP2_PROBE", "STEP3_PROBE", "STEP4_PROBE", "STEP5_PROBE",
    MARK_G, MARK_H, MARK_I,
)

# ---- 探针 A：task_board.py teammate 分支，静默 return 之前 ----
ANCHOR_A = """            if not board_tasks:
                return
            lines = [t("dispatcher.teammate_task_list")]"""

PROBE_A = """            # ── R10 探针 A（只加日志，不改行为）──────────────────────
            try:
                _dbg_incomplete = [
                    (getattr(_t, "task_id", None) or getattr(_t, "id", "?"),
                     _t.status, _t.assignee)
                    for _t in incomplete
                ]
            except Exception as _e:  # noqa: BLE001
                _dbg_incomplete = f"<unprintable: {_e}>"
            team_logger.info(
                "[{}] {} all={} incomplete={} board={} member_name={!r} | {}",
                member_name, \"""" + MARK_A + """\",
                len(all_tasks), len(incomplete), len(board_tasks), member_name,
                _dbg_incomplete,
            )
            # ── 探针 A 结束 ─────────────────────────────────────────
            if not board_tasks:
                return
            lines = [t("dispatcher.teammate_task_list")]"""

# ---- 探针 B：team_agent.py deliver_input 的 harness is None 静默 return ----
ANCHOR_B = """        harness = self.harness
        if harness is None:
            return
        await harness.send(content, immediate=use_steer)"""

PROBE_B = """        harness = self.harness
        if harness is None:
            # ── R10 探针 B（只加日志，不改行为）──
            team_logger.info(
                "[{}] {} DROPPED: harness is None (content len={})",
                self._member_name() or "?", \"""" + MARK_B + """\", len(str(content)),
            )
            # ── 探针 B 结束 ──
            return
        await harness.send(content, immediate=use_steer)"""

# ---- 探针 C：on_initial_task_poll 的两道静默 gate ----
#
# **这一处是 R10 实跑后新发现的、工单里没有的静默返回点。**
#   `on_initial_task_poll` 是成员启动后**唯一**一次主动看板的机会：
#       member_name = self._blueprint.member_name
#       if not member_name or self._infra.task_manager is None:
#           return          # ← 无声，一行日志都没有
#       await self._nudge_idle_agent(member_name)
#   如果 `_blueprint.member_name` 是空串，或该成员的 handler 拿不到 task_manager，
#   那么 nudge 链路**在第一步就断了**，而且和探针 A 一样完全无痕。
ANCHOR_C = """        member_name = self._blueprint.member_name
        if not member_name or self._infra.task_manager is None:
            return
        await self._nudge_idle_agent(member_name)"""

PROBE_C = """        # ── R10 探针 C（只加日志，不改行为）──
        team_logger.info(
            "[{}] {} role={} member_name={!r} task_manager_is_none={}",
            getattr(self._blueprint, "member_name", "?"), \"""" + MARK_C + """\",
            getattr(getattr(self._blueprint, "role", None), "value", "?"),
            getattr(self._blueprint, "member_name", "?"),
            self._infra.task_manager is None,
        )
        # ── 探针 C 结束 ──
        member_name = self._blueprint.member_name
        if not member_name or self._infra.task_manager is None:
            team_logger.info(
                "[{}] {} EARLY-RETURN (member_name falsy={}, task_manager None={})",
                getattr(self._blueprint, "member_name", "?") or "?",
                \"""" + MARK_C + """\",
                not bool(member_name), self._infra.task_manager is None,
            )
            return
        await self._nudge_idle_agent(member_name)"""

# ---- 探针 E：EventBus 是不是被所有成员**共用**了 ----
#
# R10 实跑发现：6 个成员都打了 `[...] coordination starting`，
# 但全文**只有一条** `EventBus[leader] starting`。
# 而 `kernel.start()` 里 `EventBus.start()` 的调用前提是 `not is_running`。
# ⇒ 唯一解释：成员的 bus 在进入 start() 时**已经 is_running=True**。
# 那就只剩一种可能：**所有 agent 共用同一个 EventBus 实例**（那样
# `_wake_callback` 也只有主理那一个，成员的 poll 事件全被投给主理）。
# 探针 E 直接把 `id(bus)` 打出来，一眼就能判。
ANCHOR_E = """        if not self._event_bus.is_running:
            if self._dispatcher is None:
                raise RuntimeError(\"CoordinationKernel.start() requires setup() before start()\")"""

PROBE_E = """        # ── R10 探针 E（只加日志，不改行为）──
        team_logger.info(
            "[{}] {} id={} is_running={} dispatcher_none={} role={}",
            getattr(host, \"member_name\", \"?\") or \"?\",
            \"""" + MARK_E + """\",
            id(self._event_bus),
            self._event_bus.is_running,
            self._dispatcher is None,
            getattr(getattr(host, \"role\", None), \"value\", \"?\"),
        )
        # ── 探针 E 结束 ──
        if not self._event_bus.is_running:
            if self._dispatcher is None:
                raise RuntimeError(\"CoordinationKernel.start() requires setup() before start()\")"""

# ---- 探针 F：kernel.start() 里逐个 await 打点，定位"卡在哪一步" ----
#
# R10 探针 E 证死：`kernel.start()` 只有**主理**走到底（只出现一条 BUS_PROBE），
# 6 个成员打完第 138 行的 `coordination starting` 之后再无任何输出，
# **也没有异常**——所以不是抛错，是**卡在某个 await 上永不返回**。
# 这三个点把 138 → 246 之间的 await 切开，一眼看出阻塞位置。
ANCHOR_F1 = """            await sess_mgr.bind_session(session)
            memory_manager = resources.memory_manager"""

PROBE_F1 = """            await sess_mgr.bind_session(session)
            team_logger.info("[{}] {} after bind_session", member_name, \"STEP1_PROBE\")  # ── 探针 F1 ──
            memory_manager = resources.memory_manager"""

ANCHOR_F2 = """                await resources.harness.start(team_session=session)
                await host.stream_controller.start()"""

PROBE_F2 = """                await resources.harness.start(team_session=session)
                team_logger.info("[{}] {} after harness.start", member_name, \"STEP2_PROBE\")  # ── 探针 F2 ──
                await host.stream_controller.start()
                team_logger.info("[{}] {} after stream_controller.start", member_name, \"STEP3_PROBE\")  # ── 探针 F3 ──"""

ANCHOR_F3 = """        await host.seed_member_registry()
        await host.update_status(MemberStatus.READY)"""

PROBE_F3 = """        await host.seed_member_registry()
        team_logger.info("[{}] {} after seed_member_registry", member_name, \"STEP4_PROBE\")  # ── 探针 F4 ──
        await host.update_status(MemberStatus.READY)
        team_logger.info("[{}] {} after update_status(READY)", member_name, \"STEP5_PROBE\")  # ── 探针 F5 ──"""
# ---- 探针 G：TeamHarness.start() 里 pre_run / native.start 的分界 ----
ANCHOR_G = """        child = self._make_child_session(team_session)
        kv_cache_harness_session_lifecycle_hook.on_harness_session_created(self, child)
        await child.pre_run()
        await self._native.start(session=child)"""

PROBE_G = """        child = self._make_child_session(team_session)
        kv_cache_harness_session_lifecycle_hook.on_harness_session_created(self, child)
        logger.info("[TeamHarness] TH_PROBE before child.pre_run")
        await child.pre_run()
        logger.info("[TeamHarness] TH_PROBE after child.pre_run -> native.start")
        await self._native.start(session=child)
        logger.info("[TeamHarness] TH_PROBE after native.start")"""

# ---- 探针 H：NativeHarness.start() 内部逐步（含 _prepare）----
ANCHOR_H1 = """        self._starting = True
        try:
            await self._prepare()"""

PROBE_H1 = """        self._starting = True
        try:
            logger.info("[NativeHarness] NH_PROBE step0 before _prepare")
            await self._prepare()
            logger.info("[NativeHarness] NH_PROBE step1 after _prepare (past the block!)")"""

ANCHOR_H2 = """            await self._started_event.wait()
            logger.info("[NativeHarness] started session=%s", self.session_id)"""

PROBE_H2 = """            logger.info("[NativeHarness] NH_PROBE step5 waiting _started_event")
            await self._started_event.wait()
            logger.info("[NativeHarness] NH_PROBE step6 _started_event SET")
            logger.info("[NativeHarness] started session=%s", self.session_id)"""
# ---- 探针 I：DeepAgent._ensure_initialized() 内部的 4 个 await ----
#
# R11 实测把死点收到这里：`NativeHarness._prepare()` -> `ensure_initialized()`，
# 主理 1 秒内过、成员无限等。本探针把这 4 个 await 逐一切开。
#
# ⚠️ 头号嫌疑是第 3 个：`_resolve_read_image_multimodal()` ——
#    它就是日志里那条 `[ImageModalityProbe] image modality probed` 的来源，
#    而那条日志**只在主理身上出现过**。它会拿一个 base64 图片去探模型端点，
#    若在成员上下文里等一个永远不会完成的响应，表现就正好是"卡死且无日志"。
ANCHOR_I = """        await self._register_pending_mcps()

        if self._needs_workspace_init():
            await self.init_workspace()

        await self._resolve_read_image_multimodal()

        self._sync_prompt_builder_references()"""

PROBE_I = """        logger.info("[DeepAgent] INIT_PROBE k0 before _register_pending_mcps")
        await self._register_pending_mcps()
        logger.info("[DeepAgent] INIT_PROBE k1 after _register_pending_mcps")

        logger.info("[DeepAgent] INIT_PROBE k2 before init_workspace (needed=%s)", self._needs_workspace_init())
        if self._needs_workspace_init():
            await self.init_workspace()
        logger.info("[DeepAgent] INIT_PROBE k3 after init_workspace")

        logger.info("[DeepAgent] INIT_PROBE k4 before _resolve_read_image_multimodal")
        await self._resolve_read_image_multimodal()
        logger.info("[DeepAgent] INIT_PROBE k5 after _resolve_read_image_multimodal")

        self._sync_prompt_builder_references()"""
# ---- 探针 D：EventBus 派发了哪些事件（含 poll 事件是否真的到达 handler）----
ANCHOR_D = """            try:
                if self._wake_callback:
                    await self._wake_callback(event)
            except Exception:"""

PROBE_D = """            # ── R10 探针 D（只加日志，不改行为）──
            #    看到底有哪些事件被派发。若连 POLL_TASK / INITIAL_POLL_TASK
            #    都不出现，说明轮询根本没在跑，问题在 EventBus/_poll_loop。
            try:
                team_logger.info(
                    "{} DISPATCH event_type={}",
                    \"""" + MARK_D + """\", getattr(event, "event_type", "?"),
                )
            except Exception:  # noqa: BLE001
                pass
            # ── 探针 D 结束 ──
            try:
                if self._wake_callback:
                    await self._wake_callback(event)
            except Exception:"""

PATCHES = [
    ("agent_teams/agent/coordination/handlers/task_board.py", ANCHOR_A, PROBE_A, MARK_A),
    ("agent_teams/agent/team_agent.py", ANCHOR_B, PROBE_B, MARK_B),
    ("agent_teams/agent/coordination/handlers/task_board.py", ANCHOR_C, PROBE_C, MARK_C),
    ("agent_teams/agent/coordination/event_bus.py", ANCHOR_D, PROBE_D, MARK_D),
    ("agent_teams/agent/coordination/kernel.py", ANCHOR_E, PROBE_E, MARK_E),
    ("agent_teams/agent/coordination/kernel.py", ANCHOR_F1, PROBE_F1, "STEP1_PROBE"),
    ("agent_teams/agent/coordination/kernel.py", ANCHOR_F2, PROBE_F2, "STEP2_PROBE"),
    ("agent_teams/agent/coordination/kernel.py", ANCHOR_F3, PROBE_F3, "STEP4_PROBE"),
    ("agent_teams/harness/team_harness.py", ANCHOR_G, PROBE_G, MARK_G),
    ("agent_teams/harness/native_harness.py", ANCHOR_H1, PROBE_H1, MARK_H),
    ("agent_teams/harness/native_harness.py", ANCHOR_H2, PROBE_H2, MARK_H),
    ("harness/deep_agent.py", ANCHOR_I, PROBE_I, MARK_I),
]


def _pkg_root() -> Path:
    import openjiuwen

    return Path(openjiuwen.__file__).resolve().parent


def _read(p: Path) -> str:
    """按**原样**读（newline="" 关掉通用换行转换）。

    ⚠️ R11 踩过的坑：框架源码是 **LF**，而 `Path.read_text()` 会把 CRLF 归一成 LF、
    `Path.write_text()` 在 Windows 上又把 LF 写回 CRLF —— 于是每 apply/revert 一次，
    文件就从 11629 B 变成 11952 B，**哈希永远对不上**，看着像"还原失败"。
    所以这里一律用 `newline=""`，不碰行尾。
    """
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(p: Path, text: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _nl(text: str) -> str:
    """目标文件实际用的换行符。"""
    return "\r\n" if "\r\n" in text else "\n"


def _fit(block: str, text: str) -> str:
    """把（以 \\n 写成的）锚点/探针块调成目标文件的行尾，再拿去比。"""
    return block.replace("\n", _nl(text))


def _status() -> list[tuple[Path, bool, bool]]:
    """返回 [(路径, 有探针, 锚点还在)]。"""
    root = _pkg_root()
    out = []
    for rel, anchor, _probe, mark in PATCHES:
        p = root / rel
        text = _read(p) if p.exists() else ""
        out.append((p, mark in text, _fit(anchor, text) in text))
    return out


def cmd_status(verbose: bool = False) -> int:
    root = _pkg_root()
    print(f"框架包：{root}")
    print()
    bad = 0
    for rel, anchor, _probe, mark in PATCHES:
        p = root / rel
        if not p.exists():
            print(f"  ❌ 文件不存在：{rel}")
            bad += 1
            continue
        text = _read(p)
        has_probe = mark in text
        has_anchor = _fit(anchor, text) in text
        state = "已打探针" if has_probe else ("干净（锚点可打）" if has_anchor else "⚠️ 锚点漂移")
        print(f"  {rel}")
        print(f"      {state}   [探针={has_probe} 锚点={has_anchor}]")
        if has_anchor and text.count(_fit(anchor, text)) > 1:
            print("      ⚠️ 锚点出现多次，拒绝打补丁")
            bad += 1
        if verbose:
            print(f"      文件：{p}")
    print()
    return 1 if bad else 0


def _apply_one(p: Path, anchor: str, probe: str, mark: str) -> str:
    text = _read(p)
    if mark in text:
        return "skip（已有探针）"
    n = text.count(_fit(anchor, text))
    if n != 1:
        return f"FAIL（锚点出现 {n} 次，需恰好 1 次）"
    _write(p, text.replace(_fit(anchor, text), _fit(probe, text)))
    return "ok"


def cmd_apply(dry_run: bool) -> int:
    root = _pkg_root()
    if dry_run:
        print("== dry-run：只检查锚点，不改文件 ==")
    print()
    fail = 0
    for rel, anchor, probe, mark in PATCHES:
        p = root / rel
        if not p.exists():
            print(f"  ❌ {rel}：文件不存在")
            fail += 1
            continue
        text = _read(p)
        n = text.count(_fit(anchor, text))
        already = mark in text
        label = "已打探针" if already else f"锚点命中 {n} 次"
        print(f"  {rel}\n      {label}")
        if not already and n != 1:
            fail += 1
            continue
        if dry_run or already:
            continue
        r = _apply_one(p, anchor, probe, mark)
        print(f"      → {r}")
        if r != "ok":
            fail += 1
    print()
    if fail:
        print(f"  ❌ {fail} 处未就绪；锚点可能随框架版本漂移，请人工核对后更新本脚本。")
        return 1
    if dry_run:
        print("  ✅ 锚点齐备，可执行 --apply")
    else:
        print("  ✅ 探针已就位。跑一次 run_stub_online.py 后再用 --grep 看输出。")
    return 0


def cmd_revert() -> int:
    """精确还原：把每一段探针文本**逆向替换回锚点文本**。

    ⚠️ 为什么不用正则/按行删（R11 踩过的坑）：
        早期版本用「删掉含标记的行」来还原。探针 A/C 是**多行**的
        `team_logger.info(...)` 调用，按行删只删掉了含标记的那一行参数，
        留下半截调用 → **把 task_board.py 改成了语法错误**。
        而 `ANCHOR` 与 `PROBE` 是一一对应的原文，`PROBE -> ANCHOR`
        的逐字逆向替换是**完全无损**的，多行也照原样恢复。
    """
    root = _pkg_root()
    print("== 还原（probe -> anchor 逐字逆向替换）==")
    print()
    # ⚠️ 不要按文件去重：同一个文件可能有多段探针
    #    （`task_board.py` 有 A 和 C 两段、`kernel.py` 有 E 和 F1–F3 四段）。
    #    R11 第一版加了 `seen` 去重，结果每个文件只还原了第一段，
    #    文件因此比原版**更大**（探针还在），哈希对不上。
    for rel, anchor, probe, _mark in PATCHES:
        p = root / rel
        if not p.exists():
            print(f"  skip {rel}（不存在）")
            continue
        text = _read(p)
        if probe not in text:
            print(f"  skip {rel}（这段探针不在，可能已还原或锚点变了）")
            continue
        n = text.count(probe)
        _write(p, text.replace(_fit(probe, text), _fit(anchor, text)))
        print(f"  ok {rel}（还原 {n} 段）")
    print()
    print("  建议随后 --dry-run 确认锚点完好；必要时与原始副本比对哈希。")
    return 0

def cmd_grep(log_path: str | None) -> int:
    """从框架日志里把探针输出捞出来。"""
    cands = []
    if log_path:
        cands = [Path(log_path)]
    else:
        for p in (
            Path("logs/logs/run/jiuwen.log"),
            Path("logs/run/jiuwen.log"),
            Path("run/jiuwen.log"),
        ):
            if p.exists():
                cands.append(p)
    if not cands:
        print("  ❌ 找不到框架日志（试过 logs/logs/run/jiuwen.log 等）")
        print("     用 --log <路径> 指定")
        return 1

    for p in cands:
        text = _read(p)
        lines = [
            ln for ln in text.splitlines()
            if any(m in ln for m in (MARK_A, MARK_B, MARK_C, MARK_D, MARK_E, MARK_G, MARK_H)) or "error in wake_callback" in ln
        ]
        print("=" * 74)
        print(f" 日志：{p}（{len(text):,} 字符）")
        print("=" * 74)
        if not lines:
            print("  ❌ 一条探针输出都没有。")
            print("     可能原因：① 探针没打上（先 --show）② 跑的不是这次日志 ③ 走了 scheduled 路径")
            return 1
        for ln in lines:
            print("  " + ln[:400])
        print()
        # 给一句直读结论
        nudge0 = [ln for ln in lines if MARK_A in ln and "board=0" in ln]
        dropped = [ln for ln in lines if MARK_B in ln]
        wake_err = [ln for ln in lines if "error in wake_callback" in ln]
        print("  —— 直读 ——")
        print(f"  nudge 且 board=0 : {len(nudge0)} 条" + ("  ← ⭐ 就是它：筛选条件不匹配" if nudge0 else ""))
        print(f"  deliver_input 被丢弃 : {len(dropped)} 条" + ("  ← harness 没建起来" if dropped else ""))
        print(f"  handler 抛异常 : {len(wake_err)} 条" + ("  ← 被静默吞掉，需打 traceback" if wake_err else ""))
    return 0


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="给 openJiuwen 打/撤唤醒链探针（只加日志）")
    ap.add_argument("--dry-run", action="store_true", help="只检查锚点，不改文件")
    ap.add_argument("--apply", action="store_true", help="打探针")
    ap.add_argument("--revert", action="store_true", help="还原")
    ap.add_argument("--show", action="store_true", help="看当前状态")
    ap.add_argument("--grep", action="store_true", help="从日志里捞探针输出")
    ap.add_argument("--log", default=None, help="--grep 用的日志路径")
    args = ap.parse_args()

    if args.apply or args.dry_run:
        return cmd_apply(dry_run=args.dry_run)
    if args.revert:
        return cmd_revert()
    if args.grep:
        return cmd_grep(args.log)
    return cmd_status(verbose=True)


if __name__ == "__main__":
    raise SystemExit(main())
