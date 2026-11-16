import time
import logging
import ccxt
import pandas as pd

CONFIG = {
    "EXCHANGE": "binance",
    "SYMBOL": "BTC/USDT",
    "TIMEFRAME": "15m",
    "LIMIT": 100,
    "CHECK_INTERVAL": 60,
    "EMA_FAST": 9,
    "EMA_SLOW": 21,
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,
    "TRADE_AMOUNT_USDT": 100.0,
    "STOP_LOSS_PCT": 0.015,
    "TAKE_PROFIT_PCT": 0.03,
    "LIVE_TRADING": False,
    "API_KEY": "YOUR_API_KEY",
    "API_SECRET": "YOUR_API_SECRET"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("trading_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)


class CryptoTraderBot:
    def __init__(self, config):
        self.cfg = config
        self.exchange = self._init_exchange()

        self.in_position = False
        self.entry_price = 0.0
        self.position_size = 0.0
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0

        self.paper_balance_usdt = 1000.0
        self.paper_balance_asset = 0.0

    def _init_exchange(self):
        exchange_class = getattr(ccxt, self.cfg["EXCHANGE"])
        exchange_params = {"enableRateLimit": True}

        if self.cfg["LIVE_TRADING"]:
            exchange_params["apiKey"] = self.cfg["API_KEY"]
            exchange_params["secret"] = self.cfg["API_SECRET"]

        exchange = exchange_class(exchange_params)
        mode = "LIVE" if self.cfg["LIVE_TRADING"] else "PAPER"
        logging.info(f"Connected to {self.cfg['EXCHANGE'].upper()} | Mode: {mode}")
        return exchange

    def fetch_market_data(self) -> pd.DataFrame:
        ohlcv = self.exchange.fetch_ohlcv(
            symbol=self.cfg["SYMBOL"],
            timeframe=self.cfg["TIMEFRAME"],
            limit=self.cfg["LIMIT"]
        )
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ema_fast"] = df["close"].ewm(span=self.cfg["EMA_FAST"], adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.cfg["EMA_SLOW"], adjust=False).mean()

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.cfg["RSI_PERIOD"]).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.cfg["RSI_PERIOD"]).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        return df

    def execute_buy(self, current_price: float):
        amount = self.cfg["TRADE_AMOUNT_USDT"] / current_price

        if self.cfg["LIVE_TRADING"]:
            try:
                order = self.exchange.create_market_buy_order(self.cfg["SYMBOL"], amount)
                executed_price = float(order.get("average") or current_price)
                self.position_size = float(order.get("filled") or amount)
                logging.info(f"[LIVE BUY] {self.position_size:.6f} {self.cfg['SYMBOL']} @ {executed_price:.2f}")
            except Exception as e:
                logging.error(f"Live buy order failed: {e}")
                return
        else:
            if self.paper_balance_usdt < self.cfg["TRADE_AMOUNT_USDT"]:
                logging.warning("Insufficient virtual USDT balance for buy order.")
                return
            executed_price = current_price
            self.position_size = amount
            self.paper_balance_usdt -= self.cfg["TRADE_AMOUNT_USDT"]
            self.paper_balance_asset += self.position_size
            logging.info(
                f"[PAPER BUY] {self.position_size:.6f} @ {executed_price:.2f} | Remaining USDT: {self.paper_balance_usdt:.2f}")

        self.in_position = True
        self.entry_price = executed_price
        self.stop_loss_price = executed_price * (1 - self.cfg["STOP_LOSS_PCT"])
        self.take_profit_price = executed_price * (1 + self.cfg["TAKE_PROFIT_PCT"])
        logging.info(f"Position opened -> SL: {self.stop_loss_price:.2f} | TP: {self.take_profit_price:.2f}")

    def execute_sell(self, current_price: float, reason: str):
        if self.cfg["LIVE_TRADING"]:
            try:
                order = self.exchange.create_market_sell_order(self.cfg["SYMBOL"], self.position_size)
                executed_price = float(order.get("average") or current_price)
                logging.info(f"[LIVE SELL - {reason}] {self.position_size:.6f} @ {executed_price:.2f}")
            except Exception as e:
                logging.error(f"Live sell order failed: {e}")
                return
        else:
            executed_price = current_price
            revenue = self.position_size * executed_price
            pnl = revenue - (self.position_size * self.entry_price)
            self.paper_balance_usdt += revenue
            self.paper_balance_asset = 0.0
            logging.info(
                f"[PAPER SELL - {reason}] @ {executed_price:.2f} | "
                f"PnL: {pnl:+.2f} USDT | New Balance: {self.paper_balance_usdt:.2f} USDT"
            )

        self.in_position = False
        self.entry_price = 0.0
        self.position_size = 0.0

    def evaluate_market(self, df: pd.DataFrame):
        prev_row = df.iloc[-3]
        last_closed = df.iloc[-2]
        current_row = df.iloc[-1]

        current_price = float(current_row["close"])
        ema_fast = float(last_closed["ema_fast"])
        ema_slow = float(last_closed["ema_slow"])
        rsi = float(last_closed["rsi"])

        logging.info(
            f"{self.cfg['SYMBOL']} Price: {current_price:.2f} | "
            f"EMA({self.cfg['EMA_FAST']}): {ema_fast:.2f} | "
            f"EMA({self.cfg['EMA_SLOW']}): {ema_slow:.2f} | "
            f"RSI: {rsi:.1f}"
        )

        if self.in_position:
            if current_price <= self.stop_loss_price:
                self.execute_sell(current_price, "STOP-LOSS REACHED")
            elif current_price >= self.take_profit_price:
                self.execute_sell(current_price, "TAKE-PROFIT REACHED")
            elif ema_fast < ema_slow:
                self.execute_sell(current_price, "TREND REVERSAL")
        else:
            bullish_cross = (float(prev_row["ema_fast"]) <= float(prev_row["ema_slow"])) and (ema_fast > ema_slow)
            rsi_ok = rsi < self.cfg["RSI_OVERBOUGHT"]

            if bullish_cross and rsi_ok:
                logging.info("BUY SIGNAL DETECTED")
                self.execute_buy(current_price)

    def run(self):
        logging.info("Trading bot started. Press Ctrl+C to stop.")
        while True:
            try:
                df = self.fetch_market_data()
                df = self.calculate_indicators(df)
                self.evaluate_market(df)
                time.sleep(self.cfg["CHECK_INTERVAL"])

            except ccxt.NetworkError as e:
                logging.warning(f"Network error, retrying in 15s: {e}")
                time.sleep(15)
            except ccxt.ExchangeError as e:
                logging.error(f"Exchange API error: {e}")
                time.sleep(30)
            except KeyboardInterrupt:
                logging.info("Bot stopped by user.")
                break
            except Exception as e:
                logging.critical(f"Unexpected error: {e}", exc_info=True)
                time.sleep(30)


if __name__ == "__main__":
    bot = CryptoTraderBot(CONFIG)
    bot.run()