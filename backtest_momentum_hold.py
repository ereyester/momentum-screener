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
    parser.add_argument("--top-us", type=int, default=10, help="Number of US stocks in ranking")
    parser.add_argument("--top-jp", type=int, default=6, help="Number of JP stocks in ranking")
    parser.add_argument("--benchmark", type=str, default="SPY", help="Benchmark ticker")
    args = parser.parse_args()

    top_us = args.top_us
    top_jp = args.top_jp
    bm_ticker = args.benchmark

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (HOLD Strategy) v1.0")
    print("   Buy on rank entry, Hold while ranked, Sell on rank exit")
    print("========================================================\n" + Style.RESET_ALL)

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 週足データ(過去2年)一括ダウンロード中...")
    download_tickers = tickers + [bm_ticker]

    chunk_size = 500
    all_close = {}

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
        print("データ取得に失敗しました。")
        return

    weeks = close_df.index.tolist()
    print(f"  取得データ期間: {weeks[0].date()} 〜 {weeks[-1].date()} ({len(weeks)}週間)")

    # ---- ホールド戦略のメインループ ----
    # portfolio: {ticker: cost_price}  (保有銘柄と取得単価)
    portfolio = {}  # ticker -> entry_price (per unit, normalized to 1.0 at entry)
    portfolio_value = 1.0  # ポートフォリオ全体の評価額（最初は1.0）

    start_idx = 26
    weekly_results = []

    print("\n[3] バックテスト開始 (ホールド戦略)...\n")

    for i in range(start_idx, len(weeks) - 1):
        current_week = weeks[i]
        next_week = weeks[i + 1]

        # --- スコア計算 ---
        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            s = close_df[ticker].iloc[:i + 1].dropna()
            if len(s) < 27:
                continue
            try:
                p_now = float(s.iloc[-1])
                p_1m = float(s.iloc[-5])
                p_3m = float(s.iloc[-14])
                p_6m = float(s.iloc[-27])
                if p_1m == 0 or p_3m == 0 or p_6m == 0:
                    continue
                ret_1m = ((p_now / p_1m) - 1) * 100
                ret_3m = ((p_now / p_3m) - 1) * 100
                ret_6m = ((p_now / p_6m) - 1) * 100
                raw_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                market = universe[ticker]
                scores.append({"ticker": ticker, "market": market, "score": raw_score})
            except Exception:
                continue

        if not scores:
            continue

        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top = set(score_df[score_df["market"] == "US"].head(top_us)["ticker"].tolist())
        jp_top = set(score_df[score_df["market"] == "JP"].head(top_jp)["ticker"].tolist())
        target_set = us_top | jp_top  # 今週の上位銘柄セット

        current_held = set(portfolio.keys())  # 現在の保有銘柄セット

        # --- 差分計算 ---
        new_entries = target_set - current_held   # 新規買い
        exits = current_held - target_set          # 売却
        holds = current_held & target_set          # 継続ホールド

        # --- 週間リターンを個別に計算（HOLDと新規ENTRYを分けて計上）---
        # HOLD銘柄の今週のリターン（週初→週末）
        hold_returns = []
        for t in holds:
            if t in close_df.columns:
                p0 = close_df[t].loc[current_week]
                p1 = close_df[t].loc[next_week]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    hold_returns.append((p1 / p0) - 1.0)

        # EXIT銘柄の今週のリターン（売却確定）
        exit_returns = []
        for t in exits:
            if t in close_df.columns:
                p0 = close_df[t].loc[current_week]
                p1 = close_df[t].loc[next_week]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    exit_returns.append((p1 / p0) - 1.0)

        # NEW ENTRY銘柄は今週末に買うため、今週のリターンへの寄与はなし
        # ただし次週以降にリターンが発生する

        # ポートフォリオの今週のリターン = 保有銘柄（HOLD + EXIT）の均等ウェイト平均
        # ※EXIT銘柄は今週は保有しているので今週のリターンに入る
        all_this_week = list(holds) + list(exits)
        week_returns_all = hold_returns + exit_returns
        pf_return = np.mean(week_returns_all) if week_returns_all else 0.0

        # ポートフォリオ全体の評価額を更新
        portfolio_value *= (1.0 + pf_return)

        # 売却後に新規エントリーをポートフォリオに追加
        for t in exits:
            del portfolio[t]
        for t in new_entries:
            if t in close_df.columns:
                p = close_df[t].loc[next_week]  # 次週の始値（週末引値）で購入
                if pd.notna(p) and p > 0:
                    portfolio[t] = p

        # ベンチマークリターン
        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm0 = close_df[bm_ticker].loc[current_week]
            bm1 = close_df[bm_ticker].loc[next_week]
            if pd.notna(bm0) and pd.notna(bm1) and bm0 > 0:
                bm_return = (bm1 / bm0) - 1.0

        weekly_results.append({
            "Week": next_week.strftime("%Y-%m-%d"),
            "PF_Return": pf_return,
            "BM_Return": bm_return,
            "Portfolio_Size": len(portfolio),
            "New_Buy": ", ".join(sorted(new_entries)) if new_entries else "-",
            "Sold": ", ".join(sorted(exits)) if exits else "-",
            "Hold_Count": len(holds),
        })

    if not weekly_results:
        print("バックテスト結果がありません。")
        return

    res_df = pd.DataFrame(weekly_results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()

    # 表示用フォーマット
    display_df = res_df.copy()
    display_df["PF_Return"] = (display_df["PF_Return"] * 100).map("{:+.2f}%".format)
    display_df["BM_Return"] = (display_df["BM_Return"] * 100).map("{:+.2f}%".format)
    display_df["PF_Cum"] = (display_df["PF_Cum"] * 100).map("{:.1f}%".format)
    display_df["BM_Cum"] = (display_df["BM_Cum"] * 100).map("{:.1f}%".format)

    print("====================================================================================================")
    print("  🐒 モメンタムホールド戦略 週次推移")
    print("  [新規BUY = ランク入り銘柄, SELL = ランク落ち銘柄, HOLD = ランク維持]")
    print("====================================================================================================")
    print(tabulate(
        display_df[["Week", "PF_Return", "BM_Return", "Portfolio_Size", "Hold_Count", "New_Buy", "Sold", "PF_Cum", "BM_Cum"]],
        headers=["Week", "PF_Ret", "BM_Ret", "PF_Size", "Hold", "New_Buy", "Sold", "PF_Cum", "BM_Cum"],
        tablefmt="simple",
        showindex=False
    ))

    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]

    # 売買回数カウント
    total_buys = res_df["New_Buy"].apply(lambda x: 0 if x == "-" else len(x.split(","))).sum()
    total_sells = res_df["Sold"].apply(lambda x: 0 if x == "-" else len(x.split(","))).sum()

    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (ホールド戦略)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Week'].iloc[0]} 〜 {res_df['Week'].iloc[-1]} ({len(res_df)}週間)")
    print(f"  総BUY回数 (新規エントリー): {total_buys}回")
    print(f"  総SELL回数 (ランクアウト売却): {total_sells}回")
    print(f"  モメンタムチンパン累積リターン: {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: {Fore.GREEN if final_bm > 1 else Fore.RED}{(final_bm - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_bm:.2f}倍)")
    print("========================================================")

    if final_pf > final_bm:
        outperform = (final_pf - final_bm) * 100
        print(Fore.YELLOW + f"  🔥 モメンタムチンパンがベンチマークを {outperform:+.2f}% アウトパフォームしました！" + Style.RESET_ALL)
    else:
        underperform = (final_bm - final_pf) * 100
        print(Fore.RED + f"  💀 チンパンはベンチマークに {underperform:+.2f}% 負けました" + Style.RESET_ALL)

    # 比較サマリー
    print(Fore.CYAN + "\n  📊 参考：既存の週次全とっかえ戦略との比較" + Style.RESET_ALL)
    print(f"  週次ホールド戦略 (今回):    {(final_pf - 1.0)*100:+.2f}% (資産 {final_pf:.2f}倍)")
    print(f"  週次全とっかえ戦略 (参考): +384.57% (資産 4.85倍)")
    print("  ※ 売買回数の差: ホールド戦略は全とっかえより大幅に少ない取引回数")


if __name__ == "__main__":
    main()
