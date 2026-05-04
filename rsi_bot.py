import time
import os
import ccxt
from datetime import datetime

BOT_VERSION = "2.2.1"
from dotenv import load_dotenv
from config import BotConfig
from claude_advisor import ClaudeAdvisor, ParamAdjustments
from indicators import TechnicalIndicators
from market_analyzer import MarketAnalyzer
from signal_detector import SignalDetector
from position_manager import PositionManager
from risk_manager import RiskManager
from state_manager import StateManager
from analytics import Analytics
from logging_manager import LoggingManager
from exchange_client import ExchangeClient

# Cargar variables de entorno
load_dotenv()

# Límites seguros para ajuste dinámico de parámetros por Claude
_PARAM_BOUNDS = {
    'rsi_oversold':                  (30,  45),
    'rsi_overbought':                (60,  75),
    'stop_loss_pct':                 (1.0, 3.5),
    'take_profit_pct':               (2.5, 7.0),
    'swing_confirmation_threshold':  (0.10, 0.40),
    'trailing_stop_distance':        (0.8, 3.0),
    'breakeven_threshold':           (0.5, 2.0),
}

class BinanceRSIEMABot:
    def __init__(self, api_key, api_secret, testnet=True):
        """
        Bot de trading RSI + EMA + Filtro de Tendencia para Binance - v2.1

        Args:
            api_key: Tu API key de Binance
            api_secret: Tu API secret de Binance
            testnet: True para usar testnet, False para trading real
        """

        # Configuración centralizada
        self.config = BotConfig(testnet)

        # IMPORTANTE: Configurar logging PRIMERO
        self.logging_manager = LoggingManager(
            self.config.logs_dir,
            close_callback=lambda reason: self.close_position(reason),
            save_state_callback=lambda: self.save_bot_state(),
            log_summary_callback=lambda: self.log_performance_summary()
        )
        self.logger = self.logging_manager.setup_logging()

        # Inicializar módulo de indicadores técnicos
        self.indicators = TechnicalIndicators(self.logger)

        # Estado del bot
        self.last_signal_time = 0
        self.last_claude_scan_time = 0  # Último escaneo proactivo de mercado con Claude

        # Variables de estado de mercado (para tracking)
        self.last_rsi = 50
        self.last_price = 0
        self.last_ema_fast = 0
        self.last_ema_slow = 0
        self.last_ema_trend = 0
        self.trend_direction = 'neutral'  # 'bullish', 'bearish', 'neutral'
        
        # Historial de datos para análisis
        self.price_history = []
        self.ema_history = {'fast': [], 'slow': [], 'trend': []}
        
        # Métricas para análisis
        self.trades_log = []
        self.market_data_log = []
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'consecutive_losses': 0,
            'max_consecutive_losses': 0,
            'signals_detected': 0,
            'signals_confirmed': 0,
            'signals_expired': 0,
            'recoveries_performed': 0,
            'trend_filters_applied': 0,
            'ema_confirmations': 0,
            'pullback_entries': 0
        }
        
        # Configuración del exchange DESPUÉS de definir variables
        self.exchange_client = ExchangeClient(api_key, api_secret, self.config, self.logger)
        self.exchange = self.exchange_client.exchange  # Backward compatibility

        # Inicializar módulo de análisis de mercado
        self.market_analyzer = MarketAnalyzer(self.exchange, self.config, self.indicators, self.logger)

        # Inicializar módulo de detección de señales
        self.signal_detector = SignalDetector(self.config, self.logger, self.market_analyzer, self.performance_metrics)

        # Inicializar módulo de gestión de posiciones
        self.position_manager = PositionManager(
            self.exchange,
            self.config,
            self.logger,
            log_trade_callback=self.log_trade,
            save_state_callback=self.save_bot_state
        )

        # Inicializar módulo de gestión de riesgo
        self.risk_manager = RiskManager(
            self.config,
            self.logger,
            self.position_manager,
            close_position_callback=self.close_position
        )

        # Inicializar módulo de gestión de estado
        self.state_manager = StateManager(
            self.config,
            self.logger,
            self.exchange,
            self.position_manager,
            self.signal_detector,
            self.performance_metrics
        )

        # Inicializar módulo de analytics (debe ser después de position_manager)
        self.analytics = Analytics(
            self.config,
            self.logger,
            self.position_manager,
            self.signal_detector,
            get_balance_callback=self.get_account_balance
        )
        self.analytics.set_performance_metrics(self.performance_metrics)

        # Inicializar Claude Advisor (opcional — requiere ANTHROPIC_API_KEY)
        self.claude_advisor = None
        if self.config.use_claude_advisor and os.getenv('ANTHROPIC_API_KEY'):
            try:
                self.claude_advisor = ClaudeAdvisor(self.logger)
                self.logger.info("🤖 Claude Advisor activo — validación de señales habilitada")
            except Exception as e:
                self.logger.warning(f"Claude Advisor no disponible: {e}")
        elif self.config.use_claude_advisor:
            self.logger.warning(
                "⚠️  ANTHROPIC_API_KEY no configurada — Claude Advisor desactivado. "
                "El bot opera sin validación AI. Configura la variable en .env para activarlo."
            )

        # Configurar callback de in_position para logging_manager
        self.logging_manager.set_in_position_callback(lambda: self.position_manager.in_position)

        # Verificar conexión con retry para tolerar fallos de red al arrancar
        for _attempt in range(1, 4):
            try:
                self.verify_connection()
                break
            except Exception as e:
                if _attempt < 3:
                    self.logger.warning(
                        f"⚠️ Intento {_attempt}/3 fallido al conectar con Binance: {e}. "
                        f"Reintentando en 10s..."
                    )
                    time.sleep(10)
                else:
                    self.logger.error("❌ No se pudo conectar con Binance tras 3 intentos")
                    raise

        # Inicializar archivos de logs al final
        self.init_log_files()

        # Recuperar estado y posiciones al iniciar
        self.recover_bot_state()

        # Restaurar variables de estado de mercado desde state_manager
        loaded_state = self.state_manager.get_loaded_market_state()
        self.last_signal_time = loaded_state['last_signal_time']
        self.last_rsi = loaded_state['last_rsi']
        self.last_price = loaded_state['last_price']
        self.last_ema_fast = loaded_state['last_ema_fast']
        self.last_ema_slow = loaded_state['last_ema_slow']
        self.last_ema_trend = loaded_state['last_ema_trend']
        self.trend_direction = loaded_state['trend_direction']

    def setup_logging(self):
        """Configura sistema de logging - delegado a logging_manager"""
        return self.logging_manager.setup_logging()

    def _signal_handler(self, signum, frame):
        """Maneja señales de Docker - delegado a logging_manager"""
        self.logging_manager._signal_handler(signum, frame)
        
    def verify_connection(self):
        """Verifica la conexión con Binance - delegado a exchange_client"""
        return self.exchange_client.verify_connection()
    
    def calculate_ema(self, prices, period):
        """Calcula EMA (Exponential Moving Average) - delegado a indicators"""
        return self.indicators.calculate_ema(prices, period)

    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI - delegado a indicators"""
        return self.indicators.calculate_rsi(prices, period)
    
    def get_market_data(self):
        """Obtiene datos del mercado para calcular RSI y EMAs - delegado a market_analyzer"""
        return self.market_analyzer.get_market_data(log_callback=self.log_market_data)
    
    def determine_trend_direction(self, price, ema_fast, ema_slow, ema_trend):
        """Determinar dirección de tendencia - delegado a market_analyzer"""
        return self.market_analyzer.determine_trend_direction(price, ema_fast, ema_slow, ema_trend)

    def is_pullback_to_ema(self, price, ema_fast, ema_slow):
        """Verifica si el precio está haciendo pullback a las EMAs - delegado a market_analyzer"""
        return self.market_analyzer.is_pullback_to_ema(price, ema_fast, ema_slow)
    
    def detect_swing_signal(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction):
        """Detecta señales de swing - delegado a signal_detector"""
        return self.signal_detector.detect_swing_signal(price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, self.position_manager.in_position)

    def check_swing_confirmation(self, current_price, current_rsi, trend_direction):
        """Confirma señales de swing - delegado a signal_detector"""
        return self.signal_detector.check_swing_confirmation(current_price, current_rsi, trend_direction)

    def reset_signal_state(self):
        """Resetea el estado de señales pendientes - delegado a signal_detector"""
        self.signal_detector.reset_signal_state()
    
    def log_market_data(self, price, rsi, volume, ema_fast, ema_slow, ema_trend, trend_direction, signal=None):
        """Registra datos de mercado con EMAs"""
        timestamp = datetime.now()
        
        # Calcular PnL no realizado si estamos en posición
        unrealized_pnl = 0
        if self.position_manager.in_position and self.position_manager.position:
            pos = self.position_manager.position
            if pos['side'] == 'long':
                unrealized_pnl = ((price - pos['entry_price']) / pos['entry_price']) * 100 * self.config.leverage
            else:
                unrealized_pnl = ((pos['entry_price'] - price) / pos['entry_price']) * 100 * self.config.leverage

        # Estado de señal pendiente
        pending_signal = ""
        if self.signal_detector.pending_long_signal:
            pending_signal = f"LONG_WAIT_{self.signal_detector.swing_wait_count}/{self.config.max_swing_wait}"
        elif self.signal_detector.pending_short_signal:
            pending_signal = f"SHORT_WAIT_{self.signal_detector.swing_wait_count}/{self.config.max_swing_wait}"
        
        # Actualizar variables de estado
        self.last_rsi = rsi
        self.last_price = price
        self.last_ema_fast = ema_fast
        self.last_ema_slow = ema_slow
        self.last_ema_trend = ema_trend
        self.trend_direction = trend_direction

        # Actualizar signal_detector también
        self.signal_detector.update_last_rsi(rsi)

        # Actualizar state_manager con el estado de mercado actual
        self.state_manager.set_market_state(
            self.last_signal_time, self.last_rsi, self.last_price,
            self.last_ema_fast, self.last_ema_slow, self.last_ema_trend,
            self.trend_direction
        )

        # Actualizar analytics con el estado de mercado actual
        self.analytics.set_market_state(
            self.last_ema_fast, self.last_ema_slow, self.last_ema_trend,
            self.trend_direction
        )
        
        # Actualizar historiales
        self.price_history.append(price)
        self.ema_history['fast'].append(ema_fast)
        self.ema_history['slow'].append(ema_slow)
        self.ema_history['trend'].append(ema_trend)

        # Mantener solo los últimos 50 registros
        if len(self.price_history) > 50:
            self.price_history = self.price_history[-50:]
            for key in self.ema_history:
                self.ema_history[key] = self.ema_history[key][-50:]

        # Escribir al CSV de datos de mercado
        position_side = None
        if self.position_manager.in_position and self.position_manager.position:
            position_side = self.position_manager.position['side']
        self.analytics.log_market_data(
            timestamp, price, rsi, volume, ema_fast, ema_slow, ema_trend,
            trend_direction, signal,
            self.position_manager.in_position, position_side,
            unrealized_pnl, pending_signal
        )
    
    def save_bot_state(self):
        """Guarda el estado del bot - delegado a state_manager"""
        # Actualizar estado de mercado antes de guardar
        self.state_manager.set_market_state(
            self.last_signal_time, self.last_rsi, self.last_price,
            self.last_ema_fast, self.last_ema_slow, self.last_ema_trend,
            self.trend_direction
        )
        self.state_manager.save_bot_state()

    def load_bot_state(self):
        """Carga el estado del bot - delegado a state_manager"""
        return self.state_manager.load_bot_state()

    def recover_bot_state(self):
        """Recuperación completa de estado - delegado a state_manager"""
        self.state_manager.recover_bot_state()

    def check_exchange_positions(self):
        """Verifica posiciones en el exchange - delegado a state_manager"""
        return self.state_manager.check_exchange_positions()

    def recover_position_from_exchange(self, exchange_position):
        """Recupera posición desde el exchange - delegado a state_manager"""
        return self.state_manager.recover_position_from_exchange(exchange_position)
    
    def init_log_files(self):
        """Inicializa archivos CSV - delegado a analytics"""
        self.analytics.init_log_files()
        # Mantener referencias para backward compatibility
        self.trades_csv = self.analytics.trades_csv
        self.market_csv = self.analytics.market_csv
    
    def get_account_balance(self):
        """Obtiene el balance de la cuenta - delegado a position_manager"""
        return self.position_manager.get_account_balance()

    def calculate_position_size(self, price):
        """Calcula el tamaño de la posición - delegado a position_manager"""
        return self.position_manager.calculate_position_size(price)

    def create_test_order(self, side, quantity, price):
        """Simula una orden - delegado a position_manager"""
        return self.position_manager.create_test_order(side, quantity, price)
    
    def open_long_position(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time=None):
        """Abre posición LONG - delegado a position_manager"""
        return self.position_manager.open_long_position(price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time)

    def open_short_position(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time=None):
        """Abre posición SHORT - delegado a position_manager"""
        return self.position_manager.open_short_position(price, rsi, ema_fast, ema_slow, ema_trend, trend_direction, confirmation_time)

    def close_position(self, reason="Manual", current_rsi=None, current_price=None, market_data=None):
        """Cierra la posición actual - delegado a position_manager"""
        return self.position_manager.close_position(reason, current_rsi, current_price, market_data)
    
    def update_trailing_stop_swing(self, current_price, market_data):
        """Actualiza trailing stop - delegado a risk_manager"""
        self.risk_manager.update_trailing_stop_swing(current_price, market_data)

    def check_exit_conditions_swing(self, current_price, current_rsi, market_data):
        """Verifica condiciones de salida - delegado a risk_manager"""
        self.risk_manager.check_exit_conditions_swing(current_price, current_rsi, market_data)
    
    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None,
                  ema_fast=None, ema_slow=None, ema_trend=None, trend_direction=None,
                  reason=None, pnl_pct=None, duration_hours=None, confirmation_time=None):
        """Registra trades - delegado a analytics"""
        self.analytics.log_trade(action, side, price, quantity, rsi, ema_fast, ema_slow,
                                ema_trend, trend_direction, reason, pnl_pct, duration_hours, confirmation_time)

    def update_performance_metrics(self, pnl_pct):
        """Actualiza métricas de rendimiento - delegado a analytics"""
        self.analytics.update_performance_metrics(pnl_pct)
    
    def _log_position_status(self, market_data):
        """Registra en consola el estado de mercado o posición abierta"""
        current_price = market_data['price']
        current_rsi = market_data['rsi']
        ema_fast = market_data['ema_fast']
        ema_slow = market_data['ema_slow']
        ema_trend = market_data['ema_trend']
        trend_direction = market_data['trend_direction']

        if self.position_manager.in_position and self.position_manager.position:
            position = self.position_manager.position
            if position['side'] == 'long':
                pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
                max_price = position.get('highest_price', current_price)
                trailing_stop = position.get('trailing_stop', 0)
                self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Max: ${max_price:.2f} | TS: ${trailing_stop:.2f}")
            else:
                pnl_pct = ((position['entry_price'] - current_price) / position['entry_price']) * 100
                min_price = position.get('lowest_price', current_price)
                trailing_stop = position.get('trailing_stop', 0)
                self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Min: ${min_price:.2f} | TS: ${trailing_stop:.2f}")
        else:
            ema_order = "📈" if ema_fast > ema_slow > ema_trend else "📉" if ema_fast < ema_slow < ema_trend else "🔄"
            self.logger.info(f"{ema_order} BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")

        self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f}")

    def _handle_confirmed_signal(self, signal_type, market_data, current_time):
        """Abre posición cuando una señal pendiente es confirmada"""
        current_price = market_data['price']
        current_rsi = market_data['rsi']
        ema_fast = market_data['ema_fast']
        ema_slow = market_data['ema_slow']
        ema_trend = market_data['ema_trend']
        trend_direction = market_data['trend_direction']

        if self.claude_advisor:
            decision = self.claude_advisor.validate_signal(signal_type, market_data)
            if decision and decision.action == "REJECT":
                self.logger.warning(
                    f"🤖 Claude RECHAZÓ señal {signal_type.upper()} "
                    f"(confianza: {decision.confidence}%): {decision.reasoning}"
                )
                self.signal_detector.reset_signal_state()
                return
            elif decision:
                self.logger.info(
                    f"🤖 Claude CONFIRMÓ señal {signal_type.upper()} "
                    f"(confianza: {decision.confidence}%): {decision.reasoning[:120]}"
                )

        confirmation_time_hours = 0
        if self.signal_detector.signal_trigger_time:
            confirmation_time_hours = (datetime.now() - self.signal_detector.signal_trigger_time).total_seconds() / 3600

        if signal_type == 'long':
            if self.open_long_position(current_price, current_rsi, ema_fast, ema_slow,
                                       ema_trend, trend_direction, confirmation_time_hours):
                self.last_signal_time = current_time
        elif signal_type == 'short':
            if self.open_short_position(current_price, current_rsi, ema_fast, ema_slow,
                                        ema_trend, trend_direction, confirmation_time_hours):
                self.last_signal_time = current_time

    def _scan_for_new_signal(self, market_data, current_time):
        """Busca nuevas señales si ha pasado el tiempo mínimo entre señales"""
        if current_time - self.last_signal_time >= self.config.min_time_between_signals:
            self.detect_swing_signal(
                market_data['price'], market_data['rsi'],
                market_data['ema_fast'], market_data['ema_slow'],
                market_data['ema_trend'], market_data['trend_direction']
            )

        if (self.claude_advisor and
                current_time - self.last_claude_scan_time >= self.config.claude_scan_interval):
            self.last_claude_scan_time = current_time
            context = self.claude_advisor.analyze_market_context(market_data)
            if context:
                icon = "📈" if context.bias == "long" else "📉" if context.bias == "short" else "➡️"
                forming = " — SETUP FORMÁNDOSE" if context.setup_forming else ""
                self.logger.info(
                    f"🤖 Claude [{icon} {context.bias.upper()} {context.confidence}%]{forming}: "
                    f"{context.reasoning[:150]}"
                )
                if context.key_levels:
                    self.logger.info(f"🤖 Niveles clave: {context.key_levels}")

            adjustments = self.claude_advisor.suggest_param_adjustments(
                market_data, self._current_params()
            )
            if adjustments:
                self._apply_param_adjustments(adjustments)

    def _current_params(self) -> dict:
        return {param: getattr(self.config, param) for param in _PARAM_BOUNDS}

    def _apply_param_adjustments(self, adjustments: ParamAdjustments) -> None:
        changes = []
        for param, (lo, hi) in _PARAM_BOUNDS.items():
            suggested = getattr(adjustments, param)
            clamped = max(lo, min(hi, suggested))
            current = getattr(self.config, param)
            if abs(clamped - current) > 1e-9:
                setattr(self.config, param, type(current)(clamped))
                changes.append(f"{param}: {current} → {type(current)(clamped)}")
        if changes:
            self.logger.info(
                f"🤖 Claude ajustó parámetros [{adjustments.regime}]: {', '.join(changes)}"
            )
            self.logger.info(f"🤖 Motivo: {adjustments.reasoning}")
        else:
            self.logger.debug(f"🤖 Claude evaluó parámetros [{adjustments.regime}]: sin cambios necesarios")

    def analyze_and_trade(self):
        """Análisis principal y ejecución de trades para swing"""
        market_data = self.get_market_data()
        if not market_data:
            return

        current_price = market_data['price']
        current_rsi = market_data['rsi']
        trend_direction = market_data['trend_direction']

        self._log_position_status(market_data)
        self.check_exit_conditions_swing(current_price, current_rsi, market_data)

        if self.position_manager.in_position:
            return

        current_time = time.time()
        confirmed, signal_type = self.check_swing_confirmation(current_price, current_rsi, trend_direction)

        if confirmed:
            self._handle_confirmed_signal(signal_type, market_data, current_time)
        elif not (self.signal_detector.pending_long_signal or self.signal_detector.pending_short_signal):
            self._scan_for_new_signal(market_data, current_time)
    
    def run(self):
        """Ejecuta el bot en un loop continuo optimizado para swing trading"""
        self.logger.info(f"🤖 RSI + EMA + Trend Filter Swing Bot v{BOT_VERSION} iniciado")
        self.logger.info(f"📊 Timeframe: {self.config.timeframe} | RSI({self.config.rsi_period}) | OS: {self.config.rsi_oversold} | OB: {self.config.rsi_overbought}")
        self.logger.info(f"📈 EMAs: Fast({self.config.ema_fast_period}) | Slow({self.config.ema_slow_period}) | Trend({self.config.ema_trend_period})")
        self.logger.info(f"⚡ Leverage: {self.config.leverage}x | Risk: {self.config.position_size_pct}% | SL: {self.config.stop_loss_pct}% | TP: {self.config.take_profit_pct}%")
        self.logger.info(f"🎯 Swing Confirmación: {self.config.swing_confirmation_threshold}% | Max espera: {self.config.max_swing_wait} períodos")
        self.logger.info(f"🛡️ Trailing Stop: {self.config.trailing_stop_distance}% | Breakeven: {self.config.breakeven_threshold}%")
        self.logger.info(f"💾 Estado guardado en: {self.config.state_file}")
        self.logger.info(f"🐳 Ejecutándose en Docker - PID: {os.getpid()}")
        
        # Para swing trading, verificar cada 30 minutos (timeframe 4h)
        check_interval = 1800  # 30 minutos en segundos
        iteration = 0
        
        try:
            while True:
                try:
                    # Main trading logic with error recovery
                    self.analyze_and_trade()

                    # Mostrar resumen cada 4 horas (8 iteraciones de 30 min)
                    iteration += 1
                    if iteration % 8 == 0:
                        self.log_performance_summary()

                    # Guardar estado cada hora (2 iteraciones)
                    if iteration % 2 == 0:
                        self.save_bot_state()

                    time.sleep(check_interval)

                except ccxt.NetworkError as e:
                    # Network errors: retry without crashing
                    self.logger.error(f"🌐 Error de red: {e}")
                    self.logger.info("♻️ Reintentando en 60 segundos...")
                    time.sleep(60)
                    continue

                except ccxt.ExchangeError as e:
                    # Exchange errors: log and retry
                    self.logger.error(f"🏦 Error del exchange: {e}")
                    self.logger.info("♻️ Reintentando en 60 segundos...")
                    time.sleep(60)
                    continue

                except Exception as e:
                    # Unexpected errors: log with traceback but don't crash
                    self.logger.error(f"⚠️ Error inesperado: {e}", exc_info=True)
                    self.logger.info("♻️ Continuando en 60 segundos...")
                    # Save state on unexpected errors
                    try:
                        self.save_bot_state()
                    except:
                        pass
                    time.sleep(60)
                    continue

        except KeyboardInterrupt:
            self.logger.info("🛑 Bot detenido por el usuario (KeyboardInterrupt)")
            if self.position_manager.in_position:
                self.close_position("Bot detenido")
            self.save_bot_state()
            self.log_performance_summary()

        except Exception as e:
            # Fatal errors that should stop the bot
            self.logger.error(f"❌ Error fatal en el bot: {e}", exc_info=True)
            if self.position_manager.in_position:
                try:
                    self.close_position("Error fatal del bot")
                except:
                    self.logger.error("No se pudo cerrar la posición")
            try:
                self.save_bot_state()
            except:
                self.logger.error("No se pudo guardar el estado")
            raise
    
    def log_performance_summary(self):
        """Muestra resumen de performance - delegado a analytics"""
        # Actualizar analytics con estado de mercado actual
        self.analytics.set_market_state(
            self.last_ema_fast, self.last_ema_slow, self.last_ema_trend,
            self.trend_direction
        )
        self.analytics.log_performance_summary()


# Ejemplo de uso optimizado para swing trading
if __name__ == "__main__":
    
    print("🐳 RSI + EMA + Trend Filter Swing Bot - Docker Edition")
    print(f"🐳 Python PID: {os.getpid()}")
    print(f"🐳 Working Directory: {os.getcwd()}")
    
    # Configuración con variables de entorno
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    if not API_KEY or not API_SECRET:
        print("❌ ERROR: Variables de entorno no configuradas")
        print("🐳 En Docker, asegúrate de que el .env esté configurado correctamente")
        print("🐳 Variables requeridas: BINANCE_API_KEY, BINANCE_API_SECRET")
        exit(1)
    
    print(f"🤖 Iniciando bot en modo: {'TESTNET' if USE_TESTNET else 'REAL TRADING'} | versión {BOT_VERSION}")
    print(f"🔔 CARACTERÍSTICAS SWING TRADING v{BOT_VERSION}:")
    print("  • Timeframe 4H para swing trading")
    print("  • Filtro de tendencia con EMA200")
    print("  • Confirmación de señales con EMAs 21/50")
    print("  • Sistema de pullback a EMAs")
    print("  • Trailing stop con breakeven automático")
    print("  • Ratio riesgo/beneficio 1:2")
    print("  • Verificación cada 30 minutos")
    print("🐳 DOCKER: Auto-restart + persistencia garantizada")
    
    if not USE_TESTNET:
        print("⚠️  ADVERTENCIA: Vas a usar DINERO REAL")
        print("🐳 En modo Docker, no se solicita confirmación manual")
        print("🐳 Para cancelar, detén el contenedor: docker-compose down")
    
    try:
        print("🚀 Creando instancia del bot swing...")
        bot = BinanceRSIEMABot(
            api_key=API_KEY,
            api_secret=API_SECRET, 
            testnet=USE_TESTNET
        )
        
        print("✅ Bot swing inicializado correctamente")
        print("🔄 Iniciando loop principal para swing trading...")
        bot.run()
        
    except KeyboardInterrupt:
        print("🛑 Bot detenido por señal de usuario")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        print("🐳 Docker reiniciará automáticamente el contenedor")
        exit(1)
