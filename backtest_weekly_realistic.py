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
    parser.add_argument("--top-us", type=int, default=10, help="Number of US stocks")
    parser.add_argument("--top-jp", type=int, default=6, help="Number of JP stocks")
    parser.add_argument("--benchmark", type=str, default="SPY", help="Benchmark ticker (e.g. SPY, ^N225)")
    args = parser.parse_args()

    print(Fore.YELLOW + "========================================================")
    print("   Momentum Chimp Backtester (Realistic Weekly) v1.0")
    print("   Score on Thursday Close, Trade on Friday Close")
    print("========================================================\n" + Style.RESET_ALL)

    top_us = args.top_us
    top_jp = args.top_jp
    bm_ticker = args.benchmark

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True)
    tickers = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 日次データ(過去2年)一括ダウンロード中... (これには数分かかる場合があります)")
    download_tickers = tickers + [bm_ticker]
    
    chunk_size = 500
    all_close = {}
    
    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i+chunk_size]
        try:
            raw = yf.download(chunk, period="2y", interval="1d", progress=False)
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

    close_df = pd.DataFrame(all_close).dropna(how="all")

    if close_df.empty:
        print("データ取得に失敗しました。")
        return

    days = close_df.index.tolist()
    if len(days) < 150:
        print("データ期間が短すぎます。")
        return

    print(f"  取得データ期間: {days[0].date()} 〜 {days[-1].date()} ({len(days)}営業日)")

    results = []
    # 過去6ヶ月（約126営業日）のデータがスコア計算に必要なので、開始インデックスをずらす
    start_idx = 130 
    
    print("\n[3] バックテスト開始...")
    
    # Weekly Rebalancing (step=5)
    for i in range(start_idx, len(days) - 5, 5):
        trade_day = days[i]
        next_trade_day = days[i+5]
        
        scores = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            
            # 判定は前日(i-1)の大引けデータまで（木曜夜の判定を想定）
            s = close_df[ticker].iloc[:i].dropna()
            if len(s) < 127:
                continue
                
            try:
                p_now = float(s.iloc[-1])
                p_1m  = float(s.iloc[-21])  # 約1ヶ月前(21営業日)
                p_3m  = float(s.iloc[-63])  # 約3ヶ月前(63営業日)
                p_6m  = float(s.iloc[-126]) # 約6ヶ月前(126営業日)
                
                if p_1m == 0 or p_3m == 0 or p_6m == 0: continue
                
                ret_1m = ((p_now / p_1m) - 1) * 100
                ret_3m = ((p_now / p_3m) - 1) * 100
                ret_6m = ((p_now / p_6m) - 1) * 100
                
                raw_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                market = universe[ticker]
                
                scores.append({
                    "ticker": ticker,
                    "market": market,
                    "score": raw_score
                })
            except Exception:
                continue
                
        if not scores: continue
        
        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top = score_df[score_df["market"] == "US"].head(top_us)
        jp_top = score_df[score_df["market"] == "JP"].head(top_jp)
        deck = pd.concat([us_top, jp_top])
        
        deck_tickers = deck["ticker"].tolist()
        period_returns = []
        
        for t in deck_tickers:
            if t in close_df.columns:
                p_in = close_df[t].loc[trade_day]
                p_out = close_df[t].loc[next_trade_day]
                if pd.notna(p_in) and pd.notna(p_out) and p_in > 0:
                    ret = (p_out / p_in) - 1.0
                    period_returns.append(ret)
        
        pf_return = np.mean(period_returns) if period_returns else 0.0
        
        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm_in = close_df[bm_ticker].loc[trade_day]
            bm_out = close_df[bm_ticker].loc[next_trade_day]
            if pd.notna(bm_in) and pd.notna(bm_out) and bm_in > 0:
                bm_return = (bm_out / bm_in) - 1.0
                
        results.append({
            "Trade_Date": trade_day.strftime("%Y-%m-%d"),
            "PF_Return": pf_return,
            "BM_Return": bm_return
        })
        
    if not results:
        print("バックテスト結果がありません。")
        return
        
    res_df = pd.DataFrame(results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()
    
    # 月ごとにサマリーを作成して表示
    res_df["Month"] = pd.to_datetime(res_df["Trade_Date"]).dt.to_period('M')
    
    monthly_summary = []
    for month, group in res_df.groupby("Month"):
        start_pf = group["PF_Cum"].iloc[0] / (1.0 + group["PF_Return"].iloc[0])
        end_pf = group["PF_Cum"].iloc[-1]
        month_pf_ret = (end_pf / start_pf) - 1.0
        
        start_bm = group["BM_Cum"].iloc[0] / (1.0 + group["BM_Return"].iloc[0])
        end_bm = group["BM_Cum"].iloc[-1]
        month_bm_ret = (end_bm / start_bm) - 1.0
        
        trades_count = len(group)
        
        monthly_summary.append({
            "Month": str(month),
            "Trades": trades_count,
            "PF_Return": month_pf_ret,
            "BM_Return": month_bm_ret,
            "PF_Cum": end_pf,
            "BM_Cum": end_bm
        })
        
    summary_df = pd.DataFrame(monthly_summary)
    
    display_df = summary_df.copy()
    display_df["PF_Return"] = (display_df["PF_Return"] * 100).map("{:+.2f}%".format)
    display_df["BM_Return"] = (display_df["BM_Return"] * 100).map("{:+.2f}%".format)
    display_df["PF_Cum"] = (display_df["PF_Cum"] * 100).map("{:.1f}%".format)
    display_df["BM_Cum"] = (display_df["BM_Cum"] * 100).map("{:.1f}%".format)
    
    print("\n====================================================================================================")
    print("  🐒 バックテスト月次集計 (超現実的・週次 引け成り売買 / ロスカットなし)")
    print("====================================================================================================")
    print(tabulate(display_df, headers="keys", tablefmt="simple", showindex=False))
    
    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]
    
    print("\n========================================================")
    print(Fore.CYAN + "  🏆 バックテスト最終結果 (Realistic Weekly)" + Style.RESET_ALL)
    print("========================================================")
    print(f"  期間: {res_df['Trade_Date'].iloc[0]} 〜 {res_df['Trade_Date'].iloc[-1]}")
    print(f"  総トレード回数: {len(res_df)} 回")
    print(f"  モメンタムチンパン累積リターン: {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_pf:.2f}倍)")
    print(f"  ベンチマーク ({bm_ticker}) 累積リターン: {Fore.GREEN if final_bm > 1 else Fore.RED}{(final_bm - 1.0)*100:+.2f}%{Style.RESET_ALL} (資産 {final_bm:.2f}倍)")
    print("========================================================")
    
    if final_pf > final_bm:
        outperform = (final_pf - final_bm) * 100
        print(Fore.YELLOW + f"  🔥 モメンタムチンパンがベンチマークを {outperform:+.2f}% アウトパフォームしました！" + Style.RESET_ALL)
    else:
        underperform = (final_bm - final_pf) * 100
        print(Fore.RED + f"  💀 チンパンはベンチマークに {underperform:+.2f}% 負けました" + Style.RESET_ALL)

if __name__ == "__main__":
    main()
