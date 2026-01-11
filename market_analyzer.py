import pandas as pd


class MarketAnalyzer:
    """
    Analizador de datos de mercado y tendencias
    """

    def __init__(self, exchange, config, indicators, logger):
        """
        Args:
            exchange: Instancia del exchange (ccxt)
            config: Configuración del bot
            indicators: Instancia de TechnicalIndicators
            logger: Logger para registrar información
        """
        self.exchange = exchange
        self.config = config
        self.indicators = indicators
        self.logger = logger

    def get_market_data(self, log_callback=None):
        """Obtiene datos del mercado para calcular RSI y EMAs"""
        try:
            # Obtener más datos para EMAs
            limit = max(self.config.ema_trend_period + 50, 100)
            ohlcv = self.exchange.fetch_ohlcv(
                self.config.symbol,
                self.config.timeframe,
                limit=limit
            )

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # Calcular indicadores
            current_price = float(df['close'].iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            current_rsi = self.indicators.calculate_rsi(df['close'])

            # Calcular EMAs
            ema_fast = self.indicators.calculate_ema(df['close'], self.config.ema_fast_period)
            ema_slow = self.indicators.calculate_ema(df['close'], self.config.ema_slow_period)
            ema_trend = self.indicators.calculate_ema(df['close'], self.config.ema_trend_period)

            # Determinar dirección de tendencia
            trend_direction = self.determine_trend_direction(current_price, ema_fast, ema_slow, ema_trend)

            # Log datos de mercado (si se proporciona callback)
            if log_callback:
                log_callback(current_price, current_rsi, current_volume, ema_fast, ema_slow, ema_trend, trend_direction)

            return {
                'price': current_price,
                'rsi': current_rsi,
                'volume': current_volume,
                'ema_fast': ema_fast,
                'ema_slow': ema_slow,
                'ema_trend': ema_trend,
                'trend_direction': trend_direction,
                'dataframe': df
            }

        except Exception as e:
            self.logger.error(f"Error obteniendo datos del mercado: {e}")
            return None

    def determine_trend_direction(self, price, ema_fast, ema_slow, ema_trend):
        """OPTIMIZED: More flexible trend determination"""

        # Bullish: EMA21 > EMA50 > EMA200 AND price > EMA200
        if ema_fast > ema_slow and ema_slow > ema_trend and price > ema_trend:
            fast_slow_sep = ((ema_fast - ema_slow) / ema_slow) * 100
            if fast_slow_sep >= self.config.ema_separation_min:
                return 'bullish'

        # Bearish: EMA21 < EMA50 < EMA200 AND price < EMA200
        elif ema_fast < ema_slow and ema_slow < ema_trend and price < ema_trend:
            slow_fast_sep = ((ema_slow - ema_fast) / ema_fast) * 100
            if slow_fast_sep >= self.config.ema_separation_min:
                return 'bearish'

        # NEW: Weak bullish trend (price above EMA200, EMAs close)
        elif price > ema_trend and ema_fast > ema_slow:
            return 'weak_bullish'

        # NEW: Weak bearish trend (price below EMA200, EMAs close)
        elif price < ema_trend and ema_fast < ema_slow:
            return 'weak_bearish'

        return 'neutral'

    def is_pullback_to_ema(self, price, ema_fast, ema_slow):
        """Verifica si el precio está haciendo pullback a las EMAs"""
        # Para entrada long: precio cerca de EMA21 después de estar arriba
        ema_touch_threshold = 0.5  # 0.5% de distancia máxima

        distance_to_fast = abs((price - ema_fast) / ema_fast) * 100
        distance_to_slow = abs((price - ema_slow) / ema_slow) * 100

        # Pullback a EMA21 (preferido)
        if distance_to_fast <= ema_touch_threshold:
            return True, 'EMA21'

        # Pullback a EMA50 (aceptable)
        elif distance_to_slow <= ema_touch_threshold:
            return True, 'EMA50'

        # Precio entre EMAs también es válido
        elif ema_slow <= price <= ema_fast or ema_fast <= price <= ema_slow:
            return True, 'Entre_EMAs'

        return False, 'No_pullback'
