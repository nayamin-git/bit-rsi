import time
from datetime import datetime


class PositionManager:
    """
    Gestor de posiciones (abrir, cerrar, sizing)
    """

    def __init__(self, exchange, config, logger, log_trade_callback=None, save_state_callback=None):
        """
        Args:
            exchange: Instancia del exchange (ccxt)
            config: Configuración del bot
            logger: Logger para registrar información
            log_trade_callback: Función callback para registrar trades
            save_state_callback: Función callback para guardar estado
        """
        self.exchange = exchange
        self.config = config
        self.logger = logger
        self.log_trade_callback = log_trade_callback
        self.save_state_callback = save_state_callback

        # Estado de posición
        self.position = None
        self.in_position = False

    def get_account_balance(self):
        """Obtiene el balance de la cuenta"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            return usdt_balance
        except Exception as e:
            self.logger.error(f"Error obteniendo balance: {e}")
            return 0

    def calculate_position_size(self, price):
        """Calcula el tamaño de la posición para swing trading"""
        balance = self.get_account_balance()

        if balance < self.config.min_balance_usdt:
            self.logger.warning(f"Balance insuficiente: ${balance:.2f} < ${self.config.min_balance_usdt}")
            return 0, 0

        # Calcular valor de la posición (más conservador para swing)
        position_value = balance * (self.config.position_size_pct / 100)
        effective_position = position_value * self.config.leverage

        # Verificar mínimo notional
        if effective_position < self.config.min_notional_usdt:
            self.logger.warning(f"Posición muy pequeña: ${effective_position:.2f} < ${self.config.min_notional_usdt}")
            effective_position = self.config.min_notional_usdt

        quantity = round(effective_position / price, 6)
        final_notional = quantity * price

        if final_notional < self.config.min_notional_usdt:
            self.logger.warning(f"Notional final insuficiente: ${final_notional:.2f}")
            return 0, 0

        return quantity, position_value

    def create_test_order(self, side, quantity, price):
        """Simula una orden para testnet"""
        order_id = f"swing_test_{int(time.time())}"

        fake_order = {
            'id': order_id,
            'symbol': self.config.symbol,
            'side': side,
            'amount': quantity,
            'price': price,
            'status': 'closed',
            'filled': quantity,
            'timestamp': int(time.time() * 1000),
            'info': {'test_order': True}
        }

        self.logger.info(f"🧪 ORDEN SIMULADA: {side} {quantity} BTC @ ${price:.2f}")
        return fake_order

    def open_long_position(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time=None):
        """Abre posición LONG para swing trading"""
        try:
            quantity, position_value = self.calculate_position_size(price)

            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False

            # Calcular niveles de riesgo
            stop_price = price * (1 - self.config.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.config.take_profit_pct / 100)

            # Intentar crear orden real
            try:
                if self.config.testnet:
                    order = self.exchange.create_market_order(self.config.symbol, 'buy', quantity)
                else:
                    order = self.exchange.create_market_order(self.config.symbol, 'buy', quantity)
            except Exception as order_error:
                self.logger.warning(f"Error creando orden real: {order_error}")
                order = self.create_test_order('buy', quantity, price)

            self.position = {
                'side': 'long',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi,
                'entry_ema_fast': ema_fast,
                'entry_ema_slow': ema_slow,
                'entry_ema_trend': ema_trend,
                'entry_trend_direction': trend_direction,
                'confirmation_time': confirmation_time,
                'recovered': False,
                'highest_price': price,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }

            self.in_position = True

            self.logger.info(f"🟢 SWING LONG EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Ratio: 1:{self.config.take_profit_pct/self.config.stop_loss_pct:.1f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.2f} | EMA21: ${ema_fast:.2f}")

            # Log detallado del trade
            if self.log_trade_callback:
                self.log_trade_callback('OPEN', 'long', price, quantity, rsi, ema_fast, ema_slow, ema_trend,
                              trend_direction, 'Swing Long + EMA Filter', confirmation_time=confirmation_time)

            if self.save_state_callback:
                self.save_state_callback()

            return True

        except Exception as e:
            self.logger.error(f"Error abriendo posición LONG: {e}")
            return False

    def open_short_position(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time=None):
        """Abre posición SHORT para swing trading"""
        try:
            quantity, position_value = self.calculate_position_size(price)

            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False

            stop_price = price * (1 + self.config.stop_loss_pct / 100)
            take_profit_price = price * (1 - self.config.take_profit_pct / 100)

            try:
                if self.config.testnet:
                    order = self.exchange.create_market_order(self.config.symbol, 'sell', quantity)
                else:
                    order = self.exchange.create_market_order(self.config.symbol, 'sell', quantity)
            except Exception as order_error:
                self.logger.warning(f"Error creando orden real: {order_error}")
                order = self.create_test_order('sell', quantity, price)

            self.position = {
                'side': 'short',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi,
                'entry_ema_fast': ema_fast,
                'entry_ema_slow': ema_slow,
                'entry_ema_trend': ema_trend,
                'entry_trend_direction': trend_direction,
                'confirmation_time': confirmation_time,
                'recovered': False,
                'lowest_price': price,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }

            self.in_position = True

            self.logger.info(f"🔴 SWING SHORT EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Ratio: 1:{self.config.take_profit_pct/self.config.stop_loss_pct:.1f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.2f} | EMA21: ${ema_fast:.2f}")

            if self.log_trade_callback:
                self.log_trade_callback('OPEN', 'short', price, quantity, rsi, ema_fast, ema_slow, ema_trend,
                              trend_direction, 'Swing Short + EMA Filter', confirmation_time=confirmation_time)

            if self.save_state_callback:
                self.save_state_callback()

            return True

        except Exception as e:
            self.logger.error(f"Error abriendo posición SHORT: {e}")
            return False

    def close_position(self, reason="Manual", current_rsi=None, current_price=None, market_data=None):
        """Cierra la posición actual"""
        if not self.in_position or not self.position:
            return

        try:
            side = 'sell' if self.position['side'] == 'long' else 'buy'

            # Obtener precio actual si no se proporciona
            if current_price is None:
                ticker = self.exchange.fetch_ticker(self.config.symbol)
                current_price = ticker['last']

            # Intentar crear orden de cierre
            try:
                order = self.exchange.create_market_order(self.config.symbol, side, self.position['quantity'])
            except Exception as order_error:
                self.logger.warning(f"Error creando orden de cierre: {order_error}")
                order = self.create_test_order(side, self.position['quantity'], current_price)

            # Calcular P&L
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100

            pnl_pct *= self.config.leverage

            # Calcular duración del swing
            duration_hours = (datetime.now() - self.position['entry_time']).total_seconds() / 3600

            self.logger.info(f"⭕ Posición SWING cerrada - {reason}")
            self.logger.info(f"💰 P&L: {pnl_pct:.2f}% | Duración: {duration_hours:.1f}h")

            # Log detallado del cierre
            ema_data = market_data if market_data else {}
            if self.log_trade_callback:
                self.log_trade_callback('CLOSE', self.position['side'], current_price,
                              self.position['quantity'], current_rsi,
                              ema_data.get('ema_fast', 0), ema_data.get('ema_slow', 0),
                              ema_data.get('ema_trend', 0), ema_data.get('trend_direction', 'unknown'),
                              reason, pnl_pct, duration_hours)

            self.position = None
            self.in_position = False

            if self.save_state_callback:
                self.save_state_callback()

            return True

        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
            return False
