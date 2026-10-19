"""清空 openJiuwen 团队库的**数据**，但保留表结构。

为什么不是直接删 team.db（R9 实测教训）：
    删掉整个库后，框架要在同一时刻给 6 个成员建会话表（`team_task_<suffix>` 等），
    SQLite 写锁竞争 → `create_message ... hit a transient DB error` →
    「Failed to create broadcast message」，而且 `create_task` / `spawn_teammate`
    都会稀里糊涂地"执行了但没落地"。**保留表、只清行**就没有这个问题。

用法：
    python tools/reset_team_db.py            # 清空（会打印删了多少行）
    python tools/reset_team_db.py --dry-run  # 只看会删什么
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
    guess = Path.home() / ".openjiuwen" / ".agent_teams" / "team.db"
    return guess if guess.exists() else None


def main() -> int:
    _reconfig()
    ap = argparse.ArgumentParser(description="清空团队库数据（保留表结构）")
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Path(args.db) if args.db else find_db()
    if db is None or not db.exists():
        print("  ❌ 找不到 team.db（先跑一次 run_stub_online.py 让它建库）")
        return 1

    con = sqlite3.connect(str(db))  # 可读写，才能看到 WAL
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    if not tables:
        print("  （库里没有表，无需清理）")
        return 0

    total = 0
    for t in tables:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        if not n:
            continue
        if args.dry_run:
            print(f"  将清空 {t:56} {n:4} 行")
        else:
            con.execute(f'DELETE FROM "{t}"')
            print(f"  已清空 {t:56} {n:4} 行")
        total += n

    if not args.dry_run:
        con.commit()
    con.close()
    print()
    print(f"  合计 {total} 行{'（dry-run，未改动）' if args.dry_run else ' 已清空'}")
    print("  表结构保留 —— 下次运行沿用同一套会话表，不会触发并发建表抢锁。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
