import os
from datetime import datetime


class BotConfig:
    """
    Configuración centralizada para el bot de trading RSI + EMA + Filtro de Tendencia
    """

    def __init__(self, testnet=True):
        """
        Args:
            testnet: True para usar testnet, False para trading real
        """
        # Configuración básica
        self.testnet = testnet
        self.symbol = 'BTC/USDT'
        self.timeframe = '4h'  # Timeframe para swing trading

        # Configuración RSI (optimizado para 4h timeframe)
        self.rsi_period = 14
        self.rsi_oversold = 40  # Aumentado de 35 - más señales en 4h
        self.rsi_overbought = 65  # Reducido de 75 - más señales en 4h
        self.rsi_neutral_low = 45  # RSI mínimo para confirmar señal long
        self.rsi_neutral_high = 55  # RSI máximo para confirmar señal short

        # Configuración EMA
        self.ema_fast_period = 21
        self.ema_slow_period = 50
        self.ema_trend_period = 200  # EMA para filtro de tendencia principal

        # Gestión de riesgo mejorada (optimizado para 4h timeframe)
        self.leverage = 1
        self.position_size_pct = 3  # Reducido para swing trading
        self.stop_loss_pct = 2.0  # Reducido de 3% - salidas más rápidas
        self.take_profit_pct = 4.0  # Reducido de 6% - objetivos realistas (1:2 ratio)
        self.min_balance_usdt = 50
        self.min_notional_usdt = 12

        # NUEVAS VARIABLES PARA ESTRATEGIA EMA + RSI
        self.ema_separation_min = 0.1  # Mínima separación % entre EMAs para confirmar tendencia
        self.trend_confirmation_candles = 2  # Velas para confirmar cambio de tendencia
        self.pullback_ema_touch = False  # Requerir que precio toque EMA21 en pullback

        # VARIABLES PARA CONFIRMACIÓN DE SWING (optimizado para tasa confirmación)
        self.swing_confirmation_threshold = 0.15  # Reducido de 0.3% - más confirmaciones
        self.max_swing_wait = 12  # Aumentado de 6 - más paciencia (2 velas de 4h)
        self.min_time_between_signals = 7200  # 4 horas en segundos

        # VARIABLES PARA TRAILING STOP INTELIGENTE (optimizado para protección)
        self.trailing_stop_distance = 1.5  # Reducido de 2.5% - protección más ajustada
        self.breakeven_threshold = 1.0  # Reducido de 1.5% - breakeven más rápido

        # ARCHIVOS DE PERSISTENCIA (compatible con Docker)
        self.logs_dir = os.path.join(os.getcwd(), 'logs')
        self.data_dir = os.path.join(os.getcwd(), 'data')

        # Crear directorios si no existen
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        self.state_file = os.path.join(self.data_dir, f'bot_state_{datetime.now().strftime("%Y%m%d")}.json')
        self.recovery_file = os.path.join(self.logs_dir, f'recovery_log_{datetime.now().strftime("%Y%m%d")}.txt')
