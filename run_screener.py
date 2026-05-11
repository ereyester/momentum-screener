"""
モメンタムチンパン スクリーナー 起動スクリプト
使い方:
  python run_screener.py           # 通常実行（全機能）
  python run_screener.py --quick   # モメンタムスクリーニングのみ
  python run_screener.py --csv     # CSV出力
  python run_screener.py --custom  # カスタム銘柄追加
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import csv
import time
from datetime import datetime
from colorama import init, Fore, Style
init(autoreset=True)

from momentum_screener import (
    US_STOCKS, JP_STOCKS, fetch_stock_data,
    screen_momentum_chimps, screen_value_reversal,
    print_momentum_screening, print_reversal_screening,
    print_portfolio_summary, print_entry_plan,
    print_portfolio_table, print_header, calc_entry_levels,
    format_price, earnings_countdown, color_val
)


def save_csv(all_data: dict, stocks_meta_us: dict, stocks_meta_jp: dict, filename: str = None):
    if filename is None:
        filename = f"screener_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    rows = []
    for ticker, d in all_data.items():
        meta = stocks_meta_us.get(ticker) or stocks_meta_jp.get(ticker) or {}
        lvl = calc_entry_levels(d, meta.get("tier", "B"))
        rows.append({
            "ticker": ticker,
            "name": meta.get("name", ""),
            "tier": meta.get("tier", ""),
            "theme": meta.get("theme", ""),
            "price": round(d["price"], 2),
            "currency": d["currency"],
            "day_chg_pct": round(d["day_chg"], 2),
            "ytd_chg_pct": round(d["ytd_chg"], 2),
            "ret_1m_pct": round(d["ret_1m"], 2),
            "ret_3m_pct": round(d["ret_3m"], 2),
            "ret_1y_pct": round(d["ret_1y"], 2),
            "high_52w": round(d["high_52w"], 2),
            "from_ath_pct": round(d["from_ath"], 2),
            "rsi": round(d["rsi"], 1),
            "vol_ratio": round(d["vol_ratio"], 2),
            "ma20": round(d["ma20"], 2),
            "ma50": round(d["ma50"], 2),
            "ma200": round(d["ma200"], 2),
            "momentum_score": round(d["momentum_score"], 2),
            "entry_price": round(lvl["entry"], 2),
            "stop_price": round(lvl["stop"], 2),
            "target_price": round(lvl["target"], 2),
            "earnings": earnings_countdown(ticker),
            "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  CSV保存完了: {filename} ({len(rows)}銘柄)")
    return filename


def add_custom_tickers(extra_us: list = None, extra_jp: list = None):
    """カスタム銘柄を動的追加"""
    if extra_us:
        for t in extra_us:
            if t not in US_STOCKS:
                US_STOCKS[t] = {"name": t, "tier": "B", "theme": "カスタム追加", "alloc": 0}
    if extra_jp:
        for t in extra_jp:
            if t not in JP_STOCKS:
                JP_STOCKS[t] = {"name": t, "tier": "B", "theme": "カスタム追加", "alloc": 0}


def quick_mode(all_data: dict):
    """クイックモード: モメンタムスクリーニングのみ"""
    all_list = list(all_data.values())
    screened = screen_momentum_chimps(all_list)
    print_momentum_screening(screened, US_STOCKS, JP_STOCKS, top_n=20)

    print_header("🔄 転換点ランキング TOP10")
    reversal = screen_value_reversal(all_list)
    print_reversal_screening(reversal, US_STOCKS, JP_STOCKS, top_n=10)


def full_mode(all_data: dict, save_to_csv: bool = False):
    """フルモード: 全機能実行"""
    print_portfolio_summary(3000)
    print_entry_plan(all_data, 3000)
    print_portfolio_table(all_data, US_STOCKS, "米国株 全銘柄分析", 3000)
    print_portfolio_table(all_data, JP_STOCKS, "日本株 全銘柄分析", 3000)

    all_list = list(all_data.values())
    screened = screen_momentum_chimps(all_list)
    print_momentum_screening(screened, US_STOCKS, JP_STOCKS, top_n=15)

    reversal = screen_value_reversal(all_list)
    print_reversal_screening(reversal, US_STOCKS, JP_STOCKS, top_n=10)

    # アクションリスト
    print_header("🎯 今日のアクション優先リスト")
    from tabulate import tabulate
    targets = [
        ("即打診",  "META",   "現値で打診300万円  4/29決算前ラストチャンス"),
        ("即打診",  "6976.T", "太陽誘電 現値-5%指値  AIサーバーMLCC"),
        ("指値設定", "NVDA",   "$198以下 700万円  AI王者モメンタム"),
        ("指値設定", "AVGO",   "$394以下 500万円  AI半導体2番手"),
        ("指値設定", "6857.T", "25,650円以下 500万円  4/27決算注意"),
        ("指値設定", "5803.T", "5,700円以下 400万円  5/14決算前"),
        ("指値設定", "ARM",    "$223以下 200万円  CPU相場最終受益者"),
        ("指値設定", "AMD",    "$329以下 100万円  5/5決算前"),
    ]
    rows = []
    for action, ticker, note in targets:
        d = all_data.get(ticker)
        price_str = format_price(d["price"], d["currency"]) if d else "-"
        color = Fore.GREEN if action == "即打診" else Fore.YELLOW
        rows.append([color + action + Style.RESET_ALL, ticker, price_str, note])
    print(tabulate(rows, headers=["アクション", "銘柄", "現在値", "内容"], tablefmt="simple"))

    if save_to_csv:
        save_csv(all_data, US_STOCKS, JP_STOCKS)

    print("\n" + "="*80)
    print("  ⚠️  投資判断はご自身でお願いします。本プログラムは情報提供目的です。")
    print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="モメンタムチンパン 株式スクリーナー")
    parser.add_argument("--quick",  action="store_true", help="クイックモード (スクリーニングのみ)")
    parser.add_argument("--csv",    action="store_true", help="CSV出力を追加")
    parser.add_argument("--custom", nargs="+", help="追加銘柄 例: --custom TSLA SMCI 7203.T")
    parser.add_argument("--budget", type=int, default=3000, help="予算(万円) デフォルト3000")
    args = parser.parse_args()

    print(Fore.YELLOW + """
========================================================
   Momentum Chimp - Stock Screener v1.0
   Momentum Chimp Kabu Screener
========================================================
""" + Style.RESET_ALL)

    # カスタム銘柄追加
    if args.custom:
        us_extra = [t for t in args.custom if not t.endswith(".T")]
        jp_extra = [t for t in args.custom if t.endswith(".T")]
        add_custom_tickers(us_extra, jp_extra)
        print(f"  カスタム銘柄追加: {args.custom}")

    all_tickers = list(US_STOCKS.keys()) + list(JP_STOCKS.keys())
    print(f"  データ取得中... ({len(all_tickers)}銘柄)")
    print("  ※ yfinance経由 リアルタイム/15分遅延\n")

    all_data: dict = {}
    for i, ticker in enumerate(all_tickers):
        print(f"  [{i+1:2d}/{len(all_tickers)}] {ticker:<12}", end="\r")
        data = fetch_stock_data(ticker)
        if data:
            all_data[ticker] = data
        time.sleep(0.3)

    print(f"  データ取得完了: {len(all_data)}/{len(all_tickers)} 銘柄    \n")

    if args.quick:
        quick_mode(all_data)
    else:
        full_mode(all_data, save_to_csv=args.csv)


if __name__ == "__main__":
    main()
