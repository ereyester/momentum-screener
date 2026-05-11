"""
🐒 Spike Chaser スクリーナー
今日・直近で急騰/急落した銘柄をリアルタイム検知してエントリー候補を表示する
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from colorama import Fore, Style, init
from tabulate import tabulate
import warnings
import time
import argparse

warnings.filterwarnings("ignore")
init(autoreset=True)

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from momentum_screener import US_STOCKS, JP_STOCKS


# ============================================================
# データ取得
# ============================================================

def fetch_spike_data(ticker: str, period: str = "3mo") -> dict | None:
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if hist is None or len(hist) < 22:
            return None

        close  = hist["Close"]
        volume = hist["Volume"]

        price    = float(close.iloc[-1])
        prev     = float(close.iloc[-2])
        day_ret  = (price / prev - 1) * 100

        vol_avg   = float(volume.tail(20).mean())
        vol_today = float(volume.iloc[-1])
        vol_ratio = vol_today / vol_avg if vol_avg > 0 else 1.0

        ma20  = float(close.tail(20).mean())
        ma50  = float(close.tail(50).mean()) if len(close) >= 50 else 0.0

        delta = close.diff()
        gain  = delta.where(delta > 0, 0.0).tail(14).mean()
        loss  = (-delta.where(delta < 0, 0.0)).tail(14).mean()
        rsi   = 100 - (100 / (1 + gain / loss)) if loss != 0 else 100.0

        ret_1w = (price / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0.0
        ret_1m = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0.0

        high_52w = float(close.max())
        from_ath = (price - high_52w) / high_52w * 100

        currency = "JPY" if ticker.endswith(".T") else "USD"

        return {
            "ticker":    ticker,
            "price":     price,
            "day_ret":   day_ret,
            "vol_ratio": vol_ratio,
            "ma20":      ma20,
            "ma50":      ma50,
            "rsi":       rsi,
            "ret_1w":    ret_1w,
            "ret_1m":    ret_1m,
            "from_ath":  from_ath,
            "currency":  currency,
        }
    except Exception:
        return None


# ============================================================
# スパイク判定
# ============================================================

def classify_spike(d: dict,
                   spike_up_pct: float,
                   spike_down_pct: float,
                   vol_ratio_min: float) -> str | None:
    """UP / DOWN / None を返す"""
    day_ret   = d["day_ret"]
    vol_ratio = d["vol_ratio"]
    price     = d["price"]
    ma50      = d["ma50"]
    rsi       = d["rsi"]

    is_up   = (day_ret >= spike_up_pct and vol_ratio >= vol_ratio_min
               and (ma50 == 0 or price > ma50) and rsi <= 88)
    is_down = (day_ret <= -spike_down_pct and vol_ratio >= vol_ratio_min)

    if is_up:
        return "UP"
    if is_down:
        return "DOWN"
    return None


def spike_score(d: dict, spike_type: str) -> int:
    """エントリー優先度スコア"""
    score = 0
    if spike_type == "UP":
        score += int(d["day_ret"] * 2)          # 騰落率が大きいほど高スコア
        score += int(d["vol_ratio"] * 5)         # 出来高急増
        score += int(d["ret_1m"])                # 1ヶ月トレンド
        if d["rsi"] <= 70:  score += 10          # 過熱しすぎていない
        if d["from_ath"] >= -10: score += 10     # 高値圏
    else:  # DOWN
        score += int(-d["day_ret"] * 2)          # 暴落幅が大きい
        score += int(d["vol_ratio"] * 5)         # 出来高急増
        if d["rsi"] <= 40: score += 15           # 売られすぎ
        score += int(-d["from_ath"])             # 高値から遠い（割安感）
    return score


# ============================================================
# 表示
# ============================================================

def fmt_price(price: float, currency: str) -> str:
    if currency == "JPY":
        return f"¥{price:,.0f}"
    return f"${price:,.2f}"


def fmt_ret(val: float) -> str:
    c = Fore.GREEN if val > 0 else Fore.RED
    return c + f"{val:+.2f}%" + Style.RESET_ALL


def print_spike_table(results: list, spike_type: str, meta_us: dict, meta_jp: dict):
    filtered = [r for r in results if r["spike_type"] == spike_type]
    if not filtered:
        print(f"  ({spike_type} スパイク: 該当なし)")
        return

    rows = []
    for r in filtered:
        d      = r["data"]
        ticker = d["ticker"]
        meta   = meta_us.get(ticker) or meta_jp.get(ticker) or {}
        name   = meta.get("name", ticker)[:10]
        tier   = meta.get("tier", "-")
        theme  = meta.get("theme", "-")[:18]

        tier_color = {"S": Fore.RED, "A": Fore.YELLOW, "B": Fore.GREEN}.get(tier, Fore.WHITE)

        # 推奨アクション
        if spike_type == "UP":
            action = f"{Fore.GREEN}モメンタム追撃 →{Style.RESET_ALL}"
        else:
            action = f"{Fore.CYAN}リバウンド狙い →{Style.RESET_ALL}"

        rows.append([
            Fore.CYAN + ticker + Style.RESET_ALL,
            name,
            tier_color + tier + Style.RESET_ALL,
            fmt_price(d["price"], d["currency"]),
            fmt_ret(d["day_ret"]),
            f"{d['vol_ratio']:.1f}x",
            f"{d['rsi']:.0f}",
            fmt_ret(d["from_ath"]),
            f"{r['score']}",
            action,
            theme,
        ])

    hdrs = ["銘柄", "名前", "Tier", "現在値", "本日", "出来高", "RSI", "ATH比", "スコア", "アクション", "テーマ"]
    print(tabulate(rows, headers=hdrs, tablefmt="simple"))


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spike-up-pct",   type=float, default=5.0,  help="急騰閾値% (default: 5)")
    parser.add_argument("--spike-down-pct", type=float, default=5.0,  help="急落閾値% (default: 5)")
    parser.add_argument("--vol-ratio",      type=float, default=1.3,  help="出来高倍率閾値 (default: 1.3)")
    parser.add_argument("--top-n",          type=int,   default=10,   help="表示件数")
    args = parser.parse_args()

    print(Fore.YELLOW + "=" * 64)
    print("   🐒 Spike Chaser スクリーナー  - 急騰・急落検知")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 時点")
    print("=" * 64 + Style.RESET_ALL)
    print(f"  急騰閾値: +{args.spike_up_pct}%  急落閾値: -{args.spike_down_pct}%  出来高: {args.vol_ratio}x以上\n")

    all_tickers = list(US_STOCKS.keys()) + list(JP_STOCKS.keys())
    print(f"  スキャン中... ({len(all_tickers)} 銘柄)")

    spike_results = []
    no_spike      = []

    for i, ticker in enumerate(all_tickers):
        print(f"  [{i+1:2d}/{len(all_tickers)}] {ticker:<12}", end="\r")
        d = fetch_spike_data(ticker)
        time.sleep(0.25)
        if d is None:
            continue

        stype = classify_spike(d, args.spike_up_pct, args.spike_down_pct, args.vol_ratio)
        if stype:
            score = spike_score(d, stype)
            spike_results.append({"data": d, "spike_type": stype, "score": score})
        else:
            no_spike.append(d)

    spike_results.sort(key=lambda x: x["score"], reverse=True)

    print(f"  スキャン完了: {len(spike_results)} 銘柄でスパイク検知  ({len(no_spike)} 銘柄は通常)      \n")

    # ========== 急騰 UP ==========
    up_count = sum(1 for r in spike_results if r["spike_type"] == "UP")
    print("=" * 64)
    print(f"  🚀 急騰追撃候補  (UP) — {up_count} 銘柄")
    print("=" * 64)
    print_spike_table(spike_results[:args.top_n * 2], "UP", US_STOCKS, JP_STOCKS)

    # ========== 急落リバウンド DOWN ==========
    dn_count = sum(1 for r in spike_results if r["spike_type"] == "DOWN")
    print("\n" + "=" * 64)
    print(f"  📉 急落リバウンド候補  (DOWN) — {dn_count} 銘柄")
    print("=" * 64)
    print_spike_table(spike_results[:args.top_n * 2], "DOWN", US_STOCKS, JP_STOCKS)

    # ========== 注目銘柄ランキング（UP+DOWN 合算） ==========
    print("\n" + "=" * 64)
    print(f"  🏆 スコアランキング TOP{args.top_n}（UP + DOWN 全部）")
    print("=" * 64)
    if spike_results:
        top_rows = []
        for r in spike_results[:args.top_n]:
            d      = r["data"]
            ticker = d["ticker"]
            meta   = US_STOCKS.get(ticker) or JP_STOCKS.get(ticker) or {}
            name   = meta.get("name", ticker)[:10]
            tier   = meta.get("tier", "-")
            type_c = Fore.GREEN + "🚀 UP" + Style.RESET_ALL if r["spike_type"] == "UP" else Fore.RED + "📉 DOWN" + Style.RESET_ALL
            top_rows.append([
                Fore.CYAN + ticker + Style.RESET_ALL,
                name,
                tier,
                fmt_price(d["price"], d["currency"]),
                fmt_ret(d["day_ret"]),
                f"{d['vol_ratio']:.1f}x",
                f"{d['rsi']:.0f}",
                type_c,
                r["score"],
            ])
        print(tabulate(
            top_rows,
            headers=["銘柄", "名前", "Tier", "現在値", "本日", "出来高", "RSI", "種別", "スコア"],
            tablefmt="simple",
        ))
    else:
        print("  今日はスパイク検知なし。閾値を下げて再実行してみてください。")
        print(f"  例: python screener_spike.py --spike-up-pct 3 --spike-down-pct 3")

    print(f"\n  {'─'*62}")
    print(f"  ✅ 急騰追撃: スパイク翌日にエントリー → {5}営業日後手仕舞い")
    print(f"  ✅ 急落リバウンド: 暴落翌日に打診買い → {3}〜5営業日で判断")
    print(f"  ⚠️  損切りは エントリーから -7% 厳守")
    print(f"  {'─'*62}")
    print(f"  ⚠️  本ツールは情報提供目的です。投資判断はご自身でお願いします。\n")


if __name__ == "__main__":
    main()
