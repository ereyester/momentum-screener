"""
ランキング履歴の保存 — 更新ごとのスナップショットを docs/data/history/ に蓄積する

  history/<id>.json   各回のランキング（上位 SNAPSHOT_TOP 位）
  history/index.json  スナップショット一覧（古い順）
  history/ranks.json  銘柄ごとの順位推移（index.json と同じ並び）
"""

import glob
import json
import os

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data", "history")
SNAPSHOT_TOP = 300
TRACK_TOP = 100  # ranks.json に載せる順位の上限（肥大化防止）
COLS = ["rank", "ticker", "name", "market", "currency", "price", "day_chg", "ret_1m", "score"]


def snapshot_id(updated_at: str) -> str:
    """'2026-09-27 22:49:07' -> '2026-09-27_2249'"""
    return updated_at[:10] + "_" + updated_at[11:13] + updated_at[14:16]


def save_snapshot(updated_at: str, total_scanned: int, rows: list[dict]) -> str:
    """rows: rank順の dict のリスト（COLS のキーを持つ）"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    sid = snapshot_id(updated_at)
    snap = {
        "id": sid,
        "t": updated_at[:16],
        "total": total_scanned,
        "cols": COLS,
        "rows": [[r.get(c) for c in COLS] for r in rows[:SNAPSHOT_TOP]],
    }
    with open(os.path.join(HISTORY_DIR, sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    rebuild_indexes()
    return sid


def rebuild_indexes() -> None:
    """全スナップショットから index.json / ranks.json を作り直す"""
    snaps = []
    for path in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json"))):
        if os.path.basename(path) in ("index.json", "ranks.json"):
            continue
        with open(path, encoding="utf-8") as f:
            snaps.append(json.load(f))
    snaps.sort(key=lambda s: s["id"])

    index = [{"id": s["id"], "t": s["t"], "total": s["total"], "n": len(s["rows"])} for s in snaps]

    # 疎な形式 {ticker: [[スナップショット番号, 順位, スコア, 株価], ...]}、TRACK_TOP 位以内のみ
    ranks: dict[str, list] = {}
    names: dict[str, list] = {}
    for i, s in enumerate(snaps):
        c = s["cols"]
        ri, ti, ni, mi, si, pi = (c.index(k) for k in ("rank", "ticker", "name", "market", "score", "price"))
        for row in s["rows"]:
            if row[ri] > TRACK_TOP:
                break
            t = row[ti]
            ranks.setdefault(t, []).append([i, row[ri], row[si], row[pi]])
            names[t] = [row[ni], row[mi]]  # 最新の社名・市場で上書き

    with open(os.path.join(HISTORY_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"snapshots": index}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(HISTORY_DIR, "ranks.json"), "w", encoding="utf-8") as f:
        json.dump({"ids": [s["id"] for s in snaps], "names": names, "ranks": ranks},
                  f, ensure_ascii=False, separators=(",", ":"))
