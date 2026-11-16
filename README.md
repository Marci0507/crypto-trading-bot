# Crypto Trading Bot (EMA + RSI Strategy)

Automated cryptocurrency trading bot built in Python using `ccxt` and `pandas`. Supports both paper trading simulation and live order execution.

## Features
- **Strategy:** Exponential Moving Average (EMA 9/21) crossover filtered by Relative Strength Index (RSI 14).
- **Risk Management:** Built-in Stop-Loss and Take-Profit thresholds.
- **Dual Mode:** Safe paper trading mode by default (`LIVE_TRADING = False`) with virtual balance tracking.
- **Logging:** Real-time console and file logging (`trading_bot.log`).

## Installation
```bash
pip install -r requirements.txt
```

## Usage
Configure your parameters in the CONFIG dictionary inside trading_bot.py and run:
```bash
python trading_bot.py
```
