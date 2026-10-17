#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼 openJiuwen 团队库的真实状态（任务板 / 成员 / 消息）。

**为什么需要这个工具**

排查运行层时，「我的轨迹记录器说有 / 框架说没有」这种分歧最容易浪费时间。
本工具**直接读框架自己的 SQLite**，不经过任何中间层 —— 唯一可信的口径。

另外它是**只读**的，不会污染框架状态。

用法：
    python tools/inspect_team_db.py                 # 自动找库
    python tools/inspect_team_db.py --db <path>     # 指定库
    python tools/inspect_team_db.py --team faron_wenshu_team

═══════════════════════════════════════════════════════════════════════
读库时必踩的两个坑（写在这里，省得下次再查一遍）
───────────────────────────────────────────────────────────────────────
① **库可能是空的、数据全在 WAL 里。**
   实测 `team.db` 只有 4 KB（空壳），而 `team.db-wal` 有 688 KB。
   用 `file:...?mode=ro` 只读打开**看不到 WAL 里的表**，会误判成「表没建」。
   所以这里用普通读写连接打开（只执行 SELECT）。

② **表名带会话后缀，正文在文件里。**
   `team_task_<suffix>` / `team_message_<suffix>`，suffix 由
   `_sanitize_session_id_for_table(session_id)` 生成。
   而任务的 `content`、消息的正文**不在库里**，在
   `<home>/<team>/sessions/<session>/tasks/<id>.md` 这类文件里。
   库里 `content` 字段可能是 `#file#` 占位符。
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _reconfig() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


def find_db() -> Path | None:
    """按框架的默认位置找 team.db。

    **先查约定路径，查不到才 import 框架** —— `import openjiuwen` 会打 20 秒
    的 INFO 日志（注册各种 connector / parser），对一个只读查看工具太吵了。
    """
    guess = Path.home() / ".openjiuwen" / ".agent_teams" / "team.db"
    if guess.exists():
        return guess
    try:
        from openjiuwen.agent_teams.paths import get_agent_teams_home

        cand = Path(get_agent_teams_home()) / "team.db"
        return cand if cand.exists() else None
    except Exception:  # noqa: BLE001
        return None


def show(db: Path, team: str | None) -> int:
    if not db.exists():
        print(f"  ❌ 库不存在：{db}")
        return 1

    # 注意：不要用 mode=ro —— 那样读不到 WAL（见模块头注释 ①）
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row

    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print("=" * 74)
    print(f" 库：{db}")
    print(f" 表数：{len(tables)}")
    print("=" * 74)
    for t in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"   {t:56} {n:5} 行{'   ← 有数据' if n else ''}")

    # ---- 成员 ----
    if "team_member" in tables:
        print()
        print("=" * 74)
        print(" 成员（status = 持久化状态；execution_status = 执行状态）")
        print("=" * 74)
        q = "SELECT * FROM team_member"
        args: tuple = ()
        if team:
            q += " WHERE team_name = ?"
            args = (team,)
        for r in con.execute(q, args):
            d = dict(r)
            print(f"   {str(d.get('member_name')):20} "
                  f"status={str(d.get('status')):10} "
                  f"exec={str(d.get('execution_status')):10} "
                  f"role={d.get('role')}")

    # ---- 任务 ----
    task_tables = [t for t in tables if t.startswith("team_task_")
                   and "dependency" not in t]
    for t in task_tables:
        print()
        print("=" * 74)
        print(f" 任务板：[{t}]")
        print("=" * 74)
        rows = con.execute(f'SELECT * FROM "{t}"').fetchall()
        if not rows:
            print("   （空）")
        for r in rows:
            d = dict(r)
            print(f"   task_id={d.get('task_id')!r}")
            print(f"     status={d.get('status')!r}  assignee={d.get('assignee')!r} "
                  f"reviewer={d.get('reviewer')!r}")
            print(f"     title={(d.get('title') or '')[:60]!r}")

    # ---- 依赖 ----
    dep_tables = [t for t in tables if t.startswith("team_task_dependency_")]
    for t in dep_tables:
        rows = con.execute(f'SELECT * FROM "{t}"').fetchall()
        if rows:
            print()
            print(f" 依赖：[{t}]  {len(rows)} 条")
            for r in rows:
                d = dict(r)
                print(f"   {d}")

    # ---- 消息 ----
    msg_tables = [t for t in tables if t.startswith("team_message_")]
    for t in msg_tables:
        rows = con.execute(f'SELECT * FROM "{t}"').fetchall()
        print()
        print("=" * 74)
        print(f" 消息：[{t}]  共 {len(rows)} 条")
        print("=" * 74)
        if not rows:
            print("   （空）")
        for r in rows[:20]:
            d = dict(r)
            body = (d.get("content") or "")
            print(f"   from={d.get('from_member_name')!r} "
                  f"to={d.get('to_member_name')!r} "
                  f"broadcast={d.get('broadcast')} is_read={d.get('is_read')}")
            print(f"     content={body[:60]!r}"
                  f"{'   ← 正文在文件里' if body == '#file#' else ''}")

    con.close()
    print()
    print(" 提示：content 为 '#file#' 表示正文落在")
    print("       <teams_home>/<team>/sessions/<session>/messages/.../*.md")
    return 0


def main() -> int:
    _reconfig()
    ap = argparse.ArgumentParser(description="查看 openJiuwen 团队库真实状态")
    ap.add_argument("--db", default=None, help="team.db 路径（默认自动找）")
    ap.add_argument("--team", default=None, help="只看某个团队")
    args = ap.parse_args()

    db = Path(args.db) if args.db else find_db()
    if db is None:
        print("  ❌ 找不到 team.db；用 --db 指定")
        return 1
    return show(db, args.team)


if __name__ == "__main__":
    raise SystemExit(main())
