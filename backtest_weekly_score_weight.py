"""
backtest_weekly_score_weight.py

スコア比例配分（score-weighted）の週次バックテスト。
均等配分の backtest_weekly.py と比較するために作成。

- スコアが高い銘柄ほど多くの資金を投下する
- pf_return = Σ(weight_i * return_i)  where weight_i = score_i / Σscore
"""

import pandas as pd
import yfinance as yf
import numpy as np
from colorama import Fore, Style, init
from tabulate import tabulate
import warnings
import time
import argparse

warnings.filterwarnings("ignore")
init(autoreset=True)

from universe_screener import get_universe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-us",    type=int, default=10)
    parser.add_argument("--top-jp",    type=int, default=6)
    parser.add_argument("--benchmark", type=str, default="SPY")
    args = parser.parse_args()

    top_us    = args.top_us
    top_jp    = args.top_jp
    bm_ticker = args.benchmark

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (Score-Weighted) v1.0")
    print("   スコア比例配分 × 週次リバランス")
    print("========================================================\n" + Style.RESET_ALL)

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers  = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 週足データ(過去2年)一括ダウンロード中...")
    download_tickers = tickers + [bm_ticker]
    chunk_size = 500
    all_close  = {}

    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i + chunk_size]
        try:
            raw = yf.download(chunk, period="2y", interval="1wk", progress=False)
            if "Close" in raw.columns:
                close_part = raw["Close"]
                if isinstance(close_part, pd.Series):
                    all_close[chunk[0]] = close_part
                else:
                    for t in close_part.columns:
                        all_close[t] = close_part[t]
        except Exception as e:
            print(f"Download error: {e}")
        time.sleep(0.5)

    close_df = pd.DataFrame(all_close).dropna(how="all")
    if close_df.empty:
        print("データ取得失敗。")
        return

    weeks = close_df.index.tolist()
    print(f"  取得データ期間: {weeks[0].date()} 〜 {weeks[-1].date()} ({len(weeks)}週間)")

    start_idx      = 26
    weekly_results = []

    print("\n[3] バックテスト開始 (スコア比例配分)...")

    for i in range(start_idx, len(weeks) - 1):
        current_week = weeks[i]
        next_week    = weeks[i + 1]

        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            s = close_df[ticker].iloc[:i + 1].dropna()
            if len(s) < 27:
                continue
            try:
                p_now = float(s.iloc[-1])
                p_1m  = float(s.iloc[-5])
                p_3m  = float(s.iloc[-14])
                p_6m  = float(s.iloc[-27])
                if p_1m == 0 or p_3m == 0 or p_6m == 0:
                    continue
                raw_score = (((p_now/p_1m)-1)*100 * 0.4 +
                             ((p_now/p_3m)-1)*100 * 0.3 +
                             ((p_now/p_6m)-1)*100 * 0.2)
                scores.append({"ticker": ticker, "market": universe[ticker], "score": raw_score})
            except Exception:
                continue

        if not scores:
            continue

        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top   = score_df[score_df["market"] == "US"].head(top_us)
        jp_top   = score_df[score_df["market"] == "JP"].head(top_jp)
        deck     = pd.concat([us_top, jp_top])

        # スコアが負の銘柄は最低0.001ウェイトにして計算崩れを防ぐ
        deck = deck.copy()
        deck["score_clipped"] = deck["score"].clip(lower=0.001)
        total_score = deck["score_clipped"].sum()

        weighted_return = 0.0
        valid_total_weight = 0.0

        for _, row in deck.iterrows():
            t = row["ticker"]
            if t not in close_df.columns:
                continue
            p_T  = close_df[t].loc[current_week]
            p_T1 = close_df[t].loc[next_week]
            if pd.notna(p_T) and pd.notna(p_T1) and p_T > 0:
                ret    = (p_T1 / p_T) - 1.0
                weight = row["score_clipped"] / total_score
                weighted_return    += weight * ret
                valid_total_weight += weight

        # ウェイトが1未満（データ欠損で一部銘柄が入らなかった場合）を正規化
        pf_return = weighted_return / valid_total_weight if valid_total_weight > 0 else 0.0

        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm_T  = close_df[bm_ticker].loc[current_week]
            bm_T1 = close_df[bm_ticker].loc[next_week]
            if pd.notna(bm_T) and pd.notna(bm_T1) and bm_T > 0:
                bm_return = (bm_T1 / bm_T) - 1.0

        weekly_results.append({
            "Week":      next_week.strftime("%Y-%m-%d"),
            "PF_Return": pf_return,
            "BM_Return": bm_return,
        })

    if not weekly_results:
        print("結果なし。")
        return

    res_df = pd.DataFrame(weekly_results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()

    # 月次集計
    res_df["Month"] = pd.to_datetime(res_df["Week"]).dt.to_period("M")
    monthly = []
    for month, g in res_df.groupby("Month"):
        start_pf = g["PF_Cum"].iloc[0] / (1.0 + g["PF_Return"].iloc[0])
        end_pf   = g["PF_Cum"].iloc[-1]
        start_bm = g["BM_Cum"].iloc[0] / (1.0 + g["BM_Return"].iloc[0])
        end_bm   = g["BM_Cum"].iloc[-1]
        monthly.append({
            "Month":     str(month),
            "Trades":    len(g),
            "PF_Return": f"{(end_pf/start_pf - 1)*100:+.2f}%",
            "BM_Return": f"{(end_bm/start_bm - 1)*100:+.2f}%",
            "PF_Cum":    f"{end_pf*100:.1f}%",
            "BM_Cum":    f"{end_bm*100:.1f}%",
        })

    print("\n====================================================================================================")
    print("  🐒 バックテスト月次集計 (スコア比例配分 / 週次リバランス)")
    print("====================================================================================================")
    print(tabulate(monthly, headers="keys", tablefmt="simple", showindex=False))

    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]

    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (Score-Weighted)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Week'].iloc[0]} 〜 {res_df['Week'].iloc[-1]} ({len(res_df)}週間)")
    print(f"  モメンタムチンパン累積リターン: "
          f"{Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf-1)*100:+.2f}%{Style.RESET_ALL} "
          f"(資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: "
          f"{Fore.GREEN if final_bm > 1 else Fore.RED}{(final_bm-1)*100:+.2f}%{Style.RESET_ALL} "
          f"(資産 {final_bm:.2f}倍)")
    print("========================================================")

    if final_pf > final_bm:
        print(Fore.YELLOW + f"  🔥 ベンチマークを {(final_pf-final_bm)*100:+.2f}% アウトパフォーム！" + Style.RESET_ALL)
    else:
        print(Fore.RED + f"  💀 ベンチマークに {(final_bm-final_pf)*100:+.2f}% 負けました" + Style.RESET_ALL)

    print(Fore.CYAN + "\n  📊 均等配分との比較" + Style.RESET_ALL)
    print(f"  スコア比例配分（今回）: {(final_pf-1)*100:+.2f}% (資産 {final_pf:.2f}倍)")
    print(f"  均等配分     （参考）: +384.57% (資産 4.85倍)")


if __name__ == "__main__":
    main()
