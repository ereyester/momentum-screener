"""
モメンタムチンパン Web用データ生成スクリプト
universe_screener.py のロジックをそのまま使って JSON を出力する
"""

import json
import sys
import os
import io
import time
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf

# universe_screener.py と同じディレクトリにいることを確認
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from universe_screener import (
    get_universe,
    batch_download,
    calc_momentum_scores,
    _get_usdjpy,
    _HEADERS,
    grade,
)


def fetch_jpx_names() -> dict[str, str]:
    """JPXの銘柄一覧Excelから企業名を取得（日本株用・超信頼性）"""
    print("  JPXから企業名データをダウンロード中...", end=" ", flush=True)
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content))

        names = {}
        if "コード" in df.columns and "銘柄名" in df.columns:
            for _, row in df.iterrows():
                code = str(row["コード"]).strip()
                name = str(row["銘柄名"]).strip()
                if code and name and name != "nan":
                    ticker = code + ".T"
                    names[ticker] = name
        print(f"{len(names)}銘柄の名前を取得")
        return names
    except Exception as e:
        print(f"失敗: {e}")
        return {}


def fetch_names_robust(tickers: list[str], jpx_names: dict[str, str],
                       chunk_size: int = 50) -> dict[str, str]:
    """JPX名 + yfinance で銘柄名を取得（日本株はJPX優先、米国株はyfinance）"""
    names = {}

    for t in tickers:
        # 日本株: JPXデータから取得（確実）
        if t in jpx_names:
            names[t] = jpx_names[t]
            continue

    # 残りの銘柄（主に米国株）は yfinance から取得
    remaining = [t for t in tickers if t not in names]
    if remaining:
        print(f"  yfinanceから{len(remaining)}銘柄の社名取得中...", end=" ", flush=True)
        for t in remaining:
            try:
                info = yf.Ticker(t).info
                name = info.get("shortName") or info.get("longName") or t
                names[t] = name
            except Exception:
                names[t] = t
            time.sleep(0.15)
        print("完了")

    return names


def build_deck_data(df, names, budget_man=3000, top_us=10, top_jp=6, usdjpy=150.0):
    """build_deck() と同じロジックでデッキデータを生成（JSON用）"""
    us_top = df[df["market"] == "US"].head(top_us)
    jp_top = df[df["market"] == "JP"].head(top_jp)
    deck = __import__("pandas").concat([us_top, jp_top]).reset_index(drop=True)

    n_stocks = len(deck)
    budget_jpy = budget_man * 10_000
    target_jpy_per_stock = budget_jpy / n_stocks if n_stocks > 0 else budget_jpy

    stocks = []
    actual_allocs = []

    for _, row in deck.iterrows():
        t = row["ticker"]
        target_jpy = target_jpy_per_stock
        price = row["price"]
        ma5 = row.get("ma5", 0.0)
        ma10 = row.get("ma10", 0.0)
        ma20 = row["ma20"]

        # エントリー価格（通常モード）
        if price > ma5 > 0:
            entry_p = ma5
        elif ma5 >= price > ma10 > 0:
            entry_p = ma10
        elif ma10 >= price > ma20 > 0:
            entry_p = ma20
        else:
            entry_p = price * 0.95

        stop_p = entry_p * 0.93

        # 動的利確ロジック
        ret_1m = row.get("ret_1m", 0.0)
        high_52w = row.get("high_52w", price * 1.5)
        from_ath = row.get("from_ath", 0.0)

        base_target_pct = max(15.0, min(50.0, ret_1m * 0.5)) / 100.0
        target_p = entry_p * (1.0 + base_target_pct)

        if from_ath < -3.0:
            ath_resistance = high_52w * 0.98
            if target_p > ath_resistance and ath_resistance > entry_p * 1.05:
                target_p = ath_resistance

        if row["currency"] == "JPY":
            lot_size = 100
            entry_jpy = entry_p
            # 1単元すら買えない場合は0株にする
            if target_jpy < entry_jpy * lot_size:
                shares = 0
            else:
                shares_raw = target_jpy / entry_jpy
                shares = int(shares_raw // lot_size) * lot_size
            cost_jpy = shares * entry_jpy
        else:
            entry_usd = entry_p
            entry_jpy = entry_usd * usdjpy
            if target_jpy < entry_jpy:
                shares = 0
            else:
                shares_raw = target_jpy / entry_jpy
                shares = int(shares_raw)
            cost_jpy = shares * entry_jpy

        alloc_man = cost_jpy / 10_000

        stocks.append({
            "ticker": t,
            "name": names.get(t, t),
            "market": row["market"],
            "currency": row["currency"],
            "price": round(float(price), 2),
            "ret_1m": round(float(row.get("ret_1m", 0)), 2),
            "ret_3m": round(float(row.get("ret_3m", 0)), 2),
            "rsi": round(float(row.get("rsi", 50)), 1),
            "score": round(float(row["score"]), 2),
            "shares": int(shares),
            "alloc_man": round(alloc_man),
            "entry_price": round(float(entry_p), 2),
            "stop_price": round(float(stop_p), 2),
            "target_price": round(float(target_p), 2),
        })
        actual_allocs.append(alloc_man)

    total_alloc = sum(actual_allocs)
    return {
        "budget_man": budget_man,
        "usdjpy": round(usdjpy, 2),
        "stocks": stocks,
        "total_alloc_man": round(total_alloc),
        "remaining_man": round(budget_man - total_alloc),
        "max_loss_man": round(total_alloc * 0.07),
    }


def main():
    print("=" * 60)
    print("  🦍 モメンタムチンパン Web用データ生成")
    print("=" * 60)

    # 1. ユニバース取得
    print("\n[Step 1] ユニバース取得")
    universe = get_universe(
        include_sp500=True,
        include_ndx=True,
        include_jpx=True,
        include_leverage=False,
    )
    if not universe:
        print("銘柄リストを取得できませんでした。")
        return

    tickers = list(universe.keys())

    # 2. 価格データダウンロード
    print(f"[Step 2] 価格データ一括ダウンロード (1y)")
    close_df, volume_df = batch_download(tickers, period="1y")

    if close_df.empty:
        print("価格データを取得できませんでした。")
        return

    # 3. モメンタムスコア計算
    print("[Step 3] モメンタムスコア計算中...")
    df = calc_momentum_scores(close_df, volume_df, universe)
    print(f"  スコア計算完了: {len(df)}銘柄")

    # 4. 企業名取得（JPX + yfinance）
    top_n = 50
    top_tickers = df.head(top_n + 10)["ticker"].tolist()
    print(f"[Step 4] 上位{len(top_tickers)}銘柄の企業名取得中...")
    jpx_names = fetch_jpx_names()
    names = fetch_names_robust(top_tickers, jpx_names)

    # 5. USD/JPY取得
    usdjpy = _get_usdjpy()
    print(f"  USD/JPY: {usdjpy:.2f}")

    # 6. JSON構築
    print("[Step 5] JSONデータ構築中...")

    ranking = []
    for idx, (_, row) in enumerate(df.head(top_n).iterrows()):
        t = row["ticker"]
        ranking.append({
            "rank": idx + 1,
            "ticker": t,
            "name": names.get(t, t),
            "market": row["market"],
            "currency": row["currency"],
            "price": round(float(row["price"]), 2),
            "day_chg": round(float(row["day_chg"]), 2),
            "ret_1m": round(float(row["ret_1m"]), 2),
            "ret_3m": round(float(row["ret_3m"]), 2),
            "ret_6m": round(float(row["ret_6m"]), 2),
            "ret_1y": round(float(row["ret_1y"]), 2),
            "ytd_chg": round(float(row["ytd_chg"]), 2),
            "rsi": round(float(row["rsi"]), 1),
            "from_ath": round(float(row["from_ath"]), 2),
            "vol_ratio": round(float(row["vol_ratio"]), 2),
            "volatility": round(float(row["volatility"]), 3),
            "score": round(float(row["score"]), 2),
            "ma5": round(float(row.get("ma5", 0)), 2),
            "ma20": round(float(row.get("ma20", 0)), 2),
            "ma50": round(float(row.get("ma50", 0)), 2),
            "high_52w": round(float(row.get("high_52w", 0)), 2),
            "low_52w": round(float(row.get("low_52w", 0)), 2),
        })

    # デッキ生成
    deck_data = build_deck_data(df, names, budget_man=3000, top_us=10, top_jp=6, usdjpy=usdjpy)

    # 統計
    us_df = df[df["market"] == "US"]
    jp_df = df[df["market"] == "JP"]

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_scanned": len(df),
        "stats": {
            "us_count": len(us_df),
            "jp_count": len(jp_df),
            "avg_score_us": round(float(us_df["score"].mean()), 2) if not us_df.empty else 0,
            "avg_score_jp": round(float(jp_df["score"].mean()), 2) if not jp_df.empty else 0,
        },
        "usdjpy": round(usdjpy, 2),
        "ranking": ranking,
        "deck": deck_data,
    }

    # 7. JSON保存
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "latest.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  ✅ JSON保存完了: {out_path}")
    print(f"  ランキング: {len(ranking)}銘柄")
    print(f"  デッキ: {len(deck_data['stocks'])}銘柄")
    print(f"  合計スキャン: {len(df)}銘柄")
    print("=" * 60)


if __name__ == "__main__":
    main()
