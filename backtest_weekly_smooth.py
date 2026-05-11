import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime
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
    parser.add_argument("--top-us",    type=int,   default=10,   help="Number of US stocks")
    parser.add_argument("--top-jp",    type=int,   default=6,    help="Number of JP stocks")
    parser.add_argument("--benchmark", type=str,   default="SPY",help="Benchmark ticker")
    parser.add_argument("--max-score", type=float, default=None, help="スコア上限（これを超える銘柄を除外）。例: --max-score 150")
    parser.add_argument("--skip-jp",   type=int,   default=0,    help="Number of top JP stocks to skip (e.g. 2 means starting from 3rd)")
    parser.add_argument("--skip-us",   type=int,   default=0,    help="Number of top US stocks to skip")
    args = parser.parse_args()

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (Smooth Momentum) v1.0")
    print("   Weekly Rebalancing, Smoothness (R^2) Adjusted, No Stop-Loss")
    if args.max_score:
        print(f"   ⚠️  スコア上限フィルター: score > {args.max_score} の銘柄を除外")
    print("========================================================\n" + Style.RESET_ALL)

    top_us    = args.top_us
    top_jp    = args.top_jp
    bm_ticker = args.benchmark
    max_score = args.max_score
    top_total = top_us + top_jp

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 週足データ(過去2年)一括ダウンロード中... (これには数分かかる場合があります)")
    download_tickers = tickers + [bm_ticker]
    
    chunk_size = 500
    all_close = {}
    
    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i+chunk_size]
        try:
            # 週足データを取得
            raw = yf.download(chunk, period="2y", interval="1wk", progress=False)
            if "Close" in raw.columns:
                close_part = raw["Close"]
                if isinstance(close_part, pd.Series):
                    all_close[chunk[0]] = close_part
                else:
                    for t in close_part.columns:
                        all_close[t] = close_part[t]
        except Exception as e:
            print(f"Download error on chunk {i}: {e}")
        time.sleep(0.5)

    close_df = pd.DataFrame(all_close)
    close_df = close_df.dropna(how="all")

    if close_df.empty:
        print("データ取得に失敗しました。")
        return

    weeks = close_df.index.tolist()
    if len(weeks) < 30:
        print("データ期間が短すぎます（最低半年以上の過去データ＋バックテスト期間が必要です）")
        return

    print(f"  取得データ期間: {weeks[0].date()} 〜 {weeks[-1].date()} ({len(weeks)}週間)")

    weekly_results = []
    # 過去6ヶ月（約26週）のデータがスコア計算に必要なので、開始インデックスをずらす
    start_idx = 26 
    
    print("\n[3] バックテスト開始...")
    
    for i in range(start_idx, len(weeks) - 1):
        current_week = weeks[i]
        next_week    = weeks[i+1]
        
        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            
            s = close_df[ticker].iloc[:i+1].dropna()
            if len(s) < 27:
                continue
                
            try:
                p_now = float(s.iloc[-1])
                p_1m  = float(s.iloc[-5])  # 約4週間前
                p_3m  = float(s.iloc[-14]) # 約13週間前
                p_6m  = float(s.iloc[-27]) # 約26週間前
                
                if p_1m == 0 or p_3m == 0 or p_6m == 0: continue
                
                ret_1m = ((p_now / p_1m) - 1) * 100
                ret_3m = ((p_now / p_3m) - 1) * 100
                ret_6m = ((p_now / p_6m) - 1) * 100
                
                raw_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                
                # 直近3ヶ月と1ヶ月の「滑らかさ（R^2）」を計算
                past_14w = s.iloc[-14:]
                if len(past_14w) == 14 and (past_14w > 0).all():
                    y3 = np.log(past_14w.values)
                    x3 = np.arange(len(y3))
                    slope3, intercept3 = np.polyfit(x3, y3, 1)
                    ss_tot3 = np.sum((y3 - np.mean(y3))**2)
                    r2_3m = 1 - (np.sum((y3 - (slope3 * x3 + intercept3))**2) / ss_tot3) if ss_tot3 > 0 else 0
                    
                    past_5w = s.iloc[-5:]
                    y1 = np.log(past_5w.values)
                    x1 = np.arange(len(y1))
                    slope1, intercept1 = np.polyfit(x1, y1, 1)
                    ss_tot1 = np.sum((y1 - np.mean(y1))**2)
                    r2_1m = 1 - (np.sum((y1 - (slope1 * x1 + intercept1))**2) / ss_tot1) if ss_tot1 > 0 else 0
                    
                    # 1ヶ月と3ヶ月の滑らかさを平均
                    smoothness = (r2_1m + r2_3m) / 2.0
                    
                    # スコアに滑らかさを掛ける（マイナススコアの場合はさらに下がるように、プラスの場合は綺麗な右肩上がりを優遇）
                    if raw_score > 0:
                        final_score = raw_score * (smoothness ** 2) # 滑らかでないものは大きく減点
                    else:
                        final_score = raw_score
                else:
                    final_score = raw_score * 0.1 # データ不足
                
                market = universe[ticker]
                
                scores.append({
                    "ticker": ticker,
                    "market": market,
                    "score": final_score,
                    "price_T": p_now
                })
            except Exception:
                continue
                
        if not scores: continue
        
        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        # スコア上限フィルター（異常値除外）
        if max_score is not None:
            score_df = score_df[score_df["score"] <= max_score]
        us_top = score_df[score_df["market"] == "US"].iloc[args.skip_us:args.skip_us+top_us]
        jp_top = score_df[score_df["market"] == "JP"].iloc[args.skip_jp:args.skip_jp+top_jp]
        deck = pd.concat([us_top, jp_top])
        
        deck_tickers = deck["ticker"].tolist()
        next_week_returns = []
        
        for t in deck_tickers:
            if t in close_df.columns:
                p_T = close_df[t].loc[current_week]
                p_T1 = close_df[t].loc[next_week]
                if pd.notna(p_T) and pd.notna(p_T1) and p_T > 0:
                    ret = (p_T1 / p_T) - 1.0
                    next_week_returns.append(ret)
        
        pf_return = np.mean(next_week_returns) if next_week_returns else 0.0
        
        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm_T = close_df[bm_ticker].loc[current_week]
            bm_T1 = close_df[bm_ticker].loc[next_week]
            if pd.notna(bm_T) and pd.notna(bm_T1) and bm_T > 0:
                bm_return = (bm_T1 / bm_T) - 1.0
                
        weekly_results.append({
            "Week": next_week.strftime("%Y-%m-%d"),
            "PF_Return": pf_return,
            "BM_Return": bm_return,
            "Top_US": ", ".join(us_top["ticker"].tolist()),
            "Top_JP": ", ".join([t.replace(".T", "") for t in jp_top["ticker"].tolist()])
        })
        
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
    print("  🐒 バックテスト週次推移 (毎週末リバランス / ロスカットなし)")
    print("====================================================================================================")
    # 週次だと行数が多いため、全部表示する
    print(tabulate(display_df, headers="keys", tablefmt="simple", showindex=False))
    
    # CSVにフルリストを出力
    display_df.to_csv("weekly_positions.csv", index=False)
    print("\n[INFO] 毎週のポジション変化を 'weekly_positions.csv' に保存しました。")
    
    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]
    
    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (Weekly)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Week'].iloc[0]} 〜 {res_df['Week'].iloc[-1]} ({len(res_df)}週間)")
    print(f"  モメンタムチンパン累積リターン: {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: {Fore.GREEN if final_bm > 1 else Fore.RED}{(final_bm - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_bm:.2f}倍)")
    print("========================================================")
    
    if final_pf > final_bm:
        outperform = (final_pf - final_bm) * 100
        print(Fore.YELLOW + f"  🔥 モメンタムチンパンがベンチマークを {outperform:+.2f}% アウトパフォームしました！" + Style.RESET_ALL)
    else:
        underperform = (final_bm - final_pf) * 100
        print(Fore.RED + f"  💀 チンパンはベンチマークに {underperform:+.2f}% 負けました（往復ビンタの可能性大）" + Style.RESET_ALL)

if __name__ == "__main__":
    main()
