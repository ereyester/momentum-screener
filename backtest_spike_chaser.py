"""
🐒 Spike Chaser バックテスター
急騰・急落後のモメンタム継続を検証する（UP / DOWN / BOTH 全モード比較）
"""

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

# 銘柄リストは momentum_screener.py から流用
from momentum_screener import US_STOCKS, JP_STOCKS, LEVERAGED_ETFS


# ============================================================
# ユニバース構築
# ============================================================

def build_universe(use_leverage: bool = True):
    universe = {}
    for t in US_STOCKS:
        universe[t] = "US"
    for t in JP_STOCKS:
        universe[t] = "JP"
    # レバレッジETF（デフォルトON）
    if use_leverage:
        for t in LEVERAGED_ETFS:
            universe[t] = "US"
    return universe


# ============================================================
# テクニカル指標
# ============================================================

def calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0).tail(period).mean()
    loss  = (-delta.where(delta < 0, 0.0)).tail(period).mean()
    if loss == 0:
        return 100.0
    return 100 - (100 / (1 + gain / loss))


# ============================================================
# スパイク検知
# ============================================================

def detect_spikes(close_df, vol_df, tickers, universe,
                  spike_up_pct, spike_down_pct, vol_ratio_min,
                  ma_window, mode):
    """
    各日・各銘柄のスパイクを検知し、リストで返す。
    mode: 'up' | 'down' | 'both'
    """
    days = close_df.index.tolist()
    spikes = []
    start_idx = max(ma_window + 21, 30)

    for i in range(start_idx, len(days)):
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue

            cs   = close_df[ticker]
            curr = cs.iloc[i]
            prev = cs.iloc[i - 1]

            if pd.isna(curr) or pd.isna(prev) or prev == 0:
                continue

            day_ret = (curr / prev - 1) * 100

            # 出来高倍率
            if ticker in vol_df.columns:
                vol_slice = vol_df[ticker].iloc[max(0, i - 20):i]
                vol_avg   = vol_slice.mean()
                vol_ratio = vol_df[ticker].iloc[i] / vol_avg if vol_avg > 0 else 1.0
            else:
                vol_ratio = 1.0

            # MA50
            ma_slice = cs.iloc[max(0, i - ma_window):i]
            ma50     = ma_slice.mean() if len(ma_slice) >= ma_window else None

            # RSI
            rsi_slice = cs.iloc[max(0, i - 28):i + 1]
            rsi = calc_rsi(rsi_slice) if len(rsi_slice) >= 15 else 50.0

            is_up   = (day_ret >=  spike_up_pct   and vol_ratio >= vol_ratio_min
                       and (ma50 is None or curr > ma50) and rsi <= 88)
            is_down = (day_ret <= -spike_down_pct  and vol_ratio >= vol_ratio_min)

            spike_type = None
            if mode == "up"   and is_up:   spike_type = "UP"
            elif mode == "down" and is_down: spike_type = "DOWN"
            elif mode == "both":
                if   is_up:   spike_type = "UP"
                elif is_down: spike_type = "DOWN"

            if spike_type is None:
                continue

            spikes.append({
                "signal_day":     days[i],
                "signal_day_idx": i,
                "ticker":         ticker,
                "spike_type":     spike_type,
                "day_ret":        day_ret,
                "vol_ratio":      vol_ratio,
                "signal_close":   curr,
                "market":         universe.get(ticker, "US"),
            })

    return spikes


# ============================================================
# トレードシミュレーション
# ============================================================

def simulate_trades(spikes, close_df, hold_days, stop_loss_pct):
    """
    スパイク検知翌日エントリー → hold_days 後 or ストップロス 手仕舞い
    """
    days   = close_df.index.tolist()
    trades = []

    for sp in spikes:
        ticker     = sp["ticker"]
        signal_idx = sp["signal_day_idx"]
        entry_idx  = signal_idx + 1

        if entry_idx >= len(days) or ticker not in close_df.columns:
            continue

        entry_price = close_df[ticker].iloc[entry_idx]
        if pd.isna(entry_price) or entry_price == 0:
            continue

        stop_price     = entry_price * (1 - stop_loss_pct / 100)
        planned_exit   = min(entry_idx + hold_days, len(days) - 1)
        actual_exit    = planned_exit
        actual_exit_px = None
        stopped_out    = False

        for j in range(entry_idx + 1, planned_exit + 1):
            px = close_df[ticker].iloc[j]
            if pd.isna(px):
                continue
            if px <= stop_price:
                actual_exit_px = stop_price
                actual_exit    = j
                stopped_out    = True
                break

        if actual_exit_px is None:
            actual_exit_px = close_df[ticker].iloc[actual_exit]

        if pd.isna(actual_exit_px) or actual_exit_px == 0:
            continue

        ret = (actual_exit_px / entry_price) - 1.0

        trades.append({
            **sp,
            "entry_day":    days[entry_idx],
            "entry_price":  entry_price,
            "exit_day":     days[actual_exit],
            "exit_price":   actual_exit_px,
            "return":       ret,
            "return_pct":   ret * 100,
            "stopped_out":  stopped_out,
        })

    return trades


# ============================================================
# 結果表示
# ============================================================

def print_mode_summary(trades, mode_label):
    if not trades:
        print(f"\n  {mode_label}: トレードなし")
        return

    df       = pd.DataFrame(trades)
    total    = len(df)
    wins     = (df["return"] > 0).sum()
    win_rate = wins / total * 100
    avg_ret  = df["return_pct"].mean()
    med_ret  = df["return_pct"].median()
    max_gain = df["return_pct"].max()
    max_loss = df["return_pct"].min()
    stopped  = df["stopped_out"].sum()

    df["entry_month"] = pd.to_datetime(df["entry_day"]).dt.to_period("M")
    monthly  = df.groupby("entry_month")["return"].mean()
    cum_ret  = (1 + monthly).prod() - 1

    up_df   = df[df["spike_type"] == "UP"]
    dn_df   = df[df["spike_type"] == "DOWN"]

    c  = Fore.GREEN if avg_ret > 0 else Fore.RED
    cc = Fore.GREEN if cum_ret > 0 else Fore.RED

    print(f"\n  {'─'*60}")
    print(f"  🎯 {Fore.CYAN}{mode_label}{Style.RESET_ALL}")
    print(f"  {'─'*60}")
    print(f"  総トレード数  : {total} 回")
    print(f"  勝率          : {c}{win_rate:.1f}%{Style.RESET_ALL}  (勝 {wins} / 負 {total - wins})")
    print(f"  平均リターン  : {c}{avg_ret:+.2f}%{Style.RESET_ALL}  (中央値: {med_ret:+.2f}%)")
    print(f"  最大利益      : {Fore.GREEN}{max_gain:+.2f}%{Style.RESET_ALL}")
    print(f"  最大損失      : {Fore.RED}{max_loss:+.2f}%{Style.RESET_ALL}")
    print(f"  損切り発動    : {stopped} 回 ({stopped/total*100:.1f}%)")
    print(f"  仮想累積リターン: {cc}{cum_ret*100:+.2f}%{Style.RESET_ALL}")

    if not up_df.empty:
        uw = (up_df["return"] > 0).sum() / len(up_df) * 100
        print(f"\n    急騰追撃 (UP)        : {len(up_df):3d}回  勝率 {uw:.1f}%  平均 {up_df['return_pct'].mean():+.2f}%")
    if not dn_df.empty:
        dw = (dn_df["return"] > 0).sum() / len(dn_df) * 100
        print(f"    急落リバウンド (DOWN): {len(dn_df):3d}回  勝率 {dw:.1f}%  平均 {dn_df['return_pct'].mean():+.2f}%")


def print_monthly_table(trades, mode_label):
    if not trades:
        return
    df = pd.DataFrame(trades)
    df["entry_month"] = pd.to_datetime(df["entry_day"]).dt.to_period("M")
    rows = []
    cum = 1.0
    for month, g in df.groupby("entry_month"):
        avg = g["return_pct"].mean()
        wins = (g["return"] > 0).sum()
        cum *= (1 + avg / 100)
        rows.append([
            str(month),
            len(g),
            f"{wins}/{len(g)}",
            f"{avg:+.2f}%",
            f"{(cum - 1) * 100:+.1f}%",
        ])
    print(f"\n  📅 月次集計 [{mode_label}]")
    print(tabulate(rows,
                   headers=["月", "トレード数", "勝/負", "平均リターン", "累積"],
                   tablefmt="simple"))


def print_best_worst(trades, mode_label, top_n=8):
    if not trades:
        return
    df = pd.DataFrame(trades).sort_values("return_pct", ascending=False)

    def make_rows(sub_df):
        rows = []
        for _, r in sub_df.iterrows():
            rows.append([
                r["ticker"],
                r["spike_type"],
                str(r["entry_day"])[:10],
                str(r["exit_day"])[:10],
                f"{r['day_ret']:+.1f}%",
                f"{r['return_pct']:+.1f}%",
                "🛑" if r["stopped_out"] else "✅",
            ])
        return rows

    hdrs = ["銘柄", "種別", "エントリー", "手仕舞", "当日騰落", "リターン", "結果"]
    print(f"\n  📈 ベストトレード TOP{top_n} [{mode_label}]")
    print(tabulate(make_rows(df.head(top_n)), headers=hdrs, tablefmt="simple"))
    print(f"\n  📉 ワーストトレード TOP{top_n} [{mode_label}]")
    print(tabulate(make_rows(df.tail(top_n)), headers=hdrs, tablefmt="simple"))


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spike-up-pct",   type=float, default=8.0)
    parser.add_argument("--spike-down-pct", type=float, default=8.0)
    parser.add_argument("--hold-days",      type=int,   default=5)
    parser.add_argument("--vol-ratio",      type=float, default=1.5)
    parser.add_argument("--stop-loss",      type=float, default=7.0)
    parser.add_argument("--ma-window",      type=int,   default=50)
    parser.add_argument("--benchmark",      type=str,   default="SPY")
    parser.add_argument("--detail",         action="store_true", help="月次・個別トレード詳細表示")
    parser.add_argument("--no-leverage",    action="store_true", help="レバレッジETFを除外する")
    args = parser.parse_args()

    print(Fore.YELLOW + "=" * 62)
    print("   🐒 Spike Chaser バックテスター v1.0")
    print("   急騰・急落後モメンタム追撃戦略 全モード比較")
    print("=" * 62 + Style.RESET_ALL)
    print(f"  急騰閾値: +{args.spike_up_pct}%  急落閾値: -{args.spike_down_pct}%")
    print(f"  保有日数: {args.hold_days}日  損切り: -{args.stop_loss}%  出来高: {args.vol_ratio}x以上")
    lev_on = not args.no_leverage
    lev_label = (Fore.GREEN + "ON" + Style.RESET_ALL) if lev_on else (Fore.RED + "OFF" + Style.RESET_ALL)
    print(f"  レバレッジETF: {lev_label}  TQQQ / SOXL / TECL / FNGU / UPRO / LABU")

    universe = build_universe(use_leverage=lev_on)
    tickers  = list(universe.keys())
    dl_list  = tickers + [args.benchmark]

    print(f"\n[1] データ取得中... ({len(tickers)} 銘柄 + {args.benchmark})")

    all_close, all_vol = {}, {}
    chunk_size = 100
    for i in range(0, len(dl_list), chunk_size):
        chunk = dl_list[i:i + chunk_size]
        try:
            raw = yf.download(chunk, period="2y", interval="1d", progress=False)
            for key, dest in [("Close", all_close), ("Volume", all_vol)]:
                if key not in raw.columns:
                    continue
                part = raw[key]
                if isinstance(part, pd.Series):
                    dest[chunk[0]] = part
                else:
                    for t in part.columns:
                        dest[t] = part[t]
        except Exception as e:
            print(f"  ダウンロードエラー: {e}")
        time.sleep(0.5)

    close_df = pd.DataFrame(all_close).dropna(how="all")
    vol_df   = pd.DataFrame(all_vol).dropna(how="all")

    if close_df.empty:
        print("データ取得失敗。終了します。")
        return

    days = close_df.index.tolist()
    print(f"  取得期間: {days[0].date()} 〜 {days[-1].date()} ({len(days)} 営業日)")

    # ベンチマーク
    bm_cum = 1.0
    if args.benchmark in close_df.columns:
        bm_s   = close_df[args.benchmark].dropna()
        bm_cum = bm_s.iloc[-1] / bm_s.iloc[0]
    print(f"  ベンチマーク ({args.benchmark}) 期間累積: {(bm_cum - 1) * 100:+.1f}%")

    # 全モード実行
    modes = [
        ("up",   "急騰追撃のみ  (UP)"),
        ("down", "急落リバウンド (DOWN)"),
        ("both", "両方合わせて  (BOTH)"),
    ]

    print(f"\n[2] バックテスト実行中...")
    all_results = {}
    for mode_key, mode_label in modes:
        print(f"  → {mode_label} ...")
        spikes = detect_spikes(
            close_df, vol_df, tickers, universe,
            spike_up_pct=args.spike_up_pct,
            spike_down_pct=args.spike_down_pct,
            vol_ratio_min=args.vol_ratio,
            ma_window=args.ma_window,
            mode=mode_key,
        )
        trades = simulate_trades(spikes, close_df, args.hold_days, args.stop_loss)
        all_results[mode_key] = (mode_label, trades)

    # ========== 結果表示 ==========
    print(f"\n{'=' * 62}")
    print(Fore.CYAN + "  🏆 バックテスト結果" + Style.RESET_ALL)
    print(f"{'=' * 62}")

    for mode_key, (mode_label, trades) in all_results.items():
        print_mode_summary(trades, mode_label)

    # 全モード比較テーブル
    print(f"\n{'=' * 62}")
    print("  📊 全モード比較サマリー")
    print(f"{'=' * 62}")
    summary_rows = []
    for mode_key, (mode_label, trades) in all_results.items():
        if not trades:
            summary_rows.append([mode_label, 0, "-", "-", "-", "-"])
            continue
        df       = pd.DataFrame(trades)
        total    = len(df)
        win_rate = (df["return"] > 0).sum() / total * 100
        avg_ret  = df["return_pct"].mean()
        df["m"]  = pd.to_datetime(df["entry_day"]).dt.to_period("M")
        monthly  = df.groupby("m")["return"].mean()
        cum_ret  = (1 + monthly).prod() - 1
        stopped  = df["stopped_out"].sum()
        summary_rows.append([
            mode_label,
            total,
            f"{win_rate:.1f}%",
            f"{avg_ret:+.2f}%",
            f"{cum_ret * 100:+.1f}%",
            f"{stopped}回 ({stopped/total*100:.1f}%)",
        ])

    print(tabulate(
        summary_rows,
        headers=["モード", "トレード数", "勝率", "平均リターン", "仮想累積", "損切り発動"],
        tablefmt="simple",
    ))

    print(f"\n  ベンチマーク {args.benchmark}: {(bm_cum - 1) * 100:+.1f}%")

    # 詳細モード
    if args.detail:
        for mode_key, (mode_label, trades) in all_results.items():
            print(f"\n{'=' * 62}")
            print_monthly_table(trades, mode_label)
            print_best_worst(trades, mode_label)

    print(f"\n{'=' * 62}")
    print("  ⚠️  投資判断はご自身でお願いします。")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
