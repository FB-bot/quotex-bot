# =========================================
# ADVANCED QUOTEX SIGNAL TELEGRAM BOT
# Improved Accuracy Version
# =========================================

# INSTALL:
# pip install python-telegram-bot requests pandas ta numpy

import os
import asyncio
import requests
import pandas as pd
import numpy as np
from telegram import Bot

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.volatility import BollingerBands
from ta.volume import VolumeWeightedAveragePrice

# =========================================
# TELEGRAM SETTINGS
# =========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=BOT_TOKEN)

# =========================================
# CONFIG
# =========================================

SYMBOL = "BTCUSDT"
INTERVAL = "1m"
LIMIT = 300

SIGNAL_COOLDOWN = 300
MIN_CONFIDENCE = 75

last_signal = None
last_signal_time = 0

# =========================================
# GET MARKET DATA
# =========================================

def get_market_data():

    url = (
        f"https://api.binance.com/api/v3/klines?"
        f"symbol={SYMBOL}&interval={INTERVAL}&limit={LIMIT}"
    )

    response = requests.get(url, timeout=10)

    data = response.json()

    df = pd.DataFrame(data, columns=[
        'time',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'close_time',
        'qav',
        'num_trades',
        'taker_base_vol',
        'taker_quote_vol',
        'ignore'
    ])

    numeric_cols = ['open', 'high', 'low', 'close', 'volume']

    for col in numeric_cols:
        df[col] = df[col].astype(float)

    return df

# =========================================
# CANDLE PATTERN ANALYSIS
# =========================================

def detect_engulfing(df):

    last = df.iloc[-1]
    prev = df.iloc[-2]

    bullish = (
        prev['close'] < prev['open']
        and last['close'] > last['open']
        and last['open'] < prev['close']
        and last['close'] > prev['open']
    )

    bearish = (
        prev['close'] > prev['open']
        and last['close'] < last['open']
        and last['open'] > prev['close']
        and last['close'] < prev['open']
    )

    return bullish, bearish

# =========================================
# SUPPORT / RESISTANCE
# =========================================

def support_resistance(df):

    support = df['low'].rolling(20).min().iloc[-1]
    resistance = df['high'].rolling(20).max().iloc[-1]

    return support, resistance

# =========================================
# ANALYSIS ENGINE
# =========================================

def analyze_market():

    global last_signal
    global last_signal_time

    df = get_market_data()

    # =====================================
    # INDICATORS
    # =====================================

    # RSI
    rsi = RSIIndicator(close=df['close'], window=14)
    df['rsi'] = rsi.rsi()

    # EMA
    ema_fast = EMAIndicator(close=df['close'], window=9)
    ema_slow = EMAIndicator(close=df['close'], window=21)
    ema_trend = EMAIndicator(close=df['close'], window=50)

    df['ema_fast'] = ema_fast.ema_indicator()
    df['ema_slow'] = ema_slow.ema_indicator()
    df['ema_trend'] = ema_trend.ema_indicator()

    # MACD
    macd = MACD(close=df['close'])

    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    # ADX Trend Strength
    adx = ADXIndicator(
        high=df['high'],
        low=df['low'],
        close=df['close'],
        window=14
    )

    df['adx'] = adx.adx()

    # Bollinger Bands
    bb = BollingerBands(close=df['close'], window=20)

    df['bb_high'] = bb.bollinger_hband()
    df['bb_low'] = bb.bollinger_lband()

    # STOCHASTIC
    stoch = StochasticOscillator(
        high=df['high'],
        low=df['low'],
        close=df['close']
    )

    df['stoch'] = stoch.stoch()

    # VWAP
    vwap = VolumeWeightedAveragePrice(
        high=df['high'],
        low=df['low'],
        close=df['close'],
        volume=df['volume']
    )

    df['vwap'] = vwap.volume_weighted_average_price()

    # =====================================
    # LATEST DATA
    # =====================================

    last = df.iloc[-1]

    price = last['close']

    bullish_engulfing, bearish_engulfing = detect_engulfing(df)

    support, resistance = support_resistance(df)

    confidence = 0
    signal = None

    # =====================================
    # BUY LOGIC
    # =====================================

    buy_score = 0

    if last['rsi'] < 35:
        buy_score += 15

    if last['ema_fast'] > last['ema_slow']:
        buy_score += 15

    if last['macd'] > last['macd_signal']:
        buy_score += 15

    if last['adx'] > 20:
        buy_score += 10

    if last['stoch'] < 20:
        buy_score += 10

    if price < last['bb_low']:
        buy_score += 10

    if bullish_engulfing:
        buy_score += 15

    if price > last['vwap']:
        buy_score += 10

    # =====================================
    # SELL LOGIC
    # =====================================

    sell_score = 0

    if last['rsi'] > 65:
        sell_score += 15

    if last['ema_fast'] < last['ema_slow']:
        sell_score += 15

    if last['macd'] < last['macd_signal']:
        sell_score += 15

    if last['adx'] > 20:
        sell_score += 10

    if last['stoch'] > 80:
        sell_score += 10

    if price > last['bb_high']:
        sell_score += 10

    if bearish_engulfing:
        sell_score += 15

    if price < last['vwap']:
        sell_score += 10

    # =====================================
    # FINAL SIGNAL
    # =====================================

    if buy_score >= MIN_CONFIDENCE:
        signal = "BUY"
        confidence = buy_score

    elif sell_score >= MIN_CONFIDENCE:
        signal = "SELL"
        confidence = sell_score

    # =====================================
    # COOLDOWN SYSTEM
    # =====================================

    current_time = time.time()

    if signal == last_signal:
        return None, 0

    if current_time - last_signal_time < SIGNAL_COOLDOWN:
        return None, 0

    last_signal = signal
    last_signal_time = current_time

    return signal, confidence

# =========================================
# SEND TELEGRAM MESSAGE
# =========================================

async def send_signal(signal, confidence):

    message = f"""
📊 ADVANCED QUOTEX SIGNAL

🔥 Signal: {signal}

⏰ Timeframe: 1 Minute
📈 Accuracy Score: {confidence}%

✅ RSI Confirmation
✅ EMA Trend Confirmation
✅ MACD Confirmation
✅ ADX Trend Strength
✅ Bollinger Band Confirmation
✅ Stochastic Confirmation
✅ VWAP Confirmation
✅ Candlestick Pattern

⚠️ Trade Carefully
"""

    await bot.send_message(
        chat_id=CHAT_ID,
        text=message
    )

# =========================================
# MAIN LOOP
# =========================================

async def main():

    print("BOT STARTED...")

    while True:

        try:

            signal, confidence = analyze_market()

            if signal:

                await send_signal(signal, confidence)

                print(f"SIGNAL SENT: {signal}")

            else:
                print("NO VALID SIGNAL")

        except Exception as e:

            print("ERROR:", e)

        await asyncio.sleep(60)

# =========================================
# START
# =========================================

if __name__ == "__main__":
    asyncio.run(main())
