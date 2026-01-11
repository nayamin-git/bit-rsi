import pandas as pd
import numpy as np


class TechnicalIndicators:
    """
    Calculadora de indicadores técnicos (RSI, EMA)
    """

    def __init__(self, logger=None):
        """
        Args:
            logger: Logger opcional para registrar errores
        """
        self.logger = logger

    def calculate_ema(self, prices, period):
        """Calcula EMA (Exponential Moving Average)"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)

            return prices.ewm(span=period, adjust=False).mean().iloc[-1]

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calculando EMA: {e}")
            return 0

    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)

            delta = prices.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calculando RSI: {e}")
            return 50
