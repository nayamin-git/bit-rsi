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

        # Configuración RSI
        self.rsi_period = 14
        self.rsi_oversold = 35
        self.rsi_overbought = 75
        self.rsi_neutral_low = 35  # RSI mínimo para confirmar señal long
        self.rsi_neutral_high = 65  # RSI máximo para confirmar señal short

        # Configuración EMA
        self.ema_fast_period = 21
        self.ema_slow_period = 50
        self.ema_trend_period = 200  # EMA para filtro de tendencia principal

        # Gestión de riesgo mejorada
        self.leverage = 1
        self.position_size_pct = 3  # Reducido para swing trading
        self.stop_loss_pct = 3  # Stop loss al 3%
        self.take_profit_pct = 6  # Take profit al 6% (1:2 ratio)
        self.min_balance_usdt = 50
        self.min_notional_usdt = 12

        # NUEVAS VARIABLES PARA ESTRATEGIA EMA + RSI
        self.ema_separation_min = 0.1  # Mínima separación % entre EMAs para confirmar tendencia
        self.trend_confirmation_candles = 2  # Velas para confirmar cambio de tendencia
        self.pullback_ema_touch = False  # Requerir que precio toque EMA21 en pullback

        # VARIABLES PARA CONFIRMACIÓN DE SWING
        self.swing_confirmation_threshold = 0.3  # 0.5% movimiento para confirmar swing
        self.max_swing_wait = 6  # Máximo 4 períodos de 4h para confirmación
        self.min_time_between_signals = 7200  # 4 horas en segundos

        # VARIABLES PARA TRAILING STOP INTELIGENTE
        self.trailing_stop_distance = 2.5  # % de distancia para trailing stop
        self.breakeven_threshold = 1.5  # Mover SL a breakeven cuando ganemos 1.5%

        # ARCHIVOS DE PERSISTENCIA (compatible con Docker)
        self.logs_dir = os.path.join(os.getcwd(), 'logs')
        self.data_dir = os.path.join(os.getcwd(), 'data')

        # Crear directorios si no existen
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        self.state_file = os.path.join(self.data_dir, f'bot_state_{datetime.now().strftime("%Y%m%d")}.json')
        self.recovery_file = os.path.join(self.logs_dir, f'recovery_log_{datetime.now().strftime("%Y%m%d")}.txt')
