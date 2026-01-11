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
        """ENHANCED: Trend detection with price position validation"""

        # Calculate separations
        fast_slow_sep = ((ema_fast - ema_slow) / ema_slow) * 100 if ema_slow > 0 else 0

        # BULLISH TREND: EMA21 > EMA50 > EMA200
        if ema_fast > ema_slow > ema_trend:
            # Check price position relative to EMAs
            price_vs_slow = ((price - ema_slow) / ema_slow) * 100

            # Strong bullish: Price above EMA50, good EMA separation
            if price > ema_slow * 0.995 and fast_slow_sep >= self.config.ema_separation_min:
                return 'bullish'

            # Weak bullish: EMAs aligned but price lagging below EMA50
            elif price > ema_trend:  # At least above EMA200
                return 'weak_bullish'

            # Price far below EMAs = neutral (not bullish!)
            else:
                return 'neutral'

        # BEARISH TREND: EMA21 < EMA50 < EMA200
        elif ema_fast < ema_slow < ema_trend:
            price_vs_slow = ((ema_slow - price) / price) * 100
            slow_fast_sep = abs(fast_slow_sep)  # Make positive for comparison

            # Strong bearish: Price below EMA50, good EMA separation
            if price < ema_slow * 1.005 and slow_fast_sep >= self.config.ema_separation_min:
                return 'bearish'

            # Weak bearish: EMAs aligned but price leading above EMA50
            elif price < ema_trend:  # At least below EMA200
                return 'weak_bearish'

            # Price far above EMAs = neutral (not bearish!)
            else:
                return 'neutral'

        # MIXED SIGNALS: EMAs not aligned
        elif price > ema_trend and ema_fast > ema_slow:
            # Price above EMA200 with some bullish EMA structure
            return 'weak_bullish'

        elif price < ema_trend and ema_fast < ema_slow:
            # Price below EMA200 with some bearish EMA structure
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
