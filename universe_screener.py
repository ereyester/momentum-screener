"""
モメンタムチンパン ユニバーススクリーナー
S&P500 + Nasdaq100 + 日経225 全銘柄からモメンタム最強デッキを自動生成
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from tabulate import tabulate
from colorama import init, Fore, Style
import warnings, time, argparse
warnings.filterwarnings("ignore")
init(autoreset=True)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

def _read_html_with_ua(url: str) -> list:
    import io as _io
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return pd.read_html(_io.StringIO(resp.text))


# ============================================================
# ユニバース取得
# ============================================================

def get_sp500_tickers() -> list[str]:
    try:
        tables = _read_html_with_ua(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )
        tickers = tables[0]["Symbol"].tolist()
        tickers = [t.replace(".", "-") for t in tickers]
        return tickers
    except Exception as e:
        print(f"  S&P500リスト取得失敗: {e}")
        return []


def get_nasdaq100_tickers() -> list[str]:
    try:
        tables = _read_html_with_ua("https://en.wikipedia.org/wiki/Nasdaq-100")
        for t in tables:
            if "Ticker" in t.columns or "Symbol" in t.columns:
                col = "Ticker" if "Ticker" in t.columns else "Symbol"
                return t[col].dropna().tolist()
    except Exception as e:
        print(f"  Nasdaq100リスト取得失敗: {e}")
    return []


def get_nikkei225_tickers() -> list[str]:
    try:
        tables = _read_html_with_ua("https://en.wikipedia.org/wiki/Nikkei_225")
        for t in tables:
            for col in t.columns:
                if "Code" in str(col) or "code" in str(col):
                    codes = t[col].dropna().astype(str).tolist()
                    codes = [c.zfill(4) + ".T" for c in codes if c.isdigit()]
                    if len(codes) > 50:
                        return codes
    except Exception as e:
        print(f"  日経225リスト取得失敗: {e}")

    # フォールバック: 日経225 固定リスト（2025年時点）
    print("  日経225: フォールバックリストを使用")
    codes = [
        "1332","1333","1605","1721","1801","1802","1803","1808","1812","1925",
        "1928","1963","2002","2269","2282","2413","2432","2501","2502","2503",
        "2531","2801","2802","2871","2914","3086","3099","3289","3401","3402",
        "3405","3407","3436","3659","3861","3863","4004","4005","4021","4042",
        "4043","4061","4063","4151","4183","4188","4208","4272","4324","4452",
        "4502","4503","4506","4507","4519","4523","4543","4568","4578","4631",
        "4661","4689","4704","4751","4755","4901","4902","4911","5019","5020",
        "5101","5108","5201","5202","5214","5301","5332","5333","5401","5406",
        "5411","5631","5703","5706","5707","5711","5713","5714","5801","5802",
        "5803","5831","6098","6103","6113","6141","6146","6178","6273","6301",
        "6302","6305","6326","6361","6367","6471","6472","6473","6479","6501",
        "6503","6504","6506","6508","6594","6645","6674","6701","6702","6703",
        "6724","6752","6753","6758","6762","6770","6841","6857","6861","6902",
        "6920","6952","6954","6971","6976","6981","6988","7003","7004","7011",
        "7012","7013","7201","7202","7203","7205","7211","7261","7267","7269",
        "7270","7272","7731","7733","7741","7751","7762","7832","7911","7912",
        "7974","8001","8002","8003","8015","8031","8035","8053","8058","8233",
        "8252","8267","8301","8304","8306","8308","8309","8316","8411","8591",
        "8601","8604","8630","8697","8725","8750","8766","8795","8802","8830",
        "9001","9005","9007","9008","9009","9020","9021","9022","9064","9101",
        "9104","9107","9202","9301","9432","9433","9434","9501","9502","9503",
        "9531","9532","9602","9613","9735","9766","9983","9984",
    ]
    return [c + ".T" for c in codes]


def get_jpx_tickers() -> list[str]:
    print("  (JPXから最新リストをダウンロード中...) ", end="", flush=True)
    try:
        import io as _io
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        df = pd.read_excel(_io.BytesIO(resp.content))
        
        target_markets = ["プライム（内国株式）"]
        if "市場・商品区分" in df.columns and "コード" in df.columns:
            df = df[df["市場・商品区分"].isin(target_markets)]
            codes = df["コード"].dropna().astype(str).tolist()
            # 4桁または英字含む証券コードに対応
            codes = [c + ".T" for c in codes]
            return codes
    except Exception as e:
        print(f"  JPXリスト取得失敗: {e}")

    print("  JPX取得失敗のため、フォールバック(日経225)を使用します")
    return get_nikkei225_tickers()


# レバレッジETF（爆発的リターン狙い）
LEVERAGED_ETFS = [
    "TQQQ",  # QQQ 3倍  (Nasdaq100 3x)
    "SOXL",  # SOX 3倍  (半導体指数 3x)
    "TECL",  # Tech 3倍 (Technology 3x)
    "FNGU",  # FANG+3倍 (FANG+ 3x)
    "UPRO",  # SPY 3倍  (S&P500 3x)
]


def get_universe(include_sp500: bool = True, include_ndx: bool = True,
                 include_jpx: bool = True,
                 include_leverage: bool = False) -> dict[str, str]:
    """
    Returns: {ticker: market}  market = "US" or "JP"
    include_leverage=True でレバレッジETFをユニバースに追加（デフォルトON）
    """
    universe = {}
    if include_sp500:
        print("  S&P500 リスト取得中...", end=" ", flush=True)
        sp = get_sp500_tickers()
        for t in sp:
            universe[t] = "US"
        print(f"{len(sp)}銘柄")

    if include_ndx:
        print("  Nasdaq100 リスト取得中...", end=" ", flush=True)
        ndx = get_nasdaq100_tickers()
        for t in ndx:
            universe[t] = "US"
        print(f"{len(ndx)}銘柄")

    if include_jpx:
        print("  日本株(東証全銘柄) リスト取得中...", end=" ", flush=True)
        jp = get_jpx_tickers()
        for t in jp:
            universe[t] = "JP"
        print(f"{len(jp)}銘柄")

    if include_leverage:
        for t in LEVERAGED_ETFS:
            universe[t] = "US"
        print(f"  レバレッジETF追加: {', '.join(LEVERAGED_ETFS)} ({len(LEVERAGED_ETFS)}銘柄)")

    print(f"  ユニバース合計: {len(universe)}銘柄\n")
    return universe


# ============================================================
# バッチ価格データ取得
# ============================================================

def batch_download(tickers: list[str], period: str = "1y", chunk_size: int = 100) -> tuple:
    """
    yf.download で一括取得 (個別より大幅高速)
    yfinance 1.3.x 対応: raw['Close'] が DataFrame[ticker] を返す
    """
    all_close  = {}
    all_volume = {}
    total_chunks = (len(tickers) + chunk_size - 1) // chunk_size

    for i in range(0, len(tickers), chunk_size):
        chunk    = tickers[i:i + chunk_size]
        chunk_no = i // chunk_size + 1
        print(f"  ダウンロード中 [{chunk_no}/{total_chunks}] {len(chunk)}銘柄...", end="\r", flush=True)
        try:
            raw = yf.download(
                chunk, period=period,
                auto_adjust=True, progress=False,
                threads=True
            )
            if raw is None or raw.empty:
                continue

            # yfinance 1.3.x: columns = MultiIndex (Price, Ticker)
            # raw["Close"] -> DataFrame indexed by Date, columns = tickers
            try:
                close_part  = raw["Close"]
                volume_part = raw["Volume"]

                if isinstance(close_part, pd.Series):
                    # 1銘柄のとき Series になる
                    t = chunk[0]
                    all_close[t]  = close_part
                    all_volume[t] = volume_part
                else:
                    # 複数銘柄のとき DataFrame
                    for t in close_part.columns:
                        s = close_part[t].dropna()
                        if len(s) >= 21:
                            all_close[t]  = close_part[t]
                            all_volume[t] = volume_part[t] if t in volume_part.columns else pd.Series(dtype=float)
            except (KeyError, TypeError):
                pass

        except Exception:
            pass
        time.sleep(0.4)

    print(f"  ダウンロード完了: {len(all_close)}銘柄分の価格データ取得          ")
    close_df  = pd.DataFrame(all_close) if all_close else pd.DataFrame()
    volume_df = pd.DataFrame(all_volume) if all_volume else pd.DataFrame()
    return close_df, volume_df


# ============================================================
# モメンタムスコア計算
# ============================================================

def calc_momentum_scores(close_df: pd.DataFrame, volume_df: pd.DataFrame,
                         market_map: dict[str, str]) -> pd.DataFrame:
    results = []
    tickers = close_df.columns.tolist()

    for ticker in tickers:
        try:
            s = close_df[ticker].dropna()
            if len(s) < 21:
                continue

            price     = float(s.iloc[-1])
            prev      = float(s.iloc[-2])
            day_chg   = (price - prev) / prev * 100

            high_52w  = float(s.max())
            low_52w   = float(s.min())
            from_ath  = (price - high_52w) / high_52w * 100

            ytd_s = s[s.index >= f"{datetime.now().year}-01-01"]
            ytd_chg = ((price / float(ytd_s.iloc[0])) - 1) * 100 if len(ytd_s) > 1 else 0.0

            ret_1m = ((price / float(s.iloc[-21])) - 1) * 100 if len(s) >= 21 else 0.0
            ret_3m = ((price / float(s.iloc[-63])) - 1) * 100 if len(s) >= 63 else 0.0
            ret_6m = ((price / float(s.iloc[-126])) - 1) * 100 if len(s) >= 126 else 0.0
            ret_1y = ((price / float(s.iloc[0]))   - 1) * 100

            daily_returns = s.pct_change().dropna().tail(20)
            volatility = float(daily_returns.std()) if not daily_returns.empty else 0.02

            ma5   = float(s.tail(5).mean()) if len(s) >= 5 else 0.0
            ma10  = float(s.tail(10).mean()) if len(s) >= 10 else 0.0
            ma20  = float(s.tail(20).mean())
            ma50  = float(s.tail(50).mean()) if len(s) >= 50 else 0.0
            ma200 = float(s.tail(200).mean()) if len(s) >= 200 else 0.0

            delta = s.diff()
            gain  = delta.where(delta > 0, 0.0).tail(14).mean()
            loss  = (-delta.where(delta < 0, 0.0)).tail(14).mean()
            rsi   = 100 - (100 / (1 + gain / loss)) if loss and loss != 0 else 50.0

            vol_avg = 1.0
            vol_now = 1.0
            if ticker in volume_df.columns:
                v = volume_df[ticker].dropna()
                if len(v) >= 20:
                    vol_avg = float(v.tail(20).mean())
                    vol_now = float(v.iloc[-1])
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

            # モメンタムスコア（シンプル加重平均式 - バックテスト実証済み）
            # ret_1m / ret_3m / ret_6m の加重平均のみでランキングを決定する。
            # RSI・ATH・出来高・MAは表示用の参考指標として残す。
            score = round((ret_1m * 0.4) + (ret_3m * 0.3) + (ret_6m * 0.2), 2)

            currency = "JPY" if market_map.get(ticker) == "JP" else "USD"

            results.append({
                "ticker":    ticker,
                "market":    market_map.get(ticker, "US"),
                "currency":  currency,
                "price":     price,
                "day_chg":   round(day_chg, 2),
                "ytd_chg":   round(ytd_chg, 2),
                "ret_1m":    round(ret_1m, 2),
                "ret_3m":    round(ret_3m, 2),
                "ret_6m":    round(ret_6m, 2),
                "ret_1y":    round(ret_1y, 2),
                "high_52w":  round(high_52w, 2),
                "low_52w":   round(low_52w, 2),
                "from_ath":  round(from_ath, 2),
                "rsi":       round(rsi, 1),
                "vol_ratio": round(vol_ratio, 2),
                "volatility":round(volatility, 3),
                "ma5":       round(ma5, 2),
                "ma10":      round(ma10, 2),
                "ma20":      round(ma20, 2),
                "ma50":      round(ma50, 2),
                "ma200":     round(ma200, 2),
                "score":     score,
            })
        except Exception:
            pass

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


# ============================================================
# 銘柄名取得（バッチ）
# ============================================================

def fetch_names_batch(tickers: list[str], chunk_size: int = 50) -> dict[str, str]:
    """上位銘柄の社名を取得（スコア計算後に上位だけ取得）"""
    names = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        for t in chunk:
            try:
                info = yf.Ticker(t).info
                names[t] = info.get("shortName") or info.get("longName") or t
            except Exception:
                names[t] = t
            time.sleep(0.15)
    return names


# ============================================================
# 表示
# ============================================================

def color_pct(val: float) -> str:
    if val > 0:
        return Fore.GREEN + f"{val:+.1f}%" + Style.RESET_ALL
    elif val < 0:
        return Fore.RED + f"{val:+.1f}%" + Style.RESET_ALL
    return f"{val:+.1f}%"


def fmt_price(price: float, currency: str) -> str:
    if currency == "JPY":
        return f"¥{price:,.0f}"
    return f"${price:,.2f}"


def grade(score: float) -> str:
    """スコア（ret_1m*0.4 + ret_3m*0.3 + ret_6m*0.2）のグレード表示。
    強いモメンタム銘柄の実績スコア帯を参考に設定。"""
    if score >= 60:  return Fore.RED    + "SSS" + Style.RESET_ALL
    if score >= 40:  return Fore.RED    + "SS"  + Style.RESET_ALL
    if score >= 25:  return Fore.YELLOW + "S"   + Style.RESET_ALL
    if score >= 12:  return Fore.YELLOW + "A"   + Style.RESET_ALL
    if score >=  4:  return Fore.GREEN  + "B"   + Style.RESET_ALL
    return "C"


def print_top_momentum(df: pd.DataFrame, names: dict, top_n: int = 30, market: str = "ALL"):
    width = 100
    print()
    print("=" * width)
    label = {"ALL": "米国+日本", "US": "米国", "JP": "日本"}.get(market, market)
    print(f"  🦍 モメンタムチンパン ランキング TOP{top_n}  [{label}]")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * width)

    subset = df if market == "ALL" else df[df["market"] == market]
    subset = subset.head(top_n)

    rows = []
    for rank, (_, row) in enumerate(subset.iterrows(), 1):
        t = row["ticker"]
        name = names.get(t, t)[:12]
        rows.append([
            rank,
            Fore.CYAN + t + Style.RESET_ALL,
            name,
            row["market"],
            fmt_price(row["price"], row["currency"]),
            color_pct(row["day_chg"]),
            color_pct(row["ret_1m"]),
            color_pct(row["ret_3m"]),
            color_pct(row["ytd_chg"]),
            f"{row['rsi']:.0f}",
            f"{row['from_ath']:+.1f}%",
            f"{row['score']}",
            grade(row["score"]),
        ])

    headers = ["#", "銘柄", "名前", "市場", "現在値", "本日", "1M", "3M", "YTD", "RSI", "ATH比", "Sc", "Gr"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def _get_usdjpy() -> float:
    """USD/JPY レートを取得（失敗時は150円フォールバック）"""
    try:
        ticker = yf.Ticker("USDJPY=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 150.0


def build_deck(df: pd.DataFrame, names: dict, budget_man: int = 3000,
               top_us: int = 5, top_jp: int = 3, aggressive: bool = False):
    """スクリーニング結果から最強デッキを自動生成（単位株数考慮）"""
    width = 100
    print()
    print("=" * width)
    print(f"  🏆 最強モメンタムチンパンデッキ 自動生成  予算 {budget_man:,}万円")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * width)

    usdjpy = _get_usdjpy()
    print(f"  USD/JPY: {usdjpy:.2f}円\n")

    us_top = df[df["market"] == "US"].head(top_us)
    jp_top = df[df["market"] == "JP"].head(top_jp)
    deck   = pd.concat([us_top, jp_top]).reset_index(drop=True)

    n_stocks    = len(deck)
    budget_jpy  = budget_man * 10_000  # 万円 → 円
    # 均等配分（equal weight） - バックテスト実証済みの配分方式
    target_jpy_per_stock = budget_jpy / n_stocks if n_stocks > 0 else budget_jpy

    rows = []
    actual_allocs = []

    for _, row in deck.iterrows():
        t          = row["ticker"]
        target_jpy = target_jpy_per_stock     # 均等配分（円）

        price = row["price"]
        ma5   = row.get("ma5", 0.0)
        ma10  = row.get("ma10", 0.0)
        ma20  = row["ma20"]

        if aggressive:
            vol_pct = max(0.01, min(0.05, row.get("volatility", 0.02)))
            shallow_p = price * (1.0 - vol_pct)
            if price > ma5 > 0:
                entry_p = max(ma5, shallow_p)
            elif ma5 >= price > ma10 > 0:
                entry_p = max(ma10, shallow_p)
            else:
                entry_p = max(ma20, shallow_p)
        else:
            if price > ma5 > 0:
                entry_p = ma5
            elif ma5 >= price > ma10 > 0:
                entry_p = ma10
            elif ma10 >= price > ma20 > 0:
                entry_p = ma20
            else:
                entry_p = price * 0.95  # セーフティフォールバック

        stop_p   = entry_p * 0.93
        
        # 動的利確ロジック（モメンタム＆ATHレジスタンス）
        ret_1m = row.get("ret_1m", 0.0)
        high_52w = row.get("high_52w", price * 1.5)
        from_ath = row.get("from_ath", 0.0)

        base_target_pct = max(15.0, min(50.0, ret_1m * 0.5)) / 100.0
        target_p = entry_p * (1.0 + base_target_pct)

        # ATHをまだブレイクしていない場合、ATHが強いレジスタンスになるため手前で利確
        if from_ath < -3.0:
            ath_resistance = high_52w * 0.98
            # 利確目標がATHレジスタンスを上回るが、最低でもエントリーから+5%は確保できる場合
            if target_p > ath_resistance and ath_resistance > entry_p * 1.05:
                target_p = ath_resistance

        if row["currency"] == "JPY":
            lot_size   = 100                  # 日本株: 100株単位
            entry_jpy  = entry_p              # 既に円
            shares_raw = target_jpy / entry_jpy
            shares     = max(lot_size, int(shares_raw // lot_size) * lot_size)
            cost_jpy   = shares * entry_jpy
        else:
            lot_size   = 1                    # US株: 1株単位
            entry_usd  = entry_p
            entry_jpy  = entry_usd * usdjpy
            shares_raw = target_jpy / entry_jpy
            shares     = max(1, int(shares_raw))
            cost_jpy   = shares * entry_jpy

        alloc_man = cost_jpy / 10_000

        rows.append([
            Fore.CYAN + t + Style.RESET_ALL,
            names.get(t, t)[:12],
            row["market"],
            fmt_price(row["price"], row["currency"]),
            color_pct(row["ret_1m"]),
            color_pct(row["ret_3m"]),
            f"{row['rsi']:.0f}",
            f"{row['score']}",
            f"{shares:,}株",
            f"{alloc_man:,.0f}万円",
            fmt_price(entry_p, row["currency"]),
            fmt_price(stop_p,  row["currency"]),
            fmt_price(target_p, row["currency"]),
        ])
        actual_allocs.append(alloc_man)

    headers = ["銘柄", "名前", "市場", "現在値", "1M", "3M", "RSI",
               "Sc", "株数(単元)", "実配分", "指値(-5%)", "損切(-7%)", "目標(+20%)"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))

    total_alloc = sum(actual_allocs)
    max_loss    = total_alloc * 0.07
    remaining   = budget_man - total_alloc
    print(f"\n  実配分合計: {total_alloc:,.0f}万円  |  残余資金: {remaining:,.0f}万円  |  最悪損失(-7%同時): -{max_loss:.0f}万円")
    print(f"\n  損切鉄則: エントリーから-7%で即切り  |  決算ミス: 即切り  |  指値不成立: 追わない")


def save_csv(df: pd.DataFrame, names: dict, filename: str = None):
    if filename is None:
        filename = f"universe_screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    out = df.copy()
    out["name"] = out["ticker"].map(lambda t: names.get(t, t))
    out.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\n  CSV保存: {filename} ({len(df)}銘柄)")


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="モメンタムチンパン ユニバーススクリーナー")
    parser.add_argument("--top",       type=int, default=30,    help="表示上位件数 (デフォルト30)")
    parser.add_argument("--top-us",    type=int, default=10,    help="デッキに入れる米国株数 (バックテスト実証値: 10)")
    parser.add_argument("--top-jp",    type=int, default=6,     help="デッキに入れる日本株数 (バックテスト実証値: 6)")
    parser.add_argument("--budget",    type=int, default=3000,  help="予算(万円)")
    parser.add_argument("--no-sp500",  action="store_true",     help="S&P500を除外")
    parser.add_argument("--no-ndx",    action="store_true",     help="Nasdaq100を除外")
    parser.add_argument("--no-jpx",    action="store_true",     help="日本株(東証全銘柄)を除外")
    parser.add_argument("--max-jp-price", type=int, default=None, help="日本株の株価上限（円）")
    parser.add_argument("--aggressive",action="store_true",     help="浅い指値（現在値-2%等）でアグレッシブにエントリーする")
    parser.add_argument("--csv",       action="store_true",     help="CSV出力")
    parser.add_argument("--period",    default="1y",            help="取得期間 1mo/3mo/6mo/1y (デフォルト1y)")
    args = parser.parse_args()

    print(Fore.YELLOW + """
========================================================
   Momentum Chimp Universe Screener v2.0
   S&P500 + Nasdaq100 + 東証全銘柄スクリーニング
========================================================
""" + Style.RESET_ALL)

    # 1. ユニバース取得
    print("[Step 1] ユニバース取得")
    universe = get_universe(
        include_sp500  = not args.no_sp500,
        include_ndx    = not args.no_ndx,
        include_jpx    = not args.no_jpx,
    )
    if not universe:
        print("銘柄リストを取得できませんでした。")
        return

    tickers   = list(universe.keys())
    us_tickers = [t for t, m in universe.items() if m == "US"]
    jp_tickers = [t for t, m in universe.items() if m == "JP"]

    # 2. バッチ価格ダウンロード
    print(f"[Step 2] 価格データ一括ダウンロード ({args.period})")
    close_df, volume_df = batch_download(tickers, period=args.period)

    if close_df.empty:
        print("価格データを取得できませんでした。")
        return

    # 3. モメンタムスコア計算
    print("[Step 3] モメンタムスコア計算中...")
    df = calc_momentum_scores(close_df, volume_df, universe)
    print(f"  スコア計算完了: {len(df)}銘柄")

    # 4. 上位銘柄の社名取得
    if args.max_jp_price:
        df = df[~((df["market"] == "JP") & (df["price"] > args.max_jp_price))].reset_index(drop=True)

    top_tickers = df.head(args.top + 10)["ticker"].tolist()
    print(f"[Step 4] 上位{len(top_tickers)}銘柄の社名取得中...")
    names = fetch_names_batch(top_tickers)

    # 5. 結果表示
    print_top_momentum(df, names, top_n=args.top, market="ALL")
    print_top_momentum(df, names, top_n=args.top, market="US")
    print_top_momentum(df, names, top_n=args.top, market="JP")

    # 6. 最強デッキ自動生成
    build_deck(df, names, budget_man=args.budget,
               top_us=args.top_us, top_jp=args.top_jp, aggressive=args.aggressive)

    # 7. CSV保存
    if args.csv:
        save_csv(df, names)

    print("\n" + "="*80)
    print("  ⚠️  投資判断はご自身でお願いします。本プログラムは情報提供目的です。")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
