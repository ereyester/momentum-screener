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
    parser.add_argument("--top-us", type=int, default=10, help="上昇中US銘柄の最大保有数")
    parser.add_argument("--top-jp", type=int, default=6, help="上昇中JP銘柄の最大保有数")
    parser.add_argument("--rank-window", type=int, default=200,
                        help="考慮するUS銘柄の上位ランク範囲 (例:200=上位200位以内の銘柄のみ対象)")
    parser.add_argument("--jp-rank-window", type=int, default=300,
                        help="考慮するJP銘柄の上位ランク範囲")
    parser.add_argument("--benchmark", type=str, default="SPY", help="ベンチマーク")
    args = parser.parse_args()

    top_us = args.top_us
    top_jp = args.top_jp
    us_window = args.rank_window
    jp_window = args.jp_rank_window
    bm_ticker = args.benchmark

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (Rank Rising) v1.0")
    print("   Buy: rank climbing up  |  Sell: rank starts falling")
    print("========================================================\n" + Style.RESET_ALL)

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers = list(universe.keys())
    us_tickers = [t for t in tickers if universe[t] == "US"]
    jp_tickers = [t for t in tickers if universe[t] == "JP"]
    print(f"  US: {len(us_tickers)}銘柄 / JP: {len(jp_tickers)}銘柄")

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

    # ---- 毎週のランク計算 ----
    def calc_ranks(week_idx):
        """week_idxまでのデータでスコアを計算し、US/JPそれぞれのランクを返す"""
        us_scores = []
        jp_scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            s = close_df[ticker].iloc[:week_idx + 1].dropna()
            if len(s) < 27:
                continue
            try:
                p_now = float(s.iloc[-1])
                p_1m = float(s.iloc[-5])
                p_3m = float(s.iloc[-14])
                p_6m = float(s.iloc[-27])
                if p_1m == 0 or p_3m == 0 or p_6m == 0:
                    continue
                score = (((p_now / p_1m) - 1) * 40 +
                         ((p_now / p_3m) - 1) * 30 +
                         ((p_now / p_6m) - 1) * 20)
                if universe[ticker] == "US":
                    us_scores.append((ticker, score))
                else:
                    jp_scores.append((ticker, score))
            except Exception:
                continue

        # 高スコア順にソート→ランク付け (rank 1 = 最高)
        us_scores.sort(key=lambda x: -x[1])
        jp_scores.sort(key=lambda x: -x[1])

        us_rank = {t: rank + 1 for rank, (t, _) in enumerate(us_scores)}
        jp_rank = {t: rank + 1 for rank, (t, _) in enumerate(jp_scores)}

        return us_rank, jp_rank

    start_idx = 27  # ランク比較のため1週前のランクが必要なので+1
    portfolio = {}  # ticker -> entry_price (normalized)
    weekly_results = []

    print("\n[3] バックテスト開始 (ランク上昇戦略)...")

    prev_us_rank = None
    prev_jp_rank = None

    for i in range(start_idx - 1, len(weeks) - 1):
        current_week = weeks[i]
        next_week = weeks[i + 1]

        curr_us_rank, curr_jp_rank = calc_ranks(i)

        if prev_us_rank is None:
            prev_us_rank = curr_us_rank
            prev_jp_rank = curr_jp_rank
            continue

        # ---- ランク上昇度を計算 ----
        # rank_delta > 0 = 先週より今週のランクが上がった（数字が小さくなった = 順位UP）
        # rank_delta = prev_rank - curr_rank (正なら順位が上がった)

        # US：上位us_window位以内の銘柄のみ考慮、その中でランクが上昇中の銘柄を上昇幅順に並べる
        us_rising = []
        for t, curr_r in curr_us_rank.items():
            if curr_r > us_window:
                continue  # ランク圏外は無視
            prev_r = prev_us_rank.get(t, curr_r)  # 前週ランク（なければ同ランク扱い）
            delta = prev_r - curr_r  # 正=ランクアップ、負=ランクダウン
            us_rising.append((t, curr_r, delta))

        # JP同様
        jp_rising = []
        for t, curr_r in curr_jp_rank.items():
            if curr_r > jp_window:
                continue
            prev_r = prev_jp_rank.get(t, curr_r)
            delta = prev_r - curr_r
            jp_rising.append((t, curr_r, delta))

        # 「ランクが上昇中（delta > 0）」の銘柄を上昇幅順で並べてトップN選出
        us_candidates = sorted(
            [(t, r, d) for t, r, d in us_rising if d > 0],
            key=lambda x: -x[2]
        )[:top_us]
        jp_candidates = sorted(
            [(t, r, d) for t, r, d in jp_rising if d > 0],
            key=lambda x: -x[2]
        )[:top_jp]

        target_set = set([t for t, _, _ in us_candidates] + [t for t, _, _ in jp_candidates])

        current_held = set(portfolio.keys())

        # ---- 売り判断: ランクが下がり始めた保有銘柄を売る ----
        exits = set()
        for t in current_held:
            if universe[t] == "US":
                curr_r = curr_us_rank.get(t, 99999)
                prev_r = prev_us_rank.get(t, 99999)
            else:
                curr_r = curr_jp_rank.get(t, 99999)
                prev_r = prev_jp_rank.get(t, 99999)

            delta = prev_r - curr_r  # 負 = ランクが下がった
            if delta <= 0:  # ランクが下がり始めたら売り
                exits.add(t)

        new_entries = target_set - current_held
        holds = current_held - exits

        # 週間リターン計算（HOLD + EXIT 銘柄の今週のリターン）
        week_returns = []
        for t in list(holds) + list(exits):
            if t in close_df.columns:
                p0 = close_df[t].loc[current_week]
                p1 = close_df[t].loc[next_week]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    week_returns.append((p1 / p0) - 1.0)

        pf_return = np.mean(week_returns) if week_returns else 0.0

        # ポートフォリオ更新
        for t in exits:
            portfolio.pop(t, None)
        for t in new_entries:
            if t in close_df.columns:
                p = close_df[t].loc[next_week]
                if pd.notna(p) and p > 0:
                    portfolio[t] = p

        # ベンチマーク
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
            "PF_Size": len(portfolio),
            "New_Buy": ", ".join([f"{t}(+{d})" for t, _, d in us_candidates if t in new_entries] +
                                 [f"{t.replace('.T','')}(+{d})" for t, _, d in jp_candidates if t in new_entries]) or "-",
            "Sold": ", ".join([t if universe[t] == "US" else t.replace(".T", "") for t in exits]) or "-",
            "Hold_Count": len(holds),
        })

        # 次のループへ
        prev_us_rank = curr_us_rank
        prev_jp_rank = curr_jp_rank

    if not weekly_results:
        print("バックテスト結果がありません。")
        return

    res_df = pd.DataFrame(weekly_results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()

    display_df = res_df.copy()
    display_df["PF_Return"] = (display_df["PF_Return"] * 100).map("{:+.2f}%".format)
    display_df["BM_Return"] = (display_df["BM_Return"] * 100).map("{:+.2f}%".format)
    display_df["PF_Cum"] = (display_df["PF_Cum"] * 100).map("{:.1f}%".format)
    display_df["BM_Cum"] = (display_df["BM_Cum"] * 100).map("{:.1f}%".format)

    print("\n====================================================================================================")
    print("  🐒 ランク上昇戦略 週次推移  [Buy: ランク急上昇銘柄 / Sell: ランク下落開始]")
    print("====================================================================================================")
    print(tabulate(
        display_df[["Week", "PF_Return", "BM_Return", "PF_Size", "Hold_Count", "New_Buy", "Sold", "PF_Cum", "BM_Cum"]],
        headers=["Week", "PF_Ret", "BM_Ret", "Size", "Hold", "New_Buy (+rankΔ)", "Sold", "PF_Cum", "BM_Cum"],
        tablefmt="simple", showindex=False
    ))

    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]
    total_buys = res_df["New_Buy"].apply(lambda x: 0 if x == "-" else len(x.split(","))).sum()
    total_sells = res_df["Sold"].apply(lambda x: 0 if x == "-" else len(x.split(","))).sum()

    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (ランク上昇戦略)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Week'].iloc[0]} 〜 {res_df['Week'].iloc[-1]} ({len(res_df)}週間)")
    print(f"  総BUY回数: {total_buys}回  /  総SELL回数: {total_sells}回")
    print(f"  モメンタムチンパン累積リターン: {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: {Fore.GREEN if final_bm > 1 else Fore.RED}{(final_bm - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_bm:.2f}倍)")
    print("========================================================")

    if final_pf > final_bm:
        outperform = (final_pf - final_bm) * 100
        print(Fore.YELLOW + f"  🔥 ランク上昇戦略がベンチマークを {outperform:+.2f}% アウトパフォームしました！" + Style.RESET_ALL)
    else:
        underperform = (final_bm - final_pf) * 100
        print(Fore.RED + f"  💀 ベンチマークに {underperform:+.2f}% 負けました" + Style.RESET_ALL)

    print(Fore.CYAN + "\n  📊 比較サマリー" + Style.RESET_ALL)
    print(f"  ランク上昇戦略 (今回):        {(final_pf - 1.0)*100:+.2f}% (資産 {final_pf:.2f}倍)")
    print(f"  ランク上位ホールド戦略 (参考): +313.56% (資産 4.14倍)")
    print(f"  週次全とっかえ戦略 (参考):    +384.57% (資産 4.85倍)")


if __name__ == "__main__":
    main()
