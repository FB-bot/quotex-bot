import os
import requests
import asyncio
import sqlite3
import threading
import time

from datetime import datetime, timedelta

from telegram import Bot

# ======================================
# TELEGRAM SETTINGS
# ======================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=BOT_TOKEN)

# ======================================
# PAIRS
# ======================================

PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT"
]

TIMEFRAME = "1m"
LIMIT = 120

# ======================================
# DATABASE
# ======================================

conn = sqlite3.connect(
    "/tmp/signals.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute(
    '''
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair TEXT,
        signal TEXT,
        confidence INTEGER,
        result TEXT,
        time TEXT
    )
    '''
)

conn.commit()

# ======================================
# MARKET DATA
# ======================================

def get_market_data(symbol):

    try:

        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={symbol}"
            f"&interval={TIMEFRAME}"
            f"&limit={LIMIT}"
        )

        response = requests.get(
            url,
            timeout=10
        )

        data = response.json()

        closes = []
        highs = []
        lows = []
        opens = []

        for candle in data:

            opens.append(float(candle[1]))
            highs.append(float(candle[2]))
            lows.append(float(candle[3]))
            closes.append(float(candle[4]))

        return opens, highs, lows, closes

    except Exception as e:

        print("Market Data Error:", e)

        return [], [], [], []

# ======================================
# EMA
# ======================================

def ema(prices, period):

    if len(prices) < period:
        return 0

    multiplier = 2 / (period + 1)

    ema_value = (
        sum(prices[:period]) / period
    )

    for price in prices[period:]:

        ema_value = (
            (price - ema_value)
            * multiplier
        ) + ema_value

    return ema_value

# ======================================
# RSI
# ======================================

def rsi(prices, period=14):

    if len(prices) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(1, period + 1):

        diff = prices[-i] - prices[-i - 1]

        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = (
        sum(gains) / period
        if gains else 0.01
    )

    avg_loss = (
        sum(losses) / period
        if losses else 0.01
    )

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )

# ======================================
# MACD
# ======================================

def macd(prices):

    return (
        ema(prices, 12)
        -
        ema(prices, 26)
    )

# ======================================
# STOCHASTIC
# ======================================

def stochastic(prices):

    if len(prices) < 14:
        return 50

    highest = max(prices[-14:])
    lowest = min(prices[-14:])

    current = prices[-1]

    if highest == lowest:
        return 50

    return (
        (current - lowest)
        /
        (highest - lowest)
    ) * 100

# ======================================
# MOMENTUM
# ======================================

def momentum(prices):

    if len(prices) < 10:
        return 0

    return prices[-1] - prices[-10]

# ======================================
# CANDLE PATTERN
# ======================================

def candle_pattern(
    opens,
    closes,
    highs,
    lows
):

    if len(opens) < 1:
        return "NONE"

    last_open = opens[-1]
    last_close = closes[-1]

    last_high = highs[-1]
    last_low = lows[-1]

    body = abs(
        last_close - last_open
    )

    wick = last_high - last_low

    if (
        last_close > last_open
        and wick > body * 2
    ):
        return "BULLISH"

    if (
        last_open > last_close
        and wick > body * 2
    ):
        return "BEARISH"

    return "NONE"

# ======================================
# SAVE SIGNAL
# ======================================

def save_signal(
    pair,
    signal,
    confidence
):

    try:

        cursor.execute(
            """
            INSERT INTO signals
            (
                pair,
                signal,
                confidence,
                result,
                time
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pair,
                signal,
                confidence,
                "PENDING",
                str(datetime.now())
            )
        )

        conn.commit()

    except Exception as e:

        print("Database Error:", e)

# ======================================
# WIN RATE
# ======================================

def get_win_rate():

    try:

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM signals
            WHERE result='WIN'
            """
        )

        wins = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM signals
            WHERE result
            IN ('WIN', 'LOSS')
            """
        )

        total = cursor.fetchone()[0]

        if total == 0:
            return 0

        return round(
            (wins / total) * 100,
            2
        )

    except:

        return 0

# ======================================
# DASHBOARD
# ======================================

def dashboard():

    try:

        cursor.execute(
            "SELECT COUNT(*) FROM signals"
        )

        total = cursor.fetchone()[0]

        win_rate = get_win_rate()

        return f"""

📊 DASHBOARD

Total Signals: {total}
Win Rate: {win_rate}%

"""

    except:

        return "Dashboard Error"

# ======================================
# ANALYZE MARKET
# ======================================

def analyze_pair(pair):

    opens, highs, lows, closes = get_market_data(pair)

    if len(closes) == 0:
        return None

    rsi_value = rsi(closes)

    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)

    macd_value = macd(closes)

    stochastic_value = stochastic(closes)

    momentum_value = momentum(closes)

    pattern = candle_pattern(
        opens,
        closes,
        highs,
        lows
    )

    current_price = closes[-1]

    # ======================================
    # BUY SCORE
    # ======================================

    buy_score = 0

    if ema_fast > ema_slow:
        buy_score += 1

    if rsi_value < 45:
        buy_score += 1

    if macd_value > 0:
        buy_score += 1

    if pattern == "BULLISH":
        buy_score += 1

    if momentum_value > 0:
        buy_score += 1

    if stochastic_value < 80:
        buy_score += 1

    # ======================================
    # SELL SCORE
    # ======================================

    sell_score = 0

    if ema_fast < ema_slow:
        sell_score += 1

    if rsi_value > 55:
        sell_score += 1

    if macd_value < 0:
        sell_score += 1

    if pattern == "BEARISH":
        sell_score += 1

    if momentum_value < 0:
        sell_score += 1

    if stochastic_value > 20:
        sell_score += 1

    # ======================================
    # FINAL SIGNAL
    # ======================================

    signal = None
    confidence = 0

    if buy_score >= 2:

        signal = "BUY"

        confidence = min(
            95,
            buy_score * 15
        )

    elif sell_score >= 2:

        signal = "SELL"

        confidence = min(
            95,
            sell_score * 15
        )

    return {

        "pair": pair,
        "signal": signal,
        "confidence": confidence,

        "rsi": round(rsi_value, 2),

        "stochastic": round(
            stochastic_value,
            2
        ),

        "momentum": round(
            momentum_value,
            2
        ),

        "pattern": pattern,

        "price": current_price

    }

# ======================================
# UPDATE RESULT
# ======================================

def update_result(pair, result):

    try:

        cursor.execute(
            """
            UPDATE signals
            SET result=?
            WHERE pair=?
            AND result='PENDING'
            """,
            (result, pair)
        )

        conn.commit()

    except Exception as e:

        print("Update Error:", e)

# ======================================
# CHECK SIGNAL RESULT
# ======================================

def check_signal_result(
    pair,
    signal,
    entry_price
):

    try:

        time.sleep(60)

        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={pair}"
            f"&interval=1m"
            f"&limit=1"
        )

        response = requests.get(
            url,
            timeout=10
        )

        data = response.json()

        close_price = float(data[0][4])

        result = "LOSS"

        if (
            signal == "BUY"
            and close_price > entry_price
        ):
            result = "WIN"

        elif (
            signal == "SELL"
            and close_price < entry_price
        ):
            result = "WIN"

        update_result(pair, result)

        result_message = f"""

📢 SIGNAL RESULT

💹 Pair: {pair}

📈 Signal: {signal}

🎯 Result: {result}

📍 Entry: {entry_price}
📍 Close: {close_price}

"""

        asyncio.run(
            bot.send_message(
                chat_id=CHAT_ID,
                text=result_message
            )
        )

    except Exception as e:

        print("Result Error:", e)

# ======================================
# SEND SIGNAL
# ======================================

async def send_signal(data):

    entry_time = (
        datetime.now()
        + timedelta(minutes=1)
    )

    formatted_time = entry_time.strftime(
        "%I:%M %p"
    )

    message = f"""

📊 ADVANCED QUOTEX SIGNAL

💹 Pair: {data['pair']}

🚀 Signal: {data['signal']}

🎯 Confidence: {data['confidence']}%

📈 RSI: {data['rsi']}
📉 Stochastic: {data['stochastic']}
⚡ Momentum: {data['momentum']}

🕯 Pattern: {data['pattern']}

⏰ Timeframe: 1 Minute
🕒 Entry Time: {formatted_time}

"""

    threading.Thread(

        target=check_signal_result,

        args=(
            data['pair'],
            data['signal'],
            data['price']
        )

    ).start()

    await bot.send_message(
        chat_id=CHAT_ID,
        text=message
    )

# ======================================
# STARTUP MESSAGE
# ======================================

async def startup_message():

    try:

        message = """

✅ ADVANCED QUOTEX BOT RUNNING

🤖 Bot Status: ACTIVE
📡 Market Scanner: ENABLED

⏳ Waiting For Signal...

"""

        await bot.send_message(
            chat_id=CHAT_ID,
            text=message
        )

    except Exception as e:

        print("Telegram Error:", e)

# ======================================
# MAIN LOOP
# ======================================

async def main():

    await startup_message()

    last_signals = {}

    while True:

        try:

            for pair in PAIRS:

                result = analyze_pair(pair)

                if result is None:
                    continue

                signal = result['signal']

                if signal:

                    previous = last_signals.get(pair)

                    if previous != signal:

                        await send_signal(result)

                        save_signal(
                            pair,
                            signal,
                            result['confidence']
                        )

                        last_signals[pair] = signal

                        print(
                            f"Signal Sent: {pair} {signal}"
                        )

                else:

                    print(
                        f"No signal: {pair}"
                    )

            print(dashboard())

        except Exception as e:

            print("Main Loop Error:", e)

        await asyncio.sleep(60)

# ======================================
# START BOT
# ======================================

if __name__ == "__main__":

    asyncio.run(main())
