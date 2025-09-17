import os, datetime as dt, requests, pandas as pd, yfinance as yf
from dateutil.relativedelta import relativedelta

SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL_ID"]

# ---- Watchlist (Canada focus) ----
TICKERS = {
    # US Benchmarks
    "SPY":"S&P 500", "QQQ":"Nasdaq 100", "IWM":"Russell 2000",

    # Canada Broad Market
    "XIU.TO":"S&P/TSX 60", "XIC.TO":"TSX Capped Composite",
    "ZCN.TO":"TSX Composite", "HXT.TO":"TSX 60 (swap)",

    # Banks (Big 6)
    "RY.TO":"Royal Bank", "TD.TO":"TD Bank", "BNS.TO":"Scotiabank",
    "BMO.TO":"Bank of Montreal", "CM.TO":"CIBC", "NA.TO":"National Bank",

    # Energy / Pipelines
    "CNQ.TO":"Canadian Natural", "SU.TO":"Suncor",
    "ENB.TO":"Enbridge", "TRP.TO":"TC Energy", "CVE.TO":"Cenovus",

    # Telecom
    "BCE.TO":"BCE", "T.TO":"TELUS", "RCI-B.TO":"Rogers",

    # Tech / IT
    "SHOP.TO":"Shopify (TSX)", "CSU.TO":"Constellation Software", "GIB-A.TO":"CGI",

    # Materials / Gold
    "ABX.TO":"Barrick Gold", "AEM.TO":"Agnico Eagle", "WPM.TO":"Wheaton Precious",

    # Utilities
    "FTS.TO":"Fortis", "EMA.TO":"Emera", "AQN.TO":"Algonquin",

    # Sector ETFs
    "XEG.TO":"iShares Energy", "XFN.TO":"iShares Financials", "ZEB.TO":"BMO Eq-Weight Banks",
}

def pct(a,b): return (a/b-1.0)*100 if b and b!=0 else 0.0

def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / (down.replace(0, 1e-9))
    return 100 - (100 / (1 + rs))

def post_slack(text):
    requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
        data={"channel": SLACK_CHANNEL, "text": text, "mrkdwn": True},
        timeout=20,
    )

def main():
    end   = dt.datetime.utcnow()
    start = end - relativedelta(months=13)
    syms = list(TICKERS.keys())

    data = yf.download(syms, start=start, end=end, auto_adjust=True, progress=False)
    if "Close" not in data:
        post_slack("❌ Market Digest: No price data (Yahoo blocked or tickers invalid).")
        return
    closes = data["Close"]

    lines = [f"*Daily Market Digest — {dt.datetime.now().strftime('%Y-%m-%d')}*"]

    rows = []
    for t in syms:
        try:
            s = closes[t].dropna()
        except Exception:
            continue
        if len(s) < 60:
            continue
        last = float(s.iloc[-1])
        prev = float(s.iloc[-2]) if len(s) > 1 else last
        w_ago = float(s.iloc[-6]) if len(s) > 5 else float(s.iloc[0])
        lookback = s.tail(252)
        hi52  = float(lookback.max())
        lo52  = float(lookback.min())
        rsi14 = float(rsi(s).iloc[-1])

        rows.append({
            "sym": t, "name": TICKERS[t],
            "px": last,
            "1d%": pct(last, prev),
            "5d%": pct(last, w_ago),
            "fromHi%": pct(last, hi52),
            "fromLo%": pct(last, lo52),
            "RSI14": rsi14
        })

    if not rows:
        post_slack("❌ Market Digest: No rows computed (check tickers/network).")
        return

    df = pd.DataFrame(rows).sort_values("1d%", ascending=False)

    top = df.nlargest(5, "1d%")
    bot = df.nsmallest(5, "1d%")

    def fmt_row(r):
        return (f"*{r['name']}* ({r['sym']}): {r['px']:.2f} | "
                f"1d {r['1d%']:.2f}% | 5d {r['5d%']:.2f}% | "
                f"RSI {r['RSI14']:.0f} | ΔHi {r['fromHi%']:.2f}%")

    lines.append("\n*Top movers (1d):*")
    for _, r in top.iterrows(): lines.append("• " + fmt_row(r))
    lines.append("\n*Bottom movers (1d):*")
    for _, r in bot.iterrows(): lines.append("• " + fmt_row(r))

    signals = []
    signals += [f"• *Oversold* RSI<30 → {r['name']} ({r['sym']})"
                for _, r in df[df["RSI14"] < 30].iterrows()]
    signals += [f"• *Overbought* RSI>70 → {r['name']} ({r['sym']})"
                for _, r in df[df["RSI14"] > 70].iterrows()]
    signals += [f"• *Near 52w High* (<2%): {r['name']} ({r['sym']})"
                for _, r in df[df["fromHi%"] > -2].iterrows()]  # within 2% of 52w high
    signals += [f"• *Near 52w Low* (<2%): {r['name']} ({r['sym']})"
                for _, r in df[df["fromLo%"] < 2].iterrows()]

    lines.append("\n*Signals:*" if signals else "\n*Signals:* None")
    lines += signals[:10]

    post_slack("\n".join(lines))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            post_slack(f"❌ Market Digest failed: `{e}`")
        finally:
            raise
