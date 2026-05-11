import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime
from colorama import Fore, Style, init
from tabulate import tabulate
import warnings
import time

warnings.filterwarnings("ignore")
init(autoreset=True)

import argparse
from universe_screener import get_universe

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-us", type=int, default=10, help="Number of US stocks")
    parser.add_argument("--top-jp", type=int, default=6, help="Number of JP stocks")
    parser.add_argument("--benchmark", type=str, default="SPY", help="Benchmark ticker (e.g. SPY, ^N225)")
    args = parser.parse_args()

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester v1.0")
    print("   Monthly Rebalancing, No Stop-Loss, Past 2 Years")
    print("========================================================\n" + Style.RESET_ALL)

    top_us = args.top_us
    top_jp = args.top_jp
    bm_ticker = args.benchmark
    top_total = top_us + top_jp

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 月足データ(過去2年)一括ダウンロード中... (これには数分かかる場合があります)")
    download_tickers = tickers + [bm_ticker]
    
    chunk_size = 500
    all_close = {}
    
    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i+chunk_size]
        try:
            raw = yf.download(chunk, period="2y", interval="1mo", progress=False)
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

    months = close_df.index.tolist()
    if len(months) < 13:
        print("データ期間が短すぎます（最低1年の過去データ＋バックテスト期間が必要です）")
        return

    print(f"  取得データ期間: {months[0].date()} 〜 {months[-1].date()} ({len(months)}ヶ月)")

    monthly_results = []
    start_idx = 6 
    
    print("\n[3] バックテスト開始...")
    
    for i in range(start_idx, len(months) - 1):
        current_month = months[i]
        next_month    = months[i+1]
        
        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            
            s = close_df[ticker].iloc[:i+1].dropna()
            if len(s) < 7:
                continue
                
            try:
                p_now = float(s.iloc[-1])
                p_1m  = float(s.iloc[-2])
                p_3m  = float(s.iloc[-4])
                p_6m  = float(s.iloc[-7])
                
                if p_1m == 0 or p_3m == 0 or p_6m == 0: continue
                
                ret_1m = ((p_now / p_1m) - 1) * 100
                ret_3m = ((p_now / p_3m) - 1) * 100
                ret_6m = ((p_now / p_6m) - 1) * 100
                
                raw_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                market = universe[ticker]
                
                scores.append({
                    "ticker": ticker,
                    "market": market,
                    "score": raw_score,
                    "price_T": p_now
                })
            except Exception:
                continue
                
        if not scores: continue
        
        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top = score_df[score_df["market"] == "US"].head(top_us)
        jp_top = score_df[score_df["market"] == "JP"].head(top_jp)
        deck = pd.concat([us_top, jp_top])
        
        deck_tickers = deck["ticker"].tolist()
        next_month_returns = []
        
        for t in deck_tickers:
            if t in close_df.columns:
                p_T = close_df[t].loc[current_month]
                p_T1 = close_df[t].loc[next_month]
                if pd.notna(p_T) and pd.notna(p_T1) and p_T > 0:
                    ret = (p_T1 / p_T) - 1.0
                    next_month_returns.append(ret)
        
        pf_return = np.mean(next_month_returns) if next_month_returns else 0.0
        
        spy_return = 0.0
        if bm_ticker in close_df.columns:
            spy_T = close_df[bm_ticker].loc[current_month]
            spy_T1 = close_df[bm_ticker].loc[next_month]
            if pd.notna(spy_T) and pd.notna(spy_T1) and spy_T > 0:
                spy_return = (spy_T1 / spy_T) - 1.0
                
        monthly_results.append({
            "Month": next_month.strftime("%Y-%m"),
            "PF_Return": pf_return,
            "BM_Return": spy_return,
            "Top_US": ", ".join(us_top["ticker"].tolist()[:3]) + ("..." if len(us_top)>0 else ""),
            "Top_JP": ", ".join([t.replace(".T", "") for t in jp_top["ticker"].tolist()[:3]]) + ("..." if len(jp_top)>0 else "")
        })
        
    if not monthly_results:
        print("バックテスト結果がありません。")
        return
        
    res_df = pd.DataFrame(monthly_results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()
    
    display_df = res_df.copy()
    display_df["PF_Return"] = (display_df["PF_Return"] * 100).map("{:+.2f}%".format)
    display_df["BM_Return"] = (display_df["BM_Return"] * 100).map("{:+.2f}%".format)
    display_df["PF_Cum"] = (display_df["PF_Cum"] * 100).map("{:.1f}%".format)
    display_df["BM_Cum"] = (display_df["BM_Cum"] * 100).map("{:.1f}%".format)
    
    print("\n====================================================================================================")
    print("  🐒 バックテスト月次推移 (毎月末リバランス / ロスカットなし)")
    print("====================================================================================================")
    print(tabulate(display_df, headers="keys", tablefmt="simple", showindex=False))
    
    final_pf = res_df["PF_Cum"].iloc[-1]
    final_spy = res_df["BM_Cum"].iloc[-1]
    
    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Month'].iloc[0]} 〜 {res_df['Month'].iloc[-1]} ({len(res_df)}ヶ月間)")
    print(f"  モメンタムチンパン累積リターン: {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: {Fore.GREEN if final_spy > 1 else Fore.RED}{(final_spy - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_spy:.2f}倍)")
    print("========================================================")
    
    if final_pf > final_spy:
        outperform = (final_pf - final_spy) * 100
        print(Fore.YELLOW + f"  🔥 モメンタムチンパンがベンチマークを {outperform:+.2f}% アウトパフォームしました！" + Style.RESET_ALL)

if __name__ == "__main__":
    main()
