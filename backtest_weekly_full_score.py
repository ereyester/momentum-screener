"""
backtest_weekly_full_score.py

本番スクリーナー（universe_screener.py）と全く同じスコア計算式を使った週次バックテスト。
- 日次データをダウンロード（RSI・出来高・ATH・MA計算に必要）
- 5営業日ごとにリバランス（週次）
- スコア計算: RSI / ATH / 出来高急増 / MA / リターンを組み合わせた本番式
- リターン計算: 週末終値 → 翌週末終値
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


def calc_full_score(s: pd.Series, vol_s: pd.Series | None, idx: int) -> float:
    """
    本番スクリーナーと同じスコア計算式。
    s   : 終値の時系列（ idx+1 まで使用）
    vol_s: 出来高の時系列（Noneでもよい）
    idx : 現在のインデックス（このインデックスまでのデータを使用）
    """
    s = s.iloc[:idx + 1].dropna()
    if len(s) < 21:
        return None

    price   = float(s.iloc[-1])
    prev    = float(s.iloc[-2])
    day_chg = (price - prev) / prev * 100

    high_52w = float(s.max())
    from_ath = (price - high_52w) / high_52w * 100

    ret_1m = ((price / float(s.iloc[-21])) - 1) * 100 if len(s) >= 21 else 0.0
    ret_3m = ((price / float(s.iloc[-63])) - 1) * 100 if len(s) >= 63 else 0.0

    # RSI（14日）
    delta = s.diff()
    gain  = delta.where(delta > 0, 0.0).tail(14).mean()
    loss  = (-delta.where(delta < 0, 0.0)).tail(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss)) if loss and loss != 0 else 50.0

    # MA50, MA200
    ma50  = float(s.tail(50).mean())  if len(s) >= 50  else 0.0
    ma200 = float(s.tail(200).mean()) if len(s) >= 200 else 0.0

    # 出来高比率
    vol_ratio = 1.0
    if vol_s is not None:
        v = vol_s.iloc[:idx + 1].dropna()
        if len(v) >= 20:
            vol_avg = float(v.tail(20).mean())
            vol_now = float(v.iloc[-1])
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

    # ---- 本番スクリーナーと同一のスコア式 ----
    score = 0

    # 1Mリターン（最重要 40点）
    if ret_1m >= 30:   score += 40
    elif ret_1m >= 20: score += 30
    elif ret_1m >= 10: score += 20
    elif ret_1m >= 5:  score += 10
    elif ret_1m < -10: score -= 20

    # ATH近さ（20点）
    if from_ath >= -3:    score += 20
    elif from_ath >= -8:  score += 14
    elif from_ath >= -15: score += 8
    elif from_ath <= -30: score -= 10

    # RSI（15点）
    if 60 <= rsi <= 80:  score += 15
    elif rsi > 80:       score += 8
    elif rsi < 40:       score -= 10

    # 3Mリターン（15点）
    if ret_3m >= 40:   score += 15
    elif ret_3m >= 20: score += 10
    elif ret_3m >= 10: score += 5
    elif ret_3m < -10: score -= 5

    # 出来高急増（5点）
    if vol_ratio >= 2.0:   score += 5
    elif vol_ratio >= 1.5: score += 3

    # MA上（5点）
    if ma50  > 0 and price > ma50:  score += 3
    if ma200 > 0 and price > ma200: score += 2

    # 当日騰落（5点）
    if day_chg >= 5:    score += 5
    elif day_chg >= 2:  score += 3
    elif day_chg <= -3: score -= 3

    return score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-us", type=int, default=10)
    parser.add_argument("--top-jp", type=int, default=6)
    parser.add_argument("--benchmark", type=str, default="SPY")
    args = parser.parse_args()

    top_us   = args.top_us
    top_jp   = args.top_jp
    bm_ticker = args.benchmark

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (Full Score) v1.0")
    print("   本番スクリーナー式スコア × 週次リバランス")
    print("   RSI / ATH / 出来高 / MA / リターン を統合したスコア")
    print("========================================================\n" + Style.RESET_ALL)

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers  = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 日次データ（過去2年）一括ダウンロード中... (数分かかります)")
    download_tickers = tickers + [bm_ticker]
    chunk_size = 500
    all_close  = {}
    all_volume = {}

    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i + chunk_size]
        try:
            raw = yf.download(chunk, period="2y", interval="1d", progress=False)
            if "Close" in raw.columns and "Volume" in raw.columns:
                cp = raw["Close"]
                vp = raw["Volume"]
                if isinstance(cp, pd.Series):
                    all_close[chunk[0]]  = cp
                    all_volume[chunk[0]] = vp
                else:
                    for t in cp.columns:
                        all_close[t]  = cp[t]
                        all_volume[t] = vp[t] if t in vp.columns else pd.Series(dtype=float)
        except Exception as e:
            print(f"  Error chunk {i}: {e}")
        time.sleep(0.5)

    close_df  = pd.DataFrame(all_close).dropna(how="all")
    volume_df = pd.DataFrame(all_volume).dropna(how="all")

    if close_df.empty:
        print("データ取得失敗。")
        return

    days = close_df.index.tolist()
    print(f"  取得期間: {days[0].date()} 〜 {days[-1].date()} ({len(days)}営業日)")

    # スコア計算に200日MAが必要なので200日後から開始
    start_idx = 210
    results   = []

    print("\n[3] バックテスト開始（本番スコア式）...")

    for i in range(start_idx, len(days) - 5, 5):
        trade_day = days[i]
        next_day  = days[i + 5]

        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            s = close_df[ticker]
            vol_s = volume_df[ticker] if ticker in volume_df.columns else None
            sc = calc_full_score(s, vol_s, i)
            if sc is None:
                continue
            scores.append({"ticker": ticker, "market": universe[ticker], "score": sc})

        if not scores:
            continue

        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top   = score_df[score_df["market"] == "US"].head(top_us)["ticker"].tolist()
        jp_top   = score_df[score_df["market"] == "JP"].head(top_jp)["ticker"].tolist()
        deck     = us_top + jp_top

        pf_returns = []
        for t in deck:
            if t in close_df.columns:
                p0 = close_df[t].loc[trade_day]
                p1 = close_df[t].loc[next_day]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    pf_returns.append((p1 / p0) - 1.0)

        pf_return = np.mean(pf_returns) if pf_returns else 0.0

        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm0 = close_df[bm_ticker].loc[trade_day]
            bm1 = close_df[bm_ticker].loc[next_day]
            if pd.notna(bm0) and pd.notna(bm1) and bm0 > 0:
                bm_return = (bm1 / bm0) - 1.0

        results.append({
            "Trade_Date": trade_day.strftime("%Y-%m-%d"),
            "PF_Return":  pf_return,
            "BM_Return":  bm_return,
            "Top_US":     ", ".join(us_top[:4]),
            "Top_JP":     ", ".join([t.replace(".T", "") for t in jp_top[:3]]),
        })

    if not results:
        print("結果なし。")
        return

    res_df = pd.DataFrame(results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()

    # 月次集計
    res_df["Month"] = pd.to_datetime(res_df["Trade_Date"]).dt.to_period("M")
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
    print("  🐒 バックテスト月次集計 (本番スコア式 / 週次リバランス / ロスカットなし)")
    print("====================================================================================================")
    print(tabulate(monthly, headers="keys", tablefmt="simple", showindex=False))

    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]

    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (Full Score)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Trade_Date'].iloc[0]} 〜 {res_df['Trade_Date'].iloc[-1]}")
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

    print(Fore.CYAN + "\n  📊 シンプルスコア式との比較" + Style.RESET_ALL)
    print(f"  本番スコア式（今回）:         {(final_pf-1)*100:+.2f}% (資産 {final_pf:.2f}倍)")
    print(f"  シンプル加重平均式（参考）:   +384.57% (資産 4.85倍)")


if __name__ == "__main__":
    main()
