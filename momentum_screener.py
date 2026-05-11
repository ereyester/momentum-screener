"""
モメンタムチンパン 株式スクリーナー
リアルタイム株価・モメンタム分析・指値計算・スクリーニング
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tabulate import tabulate
from colorama import init, Fore, Style
import time
import warnings
warnings.filterwarnings("ignore")

init(autoreset=True)
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 銘柄マスター
# ============================================================
US_STOCKS = {
    # モメンタム最強デッキ
    "NVDA":  {"name": "エヌビディア",      "tier": "S", "theme": "AI半導体王者",     "alloc": 700},
    "AVGO":  {"name": "ブロードコム",      "tier": "S", "theme": "AI半導体2番手",   "alloc": 500},
    "META":  {"name": "メタ",             "tier": "S", "theme": "AI広告独占",       "alloc": 300},
    "ARM":   {"name": "ARM Holdings",    "tier": "S", "theme": "CPUアーキ独占",    "alloc": 200},
    "AMD":   {"name": "AMD",             "tier": "A", "theme": "CPU復権波及",      "alloc": 100},
    # 転換点・出遅れ
    "GOOGL": {"name": "アルファベット",    "tier": "A", "theme": "出遅れMag7",       "alloc": 0},
    "MSFT":  {"name": "マイクロソフト",    "tier": "A", "theme": "Azure加速",       "alloc": 0},
    "AAPL":  {"name": "アップル",         "tier": "A", "theme": "出遅れ+CEO交代",   "alloc": 0},
    "PLTR":  {"name": "パランティア",      "tier": "A", "theme": "高値-32%成長",     "alloc": 0},
    "AXON":  {"name": "アクソン",         "tier": "A", "theme": "AI警察高値-30%",  "alloc": 0},
    "CRM":   {"name": "セールスフォース",  "tier": "A", "theme": "年初来-30%転換",   "alloc": 0},
    "QCOM":  {"name": "クアルコム",       "tier": "A", "theme": "Auto半導体出遅れ", "alloc": 0},
    "UBER":  {"name": "ウーバー",         "tier": "A", "theme": "高値-25%転換",     "alloc": 0},
    "NVO":   {"name": "ノボノルディスク",  "tier": "A", "theme": "過去1年-30%割安", "alloc": 0},
    "VRT":   {"name": "バーティブ",       "tier": "A", "theme": "好決算後逆行安",   "alloc": 0},
    "ISRG":  {"name": "インテュイティブ",  "tier": "A", "theme": "手術ロボ転換",    "alloc": 0},
    "LLY":   {"name": "イーライリリー",    "tier": "A", "theme": "GLP-1構造成長",   "alloc": 0},
    "PANW":  {"name": "パロアルト",       "tier": "A", "theme": "サイバー出遅れ",   "alloc": 0},
    "VST":   {"name": "ビストラ",         "tier": "A", "theme": "AI電力出遅れ",    "alloc": 0},
    "AMZN":  {"name": "アマゾン",         "tier": "B", "theme": "AWS+25%",         "alloc": 0},
    "MRVL":  {"name": "マーベル",         "tier": "B", "theme": "AVGO出遅れ版",    "alloc": 0},
    "ALAB":  {"name": "アステララボ",     "tier": "B", "theme": "AI配管独占",      "alloc": 0},
    "CRDO":  {"name": "クレドテクノロジー","tier": "B", "theme": "AI光DSP",         "alloc": 0},
    # 指値待ち
    "TXN":   {"name": "テキサスインスツ",  "tier": "C", "theme": "アナログ転換確認", "alloc": 0},
    "INTC":  {"name": "インテル",         "tier": "C", "theme": "急騰後深押し待ち", "alloc": 0},
    "MU":    {"name": "マイクロン",       "tier": "C", "theme": "HBM ATH圏",       "alloc": 0},
    "GEV":   {"name": "GEベルノバ",       "tier": "C", "theme": "電力転換+71%後",  "alloc": 0},
    "STX":   {"name": "シーゲート",       "tier": "C", "theme": "HDD版MU高値圏",   "alloc": 0},
}

# ============================================================
# レバレッジETF（爆発的リターン狙い）
# ============================================================
LEVERAGED_ETFS = {
    "TQQQ": {"name": "QQQ 3倍",      "tier": "S", "theme": "Nasdaq100 3倍レバレッジ",  "alloc": 0},
    "SOXL": {"name": "半導体 3倍",   "tier": "S", "theme": "SOX半導体 3倍レバレッジ",   "alloc": 0},
    "TECL": {"name": "テック 3倍",   "tier": "A", "theme": "Technology 3倍レバレッジ", "alloc": 0},
    "FNGU": {"name": "FANG+ 3倍",   "tier": "A", "theme": "FANG+指数 3倍レバレッジ",  "alloc": 0},
    "UPRO": {"name": "S&P500 3倍",  "tier": "B", "theme": "S&P500 3倍レバレッジ",    "alloc": 0},
    "LABU": {"name": "バイオ 3倍",   "tier": "C", "theme": "Biotech 3倍レバレッジ",   "alloc": 0},
}

JP_STOCKS = {
    # モメンタム最強デッキ
    "6857.T": {"name": "アドバンテスト",       "tier": "S", "theme": "AI半導体テスタ最強", "alloc": 500},
    "5803.T": {"name": "フジクラ",             "tier": "S", "theme": "DC電線10倍モメ",     "alloc": 400},
    "6976.T": {"name": "太陽誘電",             "tier": "S", "theme": "AIサーバーMLCC",     "alloc": 300},
    # 転換点
    "6594.T": {"name": "ニデック",             "tier": "A", "theme": "底値決算前",          "alloc": 0},
    "6758.T": {"name": "ソニーグループ",        "tier": "A", "theme": "国産AI連合出遅れ",   "alloc": 0},
    "4568.T": {"name": "第一三共",             "tier": "A", "theme": "ADC世界トップ",       "alloc": 0},
    "6954.T": {"name": "ファナック",            "tier": "A", "theme": "フィジカルAI出遅れ", "alloc": 0},
    "7974.T": {"name": "任天堂",               "tier": "A", "theme": "Switch2 6月",         "alloc": 0},
    "9984.T": {"name": "SBG",                 "tier": "A", "theme": "AI総合商社ARM連動",   "alloc": 0},
    "6861.T": {"name": "キーエンス",           "tier": "A", "theme": "センサーフィジカルAI", "alloc": 0},
    "8766.T": {"name": "東京海上HD",           "tier": "A", "theme": "バフェット取得",      "alloc": 0},
    "5802.T": {"name": "住友電工",             "tier": "A", "theme": "電線御三家出遅れ",    "alloc": 0},
    "6701.T": {"name": "NEC",                 "tier": "A", "theme": "AI・サイバー・防衛",   "alloc": 0},
    "7267.T": {"name": "ホンダ",               "tier": "A", "theme": "フィジカルAI×EV",    "alloc": 0},
    "8306.T": {"name": "三菱UFJ",             "tier": "A", "theme": "利上げ恩恵",          "alloc": 0},
    # フィジカルAI部品
    "6324.T": {"name": "ハーモニックドライブ",  "tier": "A", "theme": "ロボ減速機底値",     "alloc": 0},
    "6471.T": {"name": "日本精工",             "tier": "A", "theme": "ベアリング出遅れ",    "alloc": 0},
    "6268.T": {"name": "ナブテスコ",           "tier": "A", "theme": "産業ロボ関節独占",    "alloc": 0},
    "6981.T": {"name": "村田製作所",           "tier": "B", "theme": "MLCC世界1位",        "alloc": 0},
    "6920.T": {"name": "レーザーテック",        "tier": "B", "theme": "SOX連動最強",        "alloc": 0},
    # 指値待ち
    "6506.T": {"name": "安川電機",             "tier": "C", "theme": "V字確認押し目",       "alloc": 0},
    "7011.T": {"name": "三菱重工",             "tier": "C", "theme": "防衛高値圏指値",      "alloc": 0},
    "5801.T": {"name": "古河電気",             "tier": "C", "theme": "4倍後深押し待ち",     "alloc": 0},
    "6146.T": {"name": "ディスコ",             "tier": "C", "theme": "精密切断サイクル",    "alloc": 0},
}

EARNINGS_DATES = {
    "GOOGL": "2025-04-29", "META": "2025-04-29", "MSFT": "2025-04-29",
    "AAPL": "2025-04-30", "QCOM": "2025-04-30", "AMZN": "2025-05-01",
    "PLTR": "2025-05-04", "AMD": "2025-05-05", "AXON": "2025-05-06",
    "UBER": "2025-05-06", "STX": "2025-04-28", "ALAB": "2025-05-05",
    "MRVL": "2025-05-21", "PANW": "2025-06-01",
    "5803.T": "2025-05-14", "6857.T": "2025-04-27", "6594.T": "2025-04-28",
    "6506.T": "2025-05-01",
}

# ============================================================
# データ取得
# ============================================================

def fetch_stock_data(ticker: str, period: str = "1y") -> dict:
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period, auto_adjust=True)
        if hist.empty:
            return None
        info = {}
        try:
            info = tk.info or {}
        except Exception:
            pass

        price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        day_chg = (price - prev_close) / prev_close * 100

        high_52w = float(hist["Close"].max())
        low_52w = float(hist["Close"].min())
        from_ath = (price - high_52w) / high_52w * 100

        ytd_start = hist[hist.index >= f"{datetime.now().year}-01-01"]
        ytd_chg = ((price / float(ytd_start["Close"].iloc[0])) - 1) * 100 if not ytd_start.empty else 0.0

        ma20  = float(hist["Close"].tail(20).mean())
        ma50  = float(hist["Close"].tail(50).mean()) if len(hist) >= 50 else 0.0
        ma200 = float(hist["Close"].tail(200).mean()) if len(hist) >= 200 else 0.0

        delta = hist["Close"].diff()
        gain  = delta.where(delta > 0, 0.0).tail(14).mean()
        loss  = (-delta.where(delta < 0, 0.0)).tail(14).mean()
        rsi   = 100 - (100 / (1 + gain / loss)) if loss != 0 else 100.0

        vol_avg = float(hist["Volume"].tail(20).mean())
        vol_now = float(hist["Volume"].iloc[-1])
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

        ret_1m  = ((price / float(hist["Close"].iloc[-21])) - 1) * 100 if len(hist) >= 21 else 0.0
        ret_3m  = ((price / float(hist["Close"].iloc[-63])) - 1) * 100 if len(hist) >= 63 else 0.0
        ret_6m  = ((price / float(hist["Close"].iloc[-126])) - 1) * 100 if len(hist) >= 126 else 0.0
        ret_1y  = ((price / float(hist["Close"].iloc[0])) - 1) * 100

        momentum_score = (ret_1m * 0.4 + ret_3m * 0.3 + ret_6m * 0.2 + ret_1y * 0.1)

        fwd_pe = info.get("forwardPE") or info.get("trailingPE")

        return {
            "ticker": ticker,
            "price": price,
            "day_chg": day_chg,
            "ytd_chg": ytd_chg,
            "ret_1m": ret_1m,
            "ret_3m": ret_3m,
            "ret_6m": ret_6m,
            "ret_1y": ret_1y,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "from_ath": from_ath,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "momentum_score": momentum_score,
            "fwd_pe": fwd_pe,
            "currency": "JPY" if ticker.endswith(".T") else "USD",
        }
    except Exception as e:
        return None


def calc_entry_levels(data: dict, tier: str) -> dict:
    p = data["price"]
    pct = {"S": 0.05, "A": 0.05, "B": 0.07, "C": 0.10}.get(tier, 0.07)
    entry = p * (1 - pct)
    stop  = entry * 0.93
    target_pct = {"S": 0.20, "A": 0.15, "B": 0.12, "C": 0.10}.get(tier, 0.15)
    target = entry * (1 + target_pct)
    rr = target_pct / 0.07
    return {
        "entry_pct": pct * 100,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
    }


def momentum_grade(score: float) -> str:
    if score >= 50:  return "SSS"
    if score >= 30:  return "SS"
    if score >= 15:  return "S"
    if score >= 8:   return "A"
    if score >= 0:   return "B"
    if score >= -10: return "C"
    return "D"


def color_val(val: float, positive_green: bool = True) -> str:
    if val > 0:
        return (Fore.GREEN if positive_green else Fore.RED) + f"{val:+.1f}%" + Style.RESET_ALL
    elif val < 0:
        return (Fore.RED if positive_green else Fore.GREEN) + f"{val:+.1f}%" + Style.RESET_ALL
    return f"{val:+.1f}%"


def format_price(price: float, currency: str) -> str:
    if currency == "JPY":
        return f"¥{price:,.0f}"
    return f"${price:,.2f}"


def earnings_countdown(ticker: str) -> str:
    date_str = EARNINGS_DATES.get(ticker)
    if not date_str:
        return "-"
    try:
        ed = datetime.strptime(date_str, "%Y-%m-%d")
        days = (ed - datetime.now()).days
        if days < 0:
            return "発表済"
        if days == 0:
            return Fore.RED + "★今日" + Style.RESET_ALL
        if days <= 7:
            return Fore.YELLOW + f"★{days}日後" + Style.RESET_ALL
        return f"{days}日後"
    except Exception:
        return "-"


# ============================================================
# スクリーニングロジック
# ============================================================

def screen_momentum_chimps(all_data: list) -> list:
    """純粋モメンタムチンパンスクリーニング：強いものだけ残す"""
    results = []
    for d in all_data:
        if d is None:
            continue
        score = 0
        flags = []

        # 1. 1ヶ月モメンタム (最重要)
        if d["ret_1m"] >= 20:  score += 40; flags.append("1M+20%↑")
        elif d["ret_1m"] >= 10: score += 25; flags.append("1M+10%↑")
        elif d["ret_1m"] >= 5:  score += 15; flags.append("1M+5%↑")
        elif d["ret_1m"] < -10: score -= 20; flags.append("1M弱↓")

        # 2. 52週高値との距離
        if d["from_ath"] >= -5:   score += 20; flags.append("ATH圏")
        elif d["from_ath"] >= -10: score += 12; flags.append("高値近")
        elif d["from_ath"] <= -30: score -= 10; flags.append("ATH-30%↓")

        # 3. RSI (モメンタムの強さ)
        if 60 <= d["rsi"] <= 80:  score += 15; flags.append(f"RSI{d['rsi']:.0f}")
        elif d["rsi"] > 80:       score += 8;  flags.append(f"RSI{d['rsi']:.0f}過熱")
        elif d["rsi"] < 40:       score -= 10; flags.append(f"RSI{d['rsi']:.0f}弱")

        # 4. 出来高急増
        if d["vol_ratio"] >= 2.0:  score += 10; flags.append(f"出来高{d['vol_ratio']:.1f}x")
        elif d["vol_ratio"] >= 1.5: score += 5;  flags.append(f"出来高{d['vol_ratio']:.1f}x")

        # 5. 移動平均線上にいるか
        if d["ma50"] > 0 and d["price"] > d["ma50"]:
            score += 5; flags.append("MA50↑")
        if d["ma200"] > 0 and d["price"] > d["ma200"]:
            score += 5; flags.append("MA200↑")

        # 6. 今日の動き
        if d["day_chg"] >= 5:    score += 10; flags.append(f"今日{d['day_chg']:+.1f}%")
        elif d["day_chg"] >= 2:  score += 5;  flags.append(f"今日{d['day_chg']:+.1f}%")
        elif d["day_chg"] <= -3: score -= 5;  flags.append(f"今日{d['day_chg']:+.1f}%↓")

        d["chimp_score"] = score
        d["chimp_flags"] = ", ".join(flags[:5])
        results.append(d)

    results.sort(key=lambda x: x["chimp_score"], reverse=True)
    return results


def screen_value_reversal(all_data: list) -> list:
    """転換点銘柄スクリーニング：出遅れ×カタリストあり"""
    results = []
    for d in all_data:
        if d is None:
            continue
        score = 0
        flags = []

        # 高値からの下落が大きい（出遅れ）
        if d["from_ath"] <= -25:  score += 30; flags.append(f"ATH{d['from_ath']:.0f}%")
        elif d["from_ath"] <= -15: score += 20; flags.append(f"ATH{d['from_ath']:.0f}%")
        elif d["from_ath"] <= -10: score += 10; flags.append(f"ATH{d['from_ath']:.0f}%")

        # 年初来がフラット〜マイナス（出遅れ）
        if d["ytd_chg"] <= -10:  score += 20; flags.append(f"YTD{d['ytd_chg']:+.0f}%")
        elif d["ytd_chg"] <= 5:  score += 10; flags.append(f"YTD{d['ytd_chg']:+.0f}%")

        # 最近反発し始めた（転換の初動）
        if 0 < d["ret_1m"] <= 15:  score += 15; flags.append("初動↑")
        elif d["ret_1m"] > 15:     score += 5

        # 決算カタリスト接近
        date_str = EARNINGS_DATES.get(d["ticker"])
        if date_str:
            try:
                ed = datetime.strptime(date_str, "%Y-%m-%d")
                days = (ed - datetime.now()).days
                if 0 <= days <= 14:
                    score += 25; flags.append(f"決算{days}日後")
                elif 0 <= days <= 30:
                    score += 10; flags.append(f"決算{days}日後")
            except Exception:
                pass

        # RSIが回復途上（40〜55）
        if 40 <= d["rsi"] <= 55: score += 10; flags.append(f"RSI{d['rsi']:.0f}回復中")

        d["reversal_score"] = score
        d["reversal_flags"] = ", ".join(flags[:5])
        results.append(d)

    results.sort(key=lambda x: x["reversal_score"], reverse=True)
    return results


# ============================================================
# 表示
# ============================================================

def print_header(title: str):
    width = 80
    print()
    print("=" * width)
    print(f"  {title}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * width)


def print_portfolio_table(all_data: dict, stocks_meta: dict, title: str, budget_man: int):
    print_header(f"📊 {title}  予算 {budget_man:,}万円")
    rows = []
    total_alloc = sum(m["alloc"] for m in stocks_meta.values())

    for ticker, meta in stocks_meta.items():
        d = all_data.get(ticker)
        if d is None:
            rows.append([
                ticker, meta["name"][:10], meta["tier"],
                "-", "-", "-", "-", "-", "-", "-", "-", earnings_countdown(ticker)
            ])
            continue

        lvl = calc_entry_levels(d, meta["tier"])
        ccy = d["currency"]
        alloc_pct = f"{meta['alloc']/budget_man*100:.0f}%" if meta["alloc"] > 0 else "-"

        rows.append([
            Fore.CYAN + ticker + Style.RESET_ALL,
            meta["name"][:10],
            {"S": Fore.RED, "A": Fore.YELLOW, "B": Fore.GREEN, "C": Fore.WHITE}.get(meta["tier"], "") + meta["tier"] + Style.RESET_ALL,
            format_price(d["price"], ccy),
            color_val(d["day_chg"]),
            color_val(d["ytd_chg"]),
            color_val(d["ret_1m"]),
            f"{d['rsi']:.0f}",
            f"{d['from_ath']:+.1f}%",
            format_price(lvl["entry"], ccy),
            format_price(lvl["stop"], ccy),
            earnings_countdown(ticker),
        ])

    headers = ["銘柄", "名前", "Tier", "現在値", "本日", "YTD", "1M", "RSI", "ATH比", "指値", "損切", "決算"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def print_momentum_screening(results: list, stocks_meta_us: dict, stocks_meta_jp: dict, top_n: int = 15):
    print_header(f"🦍 モメンタムチンパン スクリーニング TOP{top_n}")
    rows = []
    for d in results[:top_n]:
        ticker = d["ticker"]
        meta = stocks_meta_us.get(ticker) or stocks_meta_jp.get(ticker) or {}
        name = meta.get("name", ticker)[:10]
        tier = meta.get("tier", "-")
        ccy = d["currency"]
        grade = momentum_grade(d["momentum_score"])
        rows.append([
            Fore.CYAN + ticker + Style.RESET_ALL,
            name,
            {"S": Fore.RED, "A": Fore.YELLOW, "B": Fore.GREEN, "C": Fore.WHITE}.get(tier, "") + tier + Style.RESET_ALL,
            format_price(d["price"], ccy),
            color_val(d["day_chg"]),
            color_val(d["ret_1m"]),
            color_val(d["ret_3m"]),
            f"{d['rsi']:.0f}",
            f"{d['from_ath']:+.1f}%",
            f"{d['chimp_score']}",
            grade,
            d["chimp_flags"][:35],
        ])
    headers = ["銘柄", "名前", "Tier", "現在値", "本日", "1M", "3M", "RSI", "ATH比", "スコア", "グレード", "フラグ"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def print_reversal_screening(results: list, stocks_meta_us: dict, stocks_meta_jp: dict, top_n: int = 10):
    print_header(f"🔄 転換点スクリーニング（出遅れ×カタリスト） TOP{top_n}")
    rows = []
    for d in results[:top_n]:
        ticker = d["ticker"]
        meta = stocks_meta_us.get(ticker) or stocks_meta_jp.get(ticker) or {}
        name = meta.get("name", ticker)[:10]
        tier = meta.get("tier", "-")
        ccy = d["currency"]
        rows.append([
            Fore.CYAN + ticker + Style.RESET_ALL,
            name,
            tier,
            format_price(d["price"], ccy),
            color_val(d["ytd_chg"]),
            f"{d['from_ath']:+.1f}%",
            color_val(d["ret_1m"]),
            f"{d['rsi']:.0f}",
            earnings_countdown(ticker),
            f"{d['reversal_score']}",
            d["reversal_flags"][:35],
        ])
    headers = ["銘柄", "名前", "Tier", "現在値", "YTD", "ATH比", "1M", "RSI", "決算", "スコア", "フラグ"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def print_portfolio_summary(budget_man: int = 3000):
    print_header(f"💰 最強デッキ配分サマリー  総額 {budget_man:,}万円")
    deck = [
        ("NVDA",   "エヌビディア",       700, "S", "AI王者", "USD"),
        ("AVGO",   "ブロードコム",       500, "S", "AI半導体2番手", "USD"),
        ("6857.T", "アドバンテスト",     500, "S", "AI半導体テスタ", "JPY"),
        ("META",   "メタ",              300, "S", "AI広告独占", "USD"),
        ("5803.T", "フジクラ",          400, "S", "DC電線モメンタム", "JPY"),
        ("6976.T", "太陽誘電",          300, "S", "AIサーバーMLCC", "JPY"),
        ("ARM",    "ARM Holdings",     200, "S", "CPUアーキ独占", "USD"),
        ("AMD",    "AMD",              100, "A", "CPU復権波及", "USD"),
    ]
    total = sum(d[2] for d in deck)
    rows = []
    for ticker, name, alloc, tier, theme, ccy in deck:
        pct = alloc / budget_man * 100
        entry_drop = {"S": 5, "A": 5, "B": 7, "C": 10}.get(tier, 5)
        stop_pct = entry_drop + 7
        rows.append([
            ticker, name, tier, f"{alloc:,}万円", f"{pct:.1f}%",
            theme, f"現値-{entry_drop}%", f"指値-{stop_pct}%"
        ])
    print(tabulate(rows, headers=["銘柄", "名前", "Tier", "配分", "比率", "テーマ", "指値目安", "損切"], tablefmt="simple"))
    print(f"\n  合計配分: {total:,}万円 / {budget_man:,}万円  残: {budget_man-total:,}万円")
    print(f"\n  {'─'*60}")
    print(f"  損切り鉄則: 全銘柄 エントリーから -7% で即切り")
    print(f"  決算ミス : -7%待たず 即切り")
    print(f"  指値不成立: 追わない・縁がなかった")
    print(f"  最悪シナリオ(全部-7%): -{budget_man*0.07:.0f}万円 = -7%")


def print_entry_plan(all_data: dict, budget_man: int = 3000):
    print_header("📌 エントリープラン（指値・損切りライン）")
    targets = [
        ("NVDA",   700, US_STOCKS["NVDA"]["tier"]),
        ("AVGO",   500, US_STOCKS["AVGO"]["tier"]),
        ("6857.T", 500, JP_STOCKS["6857.T"]["tier"]),
        ("META",   300, US_STOCKS["META"]["tier"]),
        ("5803.T", 400, JP_STOCKS["5803.T"]["tier"]),
        ("6976.T", 300, JP_STOCKS["6976.T"]["tier"]),
        ("ARM",    200, US_STOCKS["ARM"]["tier"]),
        ("AMD",    100, US_STOCKS["AMD"]["tier"]),
    ]
    rows = []
    for ticker, alloc, tier in targets:
        d = all_data.get(ticker)
        if d is None:
            rows.append([ticker, "-", alloc, "-", "-", "-", "-", earnings_countdown(ticker)])
            continue
        lvl = calc_entry_levels(d, tier)
        ccy = d["currency"]
        action = "即打診" if tier == "S" and ticker in ("META",) else f"指値-{lvl['entry_pct']:.0f}%"
        rows.append([
            ticker,
            format_price(d["price"], ccy),
            f"{alloc:,}万",
            action,
            format_price(lvl["entry"], ccy),
            format_price(lvl["stop"], ccy),
            format_price(lvl["target"], ccy),
            earnings_countdown(ticker),
        ])
    headers = ["銘柄", "現在値", "配分", "アクション", "指値", "損切", "目標", "決算"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


# ============================================================
# メイン
# ============================================================

def main():
    print(Fore.YELLOW + """
========================================================
   Momentum Chimp - Stock Screener v1.0
   Momentum Chimp Kabu Screener
========================================================
""" + Style.RESET_ALL)

    print("  データ取得中... (米国+日本 合計40銘柄程度)")
    print("  ※ yfinance経由 リアルタイム/15分遅延\n")

    all_tickers = list(US_STOCKS.keys()) + list(JP_STOCKS.keys())
    all_data: dict = {}

    for i, ticker in enumerate(all_tickers):
        print(f"  [{i+1:2d}/{len(all_tickers)}] {ticker:<12}", end="\r")
        data = fetch_stock_data(ticker)
        if data:
            all_data[ticker] = data
        time.sleep(0.3)

    print(f"  データ取得完了: {len(all_data)}/{len(all_tickers)} 銘柄    \n")

    # 1. 最強デッキ サマリー
    print_portfolio_summary(3000)

    # 2. エントリープラン
    print_entry_plan(all_data, 3000)

    # 3. 米国株 詳細テーブル
    print_portfolio_table(all_data, US_STOCKS, "米国株 全銘柄分析", 3000)

    # 4. 日本株 詳細テーブル
    print_portfolio_table(all_data, JP_STOCKS, "日本株 全銘柄分析", 3000)

    # 5. モメンタムチンパン スクリーニング
    all_list = [d for d in all_data.values()]
    screened = screen_momentum_chimps(all_list)
    print_momentum_screening(screened, US_STOCKS, JP_STOCKS, top_n=15)

    # 6. 転換点スクリーニング
    reversal = screen_value_reversal(all_list)
    print_reversal_screening(reversal, US_STOCKS, JP_STOCKS, top_n=10)

    # 7. 今日の最優先アクション
    print_header("🎯 今日のアクション優先リスト")
    actions = [
        ("即打診", "META",   "現値で打診300万円  4/29決算前ラストチャンス"),
        ("即打診", "6976.T", "太陽誘電 現値-5%指値  AIサーバーMLCC"),
        ("指値設定","NVDA",  "$198以下 700万円  AI王者モメンタム"),
        ("指値設定","AVGO",  "$394以下 500万円  AI半導体2番手"),
        ("指値設定","6857.T","25,650円以下 500万円  4/27決算注意"),
        ("指値設定","5803.T","5,700円以下 400万円  5/14決算前"),
        ("指値設定","ARM",   "$223以下 200万円  CPU相場最終受益者"),
        ("指値設定","AMD",   "$329以下 100万円  5/5決算前"),
    ]
    rows = []
    for action, ticker, note in actions:
        d = all_data.get(ticker)
        price_str = format_price(d["price"], d["currency"]) if d else "-"
        rows.append([
            {"即打診": Fore.GREEN + "即打診" + Style.RESET_ALL,
             "指値設定": Fore.YELLOW + "指値設定" + Style.RESET_ALL}.get(action, action),
            ticker, price_str, note
        ])
    print(tabulate(rows, headers=["アクション", "銘柄", "現在値", "内容"], tablefmt="simple"))

    print("\n" + "="*80)
    print("  ⚠️  投資判断はご自身でお願いします。本プログラムは情報提供目的です。")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
