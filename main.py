import os
import requests
import asyncio
import sqlite3
import statistics
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair TEXT,
    signal TEXT,
    confidence INTEGER,
    result TEXT,
    time TEXT
)
''')

conn.commit()

# ======================================
# MARKET DATA
# ======================================

def get_market_data(symbol):

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

# ======================================
# EMA
# ======================================

def ema(prices, period):

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

    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)

    return ema12 - ema26

# ======================================
# BOLLINGER BANDS
# ======================================

def bollinger_bands(prices, period=20):

    sma = (
        sum(prices[-period:]) / period
    )

    variance = sum(
        (p - sma) ** 2
        for p in prices[-period:]
    ) / period

    std_dev = variance ** 0.5

    upper_band = sma + (2 * std_dev)
    lower_band = sma - (2 * std_dev)

    return upper_band, lower_band

# ======================================
# STOCHASTIC
# ======================================

def stochastic(prices):

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

    return prices[-1] - prices[-10]

# ======================================
# SUPPORT & RESISTANCE
# ======================================

def support_resistance(highs, lows):

    resistance = max(highs[-20:])
    support = min(lows[-20:])

    return support, resistance

# ======================================
# CANDLE PATTERN
# ======================================

def candle_pattern(
    opens,
    closes,
    highs,
    lows
):

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
# MARTINGALE
# ======================================

martingale_step = 0

def martingale_amount(base_amount=1):

    global martingale_step

    return base_amount * (
        2 ** martingale_step
    )

# ======================================
# SAVE SIGNAL
# ======================================

def save_signal(
    pair,
    signal,
    confidence
):

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

# ======================================
# WIN RATE
# ======================================

def get_win_rate():

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

# ======================================
# DASHBOARD
# ======================================

def dashboard():

    cursor.execute(
        "SELECT COUNT(*) FROM signals"
    )

    total = cursor.fetchone()[0]

    win_rate = get_win_rate()

    return f"""

📊 DASHBOARD

Total Signals: {total}
Win Rate: {win_rate}%
Martingale Step: {martingale_step}

"""

# ======================================
# ANALYZE MARKET
# ======================================

def analyze_pair(pair):

    opens, highs, lows, closes = get_market_data(pair)

    rsi_value = rsi(closes)

    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)

    macd_value = macd(closes)

    upper_band, lower_band = bollinger_bands(closes)

    stochastic_value = stochastic(closes)

    momentum_value = momentum(closes)

    support, resistance = support_resistance(
        highs,
        lows
    )

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

        "support": round(
            support,
            2
        ),

        "resistance": round(
            resistance,
            2
        ),

        "price": current_price

    }

# ======================================
# UPDATE RESULT
# ======================================

def update_result(pair, result):

    global martingale_step

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

    if result == "WIN":
        martingale_step = 0
    else:
        martingale_step += 1

# ======================================
# SIGNAL RESULT CHECKER
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

📍 Entry Price: {entry_price}
📍 Close Price: {close_price}

"""

        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)

        loop.run_until_complete(
            bot.send_message(
                chat_id=CHAT_ID,
                text=result_message
            )
        )

        loop.close()

    except Exception as e:

        print("Result Error:", e)

# ======================================
# SEND TELEGRAM SIGNAL
# ======================================

async def send_signal(data):

    amount = martingale_amount()

    entry_time = (
        datetime.now()
        + timedelta(minutes=1)
    )

    formatted_time = entry_time.strftime(
        "%I:%M %p"
    )

    candle_time = entry_time.strftime(
        "%H:%M"
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

🟢 Support: {data['support']}
🔴 Resistance: {data['resistance']}

💰 Martingale Amount: ${amount}

⏰ Timeframe: 1 Minute
🕒 Entry Time: {formatted_time}
🕯 Entry Candle: {candle_time} Candle

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

            print("Error:", e)

        await asyncio.sleep(60)

# ======================================
# START BOT
# ======================================

if __name__ == "__main__":

    asyncio.run(main())
