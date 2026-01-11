from datetime import datetime


class SignalDetector:
    """
    Detector y confirmador de señales de trading
    """

    def __init__(self, config, logger, market_analyzer, performance_metrics):
        """
        Args:
            config: Configuración del bot
            logger: Logger para registrar información
            market_analyzer: Instancia de MarketAnalyzer para pullback detection
            performance_metrics: Diccionario de métricas de rendimiento
        """
        self.config = config
        self.logger = logger
        self.market_analyzer = market_analyzer
        self.performance_metrics = performance_metrics

        # Estado de señales pendientes
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.swing_wait_count = 0

        # Variables para comparación
        self.last_rsi = 50

    def detect_swing_signal(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, in_position):
        """OPTIMIZED: More flexible signal detection"""

        if self.pending_long_signal or self.pending_short_signal:
            return False

        # LONG Signal - More flexible conditions
        if (rsi < self.config.rsi_oversold and
            trend_direction in ['bullish', 'weak_bullish', 'neutral'] and  # Added flexibility
            not in_position):

            # More flexible pullback check
            is_pullback, pullback_type = self.market_analyzer.is_pullback_to_ema(price, ema_fast, ema_slow)

            # Accept signal even without perfect pullback if RSI is very low
            if is_pullback or not self.config.pullback_ema_touch or rsi < 25:
                self.pending_long_signal = True
                self.signal_trigger_price = price
                self.signal_trigger_time = datetime.now()
                self.swing_wait_count = 0

                self.performance_metrics['signals_detected'] += 1
                self.logger.info(f"🟡 FLEXIBLE LONG detected - RSI: {rsi:.2f} | Trend: {trend_direction}")
                return True

        # SHORT Signal - More flexible conditions
        elif (rsi > self.config.rsi_overbought and
              trend_direction in ['bearish', 'weak_bearish', 'neutral'] and  # Added flexibility
              not in_position):

            is_pullback, pullback_type = self.market_analyzer.is_pullback_to_ema(price, ema_fast, ema_slow)

            # Accept signal even without perfect pullback if RSI is very high
            if is_pullback or not self.config.pullback_ema_touch or rsi > 85:
                self.pending_short_signal = True
                self.signal_trigger_price = price
                self.signal_trigger_time = datetime.now()
                self.swing_wait_count = 0

                self.performance_metrics['signals_detected'] += 1
                self.logger.info(f"🟡 FLEXIBLE SHORT detected - RSI: {rsi:.2f} | Trend: {trend_direction}")
                return True

        return False

    def check_swing_confirmation(self, current_price, current_rsi, trend_direction):
        """OPTIMIZED: More flexible confirmation logic"""

        if not (self.pending_long_signal or self.pending_short_signal):
            return False, None

        self.swing_wait_count += 1

        # LONG Confirmation - More flexible
        if self.pending_long_signal:
            price_change_pct = ((current_price - self.signal_trigger_price) / self.signal_trigger_price) * 100

            # More flexible confirmation conditions
            rsi_improved = current_rsi > self.config.rsi_neutral_low or current_rsi > (self.last_rsi + 5)
            price_moved_up = price_change_pct >= self.config.swing_confirmation_threshold
            trend_not_bearish = trend_direction != 'bearish'  # Just avoid bearish

            if price_moved_up and rsi_improved and trend_not_bearish:
                self.logger.info(f"✅ FLEXIBLE LONG CONFIRMED! Price: +{price_change_pct:.2f}% | RSI: {current_rsi:.2f}")
                self.reset_signal_state()
                return True, 'long'

            # Extended wait time
            elif self.swing_wait_count >= self.config.max_swing_wait:
                self.logger.warning(f"⏰ LONG signal expired after {self.config.max_swing_wait} periods")
                self.reset_signal_state()
                return False, None

        # SHORT Confirmation - More flexible
        elif self.pending_short_signal:
            price_change_pct = ((self.signal_trigger_price - current_price) / self.signal_trigger_price) * 100

            rsi_improved = current_rsi < self.config.rsi_neutral_high or current_rsi < (self.last_rsi - 5)
            price_moved_down = price_change_pct >= self.config.swing_confirmation_threshold
            trend_not_bullish = trend_direction != 'bullish'

            if price_moved_down and rsi_improved and trend_not_bullish:
                self.logger.info(f"✅ FLEXIBLE SHORT CONFIRMED! Price: -{price_change_pct:.2f}% | RSI: {current_rsi:.2f}")
                self.reset_signal_state()
                return True, 'short'

            elif self.swing_wait_count >= self.config.max_swing_wait:
                self.logger.warning(f"⏰ SHORT signal expired after {self.config.max_swing_wait} periods")
                self.reset_signal_state()
                return False, None

        return False, None

    def reset_signal_state(self):
        """Resetea el estado de señales pendientes"""
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.swing_wait_count = 0

    def update_last_rsi(self, rsi):
        """Actualiza el último valor RSI para comparaciones"""
        self.last_rsi = rsi
