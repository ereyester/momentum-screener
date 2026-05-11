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

# ── 改良点 ──────────────────────────────────────────────────
# 案1: スコアをボラティリティ調整型（シャープ型）に変更
#       score = (ret_1m/vol_1m * 0.4) + (ret_3m/vol_3m * 0.3) + (ret_6m/vol_6m * 0.2)
#       ボラが低く安定した上昇銘柄を優先する
#
# 案2: ドローダウン制御
#       ポートフォリオ累積リターンが直近ピークから --dd-threshold % 以上下落したら
#       全ポジションをキャッシュに退避し、翌週から再エントリー
# ──────────────────────────────────────────────────────────

def calc_volatility(series: pd.Series, window: int) -> float:
    """週次リターンの標準偏差（年率換算なし）"""
    rets = series.pct_change().dropna()
    if len(rets) < window // 2:
        return np.nan
    return float(rets.iloc[-window:].std())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-us",       type=int,   default=10,   help="Number of US stocks")
    parser.add_argument("--top-jp",       type=int,   default=6,    help="Number of JP stocks")
    parser.add_argument("--benchmark",    type=str,   default="SPY", help="Benchmark ticker")
    parser.add_argument("--dd-threshold", type=float, default=15.0, help="ドローダウン閾値 %（例: 10 → -10%%でキャッシュ退避）")
    parser.add_argument("--dd-weeks",     type=int,   default=4,    help="キャッシュ退避週数（default: 4）")
    parser.add_argument("--blend",        type=float, default=0.3,  help="ボラ調整スコアのブレンド比率 0〜1（default: 0.3）")
    parser.add_argument("--no-leverage",  action="store_true",      help="レバレッジETFをユニバースから除外")
    args = parser.parse_args()

    print(Fore.YELLOW + "=" * 60)
    print("   Momentum Chimp Backtester v2.0")
    print(f"   改良: [案D] 生スコア(blend={1-args.blend:.1f}) + DDコントロール")
    print(f"   ドローダウン閾値: -{args.dd_threshold:.1f}%  退避期間: {args.dd_weeks}週")
    lev_str = (Fore.RED + "OFF" + Style.RESET_ALL) if args.no_leverage else (Fore.GREEN + "ON" + Style.RESET_ALL)
    print(f"   レバレッジETF: {lev_str}")
    print("=" * 60 + "\n" + Style.RESET_ALL)

    top_us    = args.top_us
    top_jp    = args.top_jp
    bm_ticker = args.benchmark
    dd_thresh  = args.dd_threshold / 100.0
    dd_weeks   = args.dd_weeks
    blend_vol  = args.blend
    blend_raw  = 1.0 - blend_vol

    print("[1] ユニバース取得中...")
    universe = get_universe(include_sp500=True, include_ndx=True, include_jpx=True,
                            include_leverage=not args.no_leverage)
    tickers = list(universe.keys())
    print(f"  対象: {len(tickers)}銘柄")

    print("[2] 週足データ(過去2年)一括ダウンロード中...")
    download_tickers = tickers + [bm_ticker]

    chunk_size = 500
    all_close = {}

    for i in range(0, len(download_tickers), chunk_size):
        chunk = download_tickers[i:i+chunk_size]
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
            print(f"Download error on chunk {i}: {e}")
        time.sleep(0.5)

    close_df = pd.DataFrame(all_close).dropna(how="all")

    if close_df.empty:
        print("データ取得に失敗しました。")
        return

    weeks = close_df.index.tolist()
    if len(weeks) < 30:
        print("データ期間が短すぎます。")
        return

    print(f"  取得データ期間: {weeks[0].date()} 〜 {weeks[-1].date()} ({len(weeks)}週間)")

    print("\n[3] バックテスト開始...")

    weekly_results = []
    start_idx = 26

    # ── 案2: ドローダウン管理用の状態変数 ──
    pf_cum       = 1.0   # 累積倍率
    peak_cum     = 1.0   # 直近ピーク
    in_cash      = False # キャッシュ退避フラグ
    cash_weeks   = 0     # 退避週数カウンター

    for i in range(start_idx, len(weeks) - 1):
        current_week = weeks[i]
        next_week    = weeks[i + 1]

        # ── 案2: ドローダウンチェック ──
        drawdown = (pf_cum / peak_cum) - 1.0
        if not in_cash and drawdown <= -dd_thresh:
            in_cash = True
            cash_weeks = 0
            print(f"  [{current_week.date()}] ⚠️  DD={drawdown*100:.1f}% → キャッシュ退避")

        # キャッシュ週: ポジションなし、リターン0
        if in_cash:
            bm_return = 0.0
            if bm_ticker in close_df.columns:
                bm_T  = close_df[bm_ticker].loc[current_week]
                bm_T1 = close_df[bm_ticker].loc[next_week]
                if pd.notna(bm_T) and pd.notna(bm_T1) and bm_T > 0:
                    bm_return = (bm_T1 / bm_T) - 1.0

            weekly_results.append({
                "Week":      next_week.strftime("%Y-%m-%d"),
                "PF_Return": 0.0,
                "BM_Return": bm_return,
                "Top_US":    "-- CASH --",
                "Top_JP":    "-- CASH --",
                "Cash":      True,
            })
            cash_weeks += 1
            if cash_weeks >= dd_weeks:
                in_cash  = False
                peak_cum = pf_cum  # 再エントリー時にピークをリセット（新基準で計測）
                print(f"  [{next_week.date()}] ✅ キャッシュ退避解除 → 再エントリー")
            continue

        # ── 案1: ボラ調整スコア計算 ──
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

                ret_1m = ((p_now / p_1m) - 1) * 100
                ret_3m = ((p_now / p_3m) - 1) * 100
                ret_6m = ((p_now / p_6m) - 1) * 100

                # ボラティリティ（週次リターンの標準偏差）
                vol_1m = calc_volatility(s.iloc[-6:],  5)
                vol_3m = calc_volatility(s.iloc[-15:], 13)
                vol_6m = calc_volatility(s.iloc[-28:], 26)

                # ボラ=0 or NaN のときはボラ調整スコアを生スコアで代替
                if any(pd.isna(v) or v == 0 for v in [vol_1m, vol_3m, vol_6m]):
                    vol_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                else:
                    vol_score = (ret_1m / vol_1m * 0.4) + (ret_3m / vol_3m * 0.3) + (ret_6m / vol_6m * 0.2)

                # 案A: 生スコアとボラ調整スコアのブレンド
                momentum_score = (ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2)
                raw_score = blend_raw * momentum_score + blend_vol * vol_score

                scores.append({
                    "ticker": ticker,
                    "market": universe[ticker],
                    "score":  raw_score,
                })
            except Exception:
                continue

        if not scores:
            continue

        score_df = pd.DataFrame(scores).sort_values("score", ascending=False)
        us_top = score_df[score_df["market"] == "US"].iloc[:top_us]
        jp_top = score_df[score_df["market"] == "JP"].iloc[:top_jp]
        deck   = pd.concat([us_top, jp_top])

        # ── リターン計算 ──
        next_week_returns = []
        for t in deck["ticker"].tolist():
            if t in close_df.columns:
                p_T  = close_df[t].loc[current_week]
                p_T1 = close_df[t].loc[next_week]
                if pd.notna(p_T) and pd.notna(p_T1) and p_T > 0:
                    next_week_returns.append((p_T1 / p_T) - 1.0)

        pf_return = float(np.mean(next_week_returns)) if next_week_returns else 0.0

        bm_return = 0.0
        if bm_ticker in close_df.columns:
            bm_T  = close_df[bm_ticker].loc[current_week]
            bm_T1 = close_df[bm_ticker].loc[next_week]
            if pd.notna(bm_T) and pd.notna(bm_T1) and bm_T > 0:
                bm_return = (bm_T1 / bm_T) - 1.0

        # ── 案2: 累積・ピーク更新 ──
        pf_cum  *= (1.0 + pf_return)
        peak_cum = max(peak_cum, pf_cum)

        weekly_results.append({
            "Week":      next_week.strftime("%Y-%m-%d"),
            "PF_Return": pf_return,
            "BM_Return": bm_return,
            "Top_US":    ", ".join(us_top["ticker"].tolist()),
            "Top_JP":    ", ".join([t.replace(".T", "") for t in jp_top["ticker"].tolist()]),
            "Cash":      False,
        })

    if not weekly_results:
        print("バックテスト結果がありません。")
        return

    res_df = pd.DataFrame(weekly_results)
    res_df["PF_Cum"] = (1.0 + res_df["PF_Return"]).cumprod()
    res_df["BM_Cum"] = (1.0 + res_df["BM_Return"]).cumprod()

    # 表示用整形
    display_df = res_df[["Week", "PF_Return", "BM_Return", "Top_US", "Top_JP", "PF_Cum", "BM_Cum"]].copy()
    display_df["PF_Return"] = (display_df["PF_Return"] * 100).map("{:+.2f}%".format)
    display_df["BM_Return"] = (display_df["BM_Return"] * 100).map("{:+.2f}%".format)
    display_df["PF_Cum"]    = (display_df["PF_Cum"] * 100).map("{:.1f}%".format)
    display_df["BM_Cum"]    = (display_df["BM_Cum"] * 100).map("{:.1f}%".format)

    print("\n" + "=" * 100)
    print("  🐒 バックテスト週次推移 v2 (ボラ調整スコア + DDコントロール)")
    print("=" * 100)
    print(tabulate(display_df, headers="keys", tablefmt="simple", showindex=False))

    display_df.to_csv("weekly_positions_v2.csv", index=False)
    print("\n[INFO] ポジション履歴を 'weekly_positions_v2.csv' に保存しました。")

    final_pf = res_df["PF_Cum"].iloc[-1]
    final_bm = res_df["BM_Cum"].iloc[-1]
    cash_count = res_df["Cash"].sum()

    # ── ベースラインとの比較 ──
    baseline_pf = 4.8457  # backtest_weekly.py 実績
    baseline_bm = 1.2551

    print("\n" + "=" * 60)
    print(Fore.CYAN + "  🏆 バックテスト最終結果 v2 (ボラ調整 + DDコントロール)" + Style.RESET_ALL)
    print("=" * 60)
    print(f"  期間: {res_df['Week'].iloc[0]} 〜 {res_df['Week'].iloc[-1]} ({len(res_df)}週間)")
    print(f"  スコアブレンド: 生スコア×{blend_raw:.1f} + ボラ調整×{blend_vol:.1f}  退避期間: {dd_weeks}週")
    print(f"  キャッシュ退避週数（合計）: {cash_count}週")
    print(f"  PF累積リターン:  {Fore.GREEN if final_pf > 1 else Fore.RED}{(final_pf-1)*100:+.2f}%{Style.RESET_ALL}  ({final_pf:.2f}倍)")
    print(f"  ベンチマーク({bm_ticker}): {(final_bm-1)*100:+.2f}%  ({final_bm:.2f}倍)")
    print("─" * 60)
    print(f"  【ベースライン比較】")
    print(f"  ベースライン (v1): {(baseline_pf-1)*100:+.2f}%  ({baseline_pf:.2f}倍)")
    print(f"  v2 改良版(blend={blend_vol:.1f}): {(final_pf-1)*100:+.2f}%  ({final_pf:.2f}倍)")
    delta = (final_pf - baseline_pf) * 100
    arrow = "↑" if delta > 0 else "↓"
    color = Fore.GREEN if delta > 0 else Fore.RED
    print(f"  差分:              {color}{arrow} {abs(delta):.2f}%{Style.RESET_ALL}")
    print("=" * 60)

    if final_pf > final_bm:
        print(Fore.YELLOW + f"  🔥 ベンチマークを {(final_pf - final_bm)*100:+.2f}% アウトパフォーム！" + Style.RESET_ALL)
    else:
        print(Fore.RED + f"  💀 ベンチマークに {(final_bm - final_pf)*100:+.2f}% 負けました" + Style.RESET_ALL)


if __name__ == "__main__":
    main()
