from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import sqlite3
import time

app = Flask(__name__)

# --- DB Setup ---
DB_NAME = "arbitrage.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    buy_exchange TEXT,
                    sell_exchange TEXT,
                    buy_price REAL,
                    sell_price REAL,
                    profit_percent REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

init_db()

# --- Exchanges to Track ---
EXCHANGES = {
    "binance": "https://api.binance.com/api/v3/ticker/price?symbol={}",
    "kucoin": "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={}",
    "bybit": "https://api.bybit.com/v2/public/tickers?symbol={}"
}

# --- Fetch Price ---
def fetch_price(exchange, symbol):
    try:
        if exchange == "binance":
            url = EXCHANGES[exchange].format(symbol)
            data = requests.get(url, timeout=5).json()
            return float(data["price"])
        elif exchange == "kucoin":
            url = EXCHANGES[exchange].format(symbol.replace("USDT", "-USDT"))
            data = requests.get(url, timeout=5).json()
            return float(data["data"]["price"])
        elif exchange == "bybit":
            url = EXCHANGES[exchange].format(symbol)
            data = requests.get(url, timeout=5).json()
            return float(data["result"][0]["last_price"])
    except Exception as e:
        print(f"Error fetching {exchange} {symbol}: {e}")
        return None

# --- Arbitrage Scanner ---
def scan_arbitrage():
    symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
    opportunities = []

    for sym in symbols:
        prices = {}
        for ex in EXCHANGES:
            p = fetch_price(ex, sym)
            if p:
                prices[ex] = p

        if len(prices) >= 2:
            min_ex = min(prices, key=prices.get)
            max_ex = max(prices, key=prices.get)

            buy_price = prices[min_ex]
            sell_price = prices[max_ex]

            profit_percent = ((sell_price - buy_price) / buy_price) * 100

            if profit_percent > 0.5:  # Only save profitable spreads above 0.5%
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO opportunities (symbol, buy_exchange, sell_exchange, buy_price, sell_price, profit_percent) VALUES (?, ?, ?, ?, ?, ?)",
                          (sym, min_ex, max_ex, buy_price, sell_price, profit_percent))
                conn.commit()
                conn.close()

                opportunities.append({
                    "symbol": sym,
                    "buy_exchange": min_ex,
                    "sell_exchange": max_ex,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "profit_percent": round(profit_percent, 2)
                })

    return opportunities

# --- Scheduler ---
scheduler = BackgroundScheduler()
scheduler.add_job(scan_arbitrage, "interval", seconds=60)
scheduler.start()

# --- Routes ---
@app.route("/")
def home():
    return "<h2>🚀 Arbitrage Scanner Running...</h2><p>Visit /opportunities for live results</p>"

@app.route("/opportunities")
def get_opportunities():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT symbol, buy_exchange, sell_exchange, buy_price, sell_price, profit_percent, timestamp FROM opportunities ORDER BY timestamp DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "symbol": r[0],
            "buy_exchange": r[1],
            "sell_exchange": r[2],
            "buy_price": r[3],
            "sell_price": r[4],
            "profit_percent": round(r[5], 2),
            "timestamp": r[6]
        })
    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
