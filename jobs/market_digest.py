import os
from datetime import datetime
import yfinance as yf
import requests

# Slack credentials from GitHub secrets
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL_ID"]

def fetch_stats(tickers):
    """Fetch last close, percent change and volume for each ticker."""
    stats = []
    for ticker in tickers:
        # Download last two days of daily data for each ticker
        data = yf.Ticker(ticker).history(period="2d", interval="1d")
        if data.empty:
            continue
        # Latest close and previous close (if available)
        last_close = data["Close"].iloc[-1]
        prev_close = data["Close"].iloc[-2] if len(data) >= 2 else last_close
        # Compute percent change relative to previous close
        pct_change = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0
        volume = data["Volume"].iloc[-1]
        stats.append({
            "ticker": ticker,
            "last_close": float(last_close),
            "pct_change": float(pct_change),
            "volume": int(volume),
        })
    return stats

def build_message(stats):
    """Build a Slack message summarizing stock stats."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"*\ud83d\udcc5 Market Digest – {today}*"]
    for item in stats:
        lines.append(
            f"`{item['ticker']}`: Close ${item['last_close']:.2f}, "
            f"Change {item['pct_change']:+.2f}%, Vol {item['volume']:,}"
        )
    return "\n".join(lines)

def post_to_slack(text):
    """Post a message to the configured Slack channel."""
    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
        json={"channel": SLACK_CHANNEL, "text": text},
        timeout=20,
    )
    # Raise if request failed or Slack reports an error
    if response.status_code != 200 or not response.json().get("ok", False):
        raise RuntimeError(f"Slack API error: {response.text}")

def main():
    tickers = ["SHOP.TO", "TD.TO", "RY.TO", "BNS.TO", "ENB.TO"]
    stats = fetch_stats(tickers)
    if not stats:
        post_to_slack("\u26a0\ufe0f Market Digest: No data available for tickers.")
        return
    message = build_message(stats)
    post_to_slack(message)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Report failure to Slack and re-raise for debugging
        try:
            post_to_slack(f"\u274c Market Digest failed: {exc}")
        finally:
            raise
