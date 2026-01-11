class RiskManager:
    """
    Gestor de riesgo (trailing stops, exit conditions)
    """

    def __init__(self, config, logger, position_manager, close_position_callback):
        """
        Args:
            config: Configuración del bot
            logger: Logger para registrar información
            position_manager: Instancia de PositionManager
            close_position_callback: Función callback para cerrar posiciones
        """
        self.config = config
        self.logger = logger
        self.position_manager = position_manager
        self.close_position_callback = close_position_callback

    def update_trailing_stop_swing(self, current_price, market_data):
        """Actualiza trailing stop para swing trading"""
        if not self.position_manager.in_position or not self.position_manager.position:
            return

        position = self.position_manager.position

        if position['side'] == 'long':
            # Actualizar precio máximo
            if current_price > position['highest_price']:
                position['highest_price'] = current_price

                # Mover stop loss a breakeven cuando ganemos el threshold
                if not position['breakeven_moved']:
                    gain_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
                    if gain_pct >= self.config.breakeven_threshold:
                        position['trailing_stop'] = position['entry_price'] * 1.001  # Breakeven + 0.1%
                        position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${position['trailing_stop']:.2f}")
                        return

                # Trailing stop normal
                if position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 - self.config.trailing_stop_distance / 100)
                    if new_trailing_stop > position['trailing_stop']:
                        old_stop = position['trailing_stop']
                        position['trailing_stop'] = new_trailing_stop
                        self.logger.info(f"📈 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f}")

        else:  # SHORT
            if current_price < position['lowest_price']:
                position['lowest_price'] = current_price

                if not position['breakeven_moved']:
                    gain_pct = ((position['entry_price'] - current_price) / position['entry_price']) * 100
                    if gain_pct >= self.config.breakeven_threshold:
                        position['trailing_stop'] = position['entry_price'] * 0.999  # Breakeven - 0.1%
                        position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${position['trailing_stop']:.2f}")
                        return

                if position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 + self.config.trailing_stop_distance / 100)
                    if new_trailing_stop < position['trailing_stop']:
                        old_stop = position['trailing_stop']
                        position['trailing_stop'] = new_trailing_stop
                        self.logger.info(f"📉 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f}")

    def check_exit_conditions_swing(self, current_price, current_rsi, market_data):
        """Verifica condiciones de salida para swing trading"""
        if not self.position_manager.in_position or not self.position_manager.position:
            return

        # Actualizar trailing stop
        self.update_trailing_stop_swing(current_price, market_data)

        position = self.position_manager.position
        trend_direction = market_data.get('trend_direction', 'neutral')
        ema_fast = market_data.get('ema_fast', 0)
        ema_slow = market_data.get('ema_slow', 0)

        if position['side'] == 'long':
            # 1. Stop Loss de emergencia
            if current_price <= position['stop_loss']:
                self.close_position_callback("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return

            # 2. Take Profit objetivo
            elif current_price >= position['take_profit']:
                self.close_position_callback("Take Profit Objetivo", current_rsi, current_price, market_data)
                return

            # 3. Trailing stop dinámico
            elif current_price <= position['trailing_stop']:
                price_from_max = ((position['highest_price'] - current_price) / position['highest_price']) * 100
                self.close_position_callback(f"Trailing Stop (-{price_from_max:.1f}%)", current_rsi, current_price, market_data)
                return

            # 4. Cambio de tendencia a bajista
            elif trend_direction == 'bearish':
                self.logger.warning("⚠️ Tendencia cambió a bajista - Evaluando salida...")
                # Solo salir si también hay señales técnicas adversas
                if current_rsi > 70 or current_price < ema_fast:
                    self.close_position_callback("Cambio Tendencia Bajista", current_rsi, current_price, market_data)
                    return

            # 5. RSI muy overbought + precio bajo EMA21
            elif current_rsi > 80 and current_price < ema_fast:
                self.close_position_callback("RSI Overbought + Bajo EMA21", current_rsi, current_price, market_data)
                return

        else:  # SHORT
            # 1. Stop Loss de emergencia
            if current_price >= position['stop_loss']:
                self.close_position_callback("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return

            # 2. Take Profit objetivo
            elif current_price <= position['take_profit']:
                self.close_position_callback("Take Profit Objetivo", current_rsi, current_price, market_data)
                return

            # 3. Trailing stop dinámico
            elif current_price >= position['trailing_stop']:
                price_from_min = ((current_price - position['lowest_price']) / position['lowest_price']) * 100
                self.close_position_callback(f"Trailing Stop (+{price_from_min:.1f}%)", current_rsi, current_price, market_data)
                return

            # 4. Cambio de tendencia a alcista
            elif trend_direction == 'bullish':
                self.logger.warning("⚠️ Tendencia cambió a alcista - Evaluando salida...")
                if current_rsi < 30 or current_price > ema_fast:
                    self.close_position_callback("Cambio Tendencia Alcista", current_rsi, current_price, market_data)
                    return

            # 5. RSI muy oversold + precio sobre EMA21
            elif current_rsi < 20 and current_price > ema_fast:
                self.close_position_callback("RSI Oversold + Sobre EMA21", current_rsi, current_price, market_data)
                return
