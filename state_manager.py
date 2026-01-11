import json
import os
import time
from datetime import datetime


class StateManager:
    """
    Gestor de persistencia y recuperación de estado
    """

    def __init__(self, config, logger, exchange, position_manager, signal_detector, performance_metrics):
        """
        Args:
            config: Configuración del bot
            logger: Logger para registrar información
            exchange: Instancia del exchange (ccxt)
            position_manager: Instancia de PositionManager
            signal_detector: Instancia de SignalDetector
            performance_metrics: Diccionario de métricas de rendimiento
        """
        self.config = config
        self.logger = logger
        self.exchange = exchange
        self.position_manager = position_manager
        self.signal_detector = signal_detector
        self.performance_metrics = performance_metrics

        # Referencias a variables de estado de mercado (se establecerán desde el bot)
        self.market_state = {
            'last_signal_time': 0,
            'last_rsi': 50,
            'last_price': 0,
            'last_ema_fast': 0,
            'last_ema_slow': 0,
            'last_ema_trend': 0,
            'trend_direction': 'neutral'
        }

    def set_market_state(self, last_signal_time, last_rsi, last_price, last_ema_fast, last_ema_slow, last_ema_trend, trend_direction):
        """Actualiza referencias a las variables de estado de mercado"""
        self.market_state = {
            'last_signal_time': last_signal_time,
            'last_rsi': last_rsi,
            'last_price': last_price,
            'last_ema_fast': last_ema_fast,
            'last_ema_slow': last_ema_slow,
            'last_ema_trend': last_ema_trend,
            'trend_direction': trend_direction
        }

    def save_bot_state(self):
        """Guarda el estado actual del bot en archivo JSON"""
        try:
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                else:
                    return obj

            state_data = {
                'timestamp': datetime.now().isoformat(),
                'in_position': self.position_manager.in_position,
                'position': serialize_datetime(self.position_manager.position) if self.position_manager.position else None,
                'last_signal_time': self.market_state['last_signal_time'],
                'pending_long_signal': self.signal_detector.pending_long_signal,
                'pending_short_signal': self.signal_detector.pending_short_signal,
                'signal_trigger_price': self.signal_detector.signal_trigger_price,
                'signal_trigger_time': self.signal_detector.signal_trigger_time.isoformat() if self.signal_detector.signal_trigger_time else None,
                'swing_wait_count': self.signal_detector.swing_wait_count,
                'performance_metrics': self.performance_metrics,
                'last_rsi': self.market_state['last_rsi'],
                'last_price': self.market_state['last_price'],
                'last_ema_fast': self.market_state['last_ema_fast'],
                'last_ema_slow': self.market_state['last_ema_slow'],
                'last_ema_trend': self.market_state['last_ema_trend'],
                'trend_direction': self.market_state['trend_direction']
            }

            with open(self.config.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)

        except Exception as e:
            self.logger.error(f"Error guardando estado del bot: {e}")

    def load_bot_state(self):
        """Carga el estado previo del bot desde archivo JSON"""
        try:
            if not os.path.exists(self.config.state_file):
                self.logger.info("📄 No hay archivo de estado previo")
                return False

            with open(self.config.state_file, 'r') as f:
                state_data = json.load(f)

            # Verificar que el estado no sea muy antiguo (máximo 48 horas para swing trading)
            state_time = datetime.fromisoformat(state_data['timestamp'])
            time_diff = datetime.now() - state_time

            if time_diff.total_seconds() > 172800:  # 48 horas
                self.logger.warning(f"⏰ Estado muy antiguo ({time_diff}), no se cargará")
                return False

            # Restaurar estado de posición
            self.position_manager.in_position = state_data.get('in_position', False)

            # Restaurar estado de señales
            self.signal_detector.pending_long_signal = state_data.get('pending_long_signal', False)
            self.signal_detector.pending_short_signal = state_data.get('pending_short_signal', False)
            self.signal_detector.signal_trigger_price = state_data.get('signal_trigger_price')
            self.signal_detector.swing_wait_count = state_data.get('swing_wait_count', 0)

            # Restaurar signal_trigger_time
            if state_data.get('signal_trigger_time'):
                self.signal_detector.signal_trigger_time = datetime.fromisoformat(state_data['signal_trigger_time'])

            # Restaurar posición si existe
            if state_data.get('position'):
                self.position_manager.position = state_data['position'].copy()
                if 'entry_time' in self.position_manager.position:
                    self.position_manager.position['entry_time'] = datetime.fromisoformat(self.position_manager.position['entry_time'])

            # Restaurar métricas
            if state_data.get('performance_metrics'):
                self.performance_metrics.update(state_data['performance_metrics'])

            # Restaurar market state (será actualizado por el bot)
            self.market_state['last_signal_time'] = state_data.get('last_signal_time', 0)
            self.market_state['last_rsi'] = state_data.get('last_rsi', 50)
            self.market_state['last_price'] = state_data.get('last_price', 0)
            self.market_state['last_ema_fast'] = state_data.get('last_ema_fast', 0)
            self.market_state['last_ema_slow'] = state_data.get('last_ema_slow', 0)
            self.market_state['last_ema_trend'] = state_data.get('last_ema_trend', 0)
            self.market_state['trend_direction'] = state_data.get('trend_direction', 'neutral')

            self.logger.info(f"📥 Estado del bot cargado desde {state_time.strftime('%H:%M:%S')}")
            return True

        except Exception as e:
            self.logger.error(f"Error cargando estado del bot: {e}")
            return False

    def recover_bot_state(self):
        """Proceso completo de recuperación del estado del bot"""
        self.logger.info("🔄 Iniciando recuperación de estado...")

        # Intentar cargar estado desde archivo
        state_loaded = self.load_bot_state()

        # Verificar posiciones reales en el exchange
        exchange_position = self.check_exchange_positions()

        # Reconciliar estado
        if state_loaded and self.position_manager.in_position and exchange_position:
            self.logger.info("✅ Estado y posición recuperados correctamente")

        elif not state_loaded and exchange_position:
            self.logger.warning("⚠️ Posición encontrada sin estado guardado - Recuperando...")
            self.recover_position_from_exchange(exchange_position)

        elif state_loaded and self.position_manager.in_position and not exchange_position:
            self.logger.error("❌ Estado dice posición abierta pero no existe en exchange")
            self.logger.error("🔧 Limpiando estado inconsistente...")
            self.position_manager.position = None
            self.position_manager.in_position = False

        elif not state_loaded and not exchange_position:
            self.logger.info("✅ Bot limpio - Sin estado previo ni posiciones")

        # Guardar estado actualizado
        self.save_bot_state()

        self.logger.info("🔄 Recuperación completada")

    def check_exchange_positions(self):
        """Verifica posiciones reales en el exchange"""
        try:
            # Para futuros con apalancamiento
            try:
                if not self.config.testnet and self.config.leverage > 1:
                    self.exchange.set_sandbox_mode(False)
                    positions = self.exchange.fetch_positions([self.config.symbol])

                    for pos in positions:
                        if pos['size'] > 0:
                            self.logger.warning(f"🔍 Posición detectada en exchange: {pos['side']} {pos['size']} @ {pos['entryPrice']}")
                            return pos
            except:
                pass

            # Para spot trading
            balance = self.exchange.fetch_balance()
            btc_balance = float(balance.get('BTC', {}).get('free', 0))

            if btc_balance > 0.001:
                ticker = self.exchange.fetch_ticker(self.config.symbol)
                current_price = ticker['last']

                self.logger.warning(f"🔍 Balance BTC detectado: {btc_balance:.6f} BTC (≈${btc_balance * current_price:.2f})")

                return {
                    'side': 'long',
                    'size': btc_balance,
                    'entryPrice': current_price,
                    'symbol': self.config.symbol
                }

            return None

        except Exception as e:
            self.logger.error(f"Error verificando posiciones en exchange: {e}")
            return None

    def recover_position_from_exchange(self, exchange_position):
        """Recupera una posición desde datos del exchange"""
        try:
            current_price = exchange_position.get('entryPrice', 0)
            quantity = exchange_position.get('size', 0)
            side = exchange_position.get('side', 'long')

            # Calcular stop loss y take profit basado en precio actual
            if side == 'long':
                stop_price = current_price * (1 - self.config.stop_loss_pct / 100)
                take_profit_price = current_price * (1 + self.config.take_profit_pct / 100)
            else:
                stop_price = current_price * (1 + self.config.stop_loss_pct / 100)
                take_profit_price = current_price * (1 - self.config.take_profit_pct / 100)

            # Crear posición para monitoreo
            self.position_manager.position = {
                'side': side,
                'entry_price': current_price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': f"recovered_{int(time.time())}",
                'entry_rsi': 50,
                'recovered': True,
                'highest_price': current_price if side == 'long' else None,
                'lowest_price': current_price if side == 'short' else None,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }

            self.position_manager.in_position = True

            # Log de recuperación
            with open(self.config.recovery_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Posición recuperada: {side} {quantity} @ ${current_price:.2f}\n")

            self.logger.warning(f"🔄 POSICIÓN RECUPERADA: {side.upper()} {quantity:.6f} BTC @ ${current_price:.2f}")
            self.logger.warning(f"📊 Nuevos niveles - SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")

            self.performance_metrics['recoveries_performed'] += 1

            return True

        except Exception as e:
            self.logger.error(f"Error recuperando posición: {e}")
            return False

    def get_loaded_market_state(self):
        """Retorna el estado de mercado cargado para que el bot lo restaure"""
        return self.market_state
