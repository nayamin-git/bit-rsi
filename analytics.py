import csv
import os
from datetime import datetime


class Analytics:
    """
    Gestor de logging y análisis de rendimiento
    """

    def __init__(self, config, logger, position_manager, signal_detector, get_balance_callback):
        """
        Args:
            config: Configuración del bot
            logger: Logger para registrar información
            position_manager: Instancia de PositionManager
            signal_detector: Instancia de SignalDetector
            get_balance_callback: Función callback para obtener balance
        """
        self.config = config
        self.logger = logger
        self.position_manager = position_manager
        self.signal_detector = signal_detector
        self.get_balance_callback = get_balance_callback

        # Archivos CSV
        self.trades_csv = None
        self.market_csv = None

        # Referencias a variables de estado (se establecerán desde el bot)
        self.market_state = {
            'last_ema_fast': 0,
            'last_ema_slow': 0,
            'last_ema_trend': 0,
            'trend_direction': 'neutral'
        }

        # Referencias a métricas
        self.performance_metrics = None
        self.trades_log = []

    def set_performance_metrics(self, performance_metrics):
        """Establece referencia a las métricas de rendimiento"""
        self.performance_metrics = performance_metrics

    def set_market_state(self, last_ema_fast, last_ema_slow, last_ema_trend, trend_direction):
        """Actualiza referencias a las variables de estado de mercado"""
        self.market_state = {
            'last_ema_fast': last_ema_fast,
            'last_ema_slow': last_ema_slow,
            'last_ema_trend': last_ema_trend,
            'trend_direction': trend_direction
        }

    def init_log_files(self):
        """Inicializa archivos CSV para análisis"""
        self.trades_csv = os.path.join(self.config.logs_dir, f'swing_trades_{datetime.now().strftime("%Y%m%d")}.csv')
        self.market_csv = os.path.join(self.config.logs_dir, f'swing_market_data_{datetime.now().strftime("%Y%m%d")}.csv')

        # Headers para trades
        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'action', 'side', 'price', 'quantity', 'rsi',
                    'ema_fast', 'ema_slow', 'ema_trend', 'trend_direction',
                    'stop_loss', 'take_profit', 'reason', 'pnl_pct', 'pnl_usdt',
                    'balance_before', 'balance_after', 'trade_duration_hours',
                    'signal_confirmed', 'confirmation_time_hours', 'pullback_type'
                ])

        # Headers para datos de mercado
        if not os.path.exists(self.market_csv):
            with open(self.market_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'price', 'rsi', 'volume', 'ema_fast', 'ema_slow',
                    'ema_trend', 'trend_direction', 'signal', 'in_position',
                    'position_side', 'unrealized_pnl_pct', 'pending_signal'
                ])

    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None,
                  ema_fast=None, ema_slow=None, ema_trend=None, trend_direction=None,
                  reason=None, pnl_pct=None, duration_hours=None, confirmation_time=None):
        """Registra trades con datos de EMAs"""
        timestamp = datetime.now()
        balance = self.get_balance_callback()

        try:
            with open(self.trades_csv, 'a', newline='') as f:
                writer = csv.writer(f)

                if action == 'OPEN':
                    pullback_type = "Unknown"
                    # Note: _last_pullback_type would need to be tracked if needed
                    position = self.position_manager.position

                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        ema_fast or 0, ema_slow or 0, ema_trend or 0, trend_direction or '',
                        position['stop_loss'] if position else '',
                        position['take_profit'] if position else '',
                        reason or '', '', '', balance, '', '',
                        "YES" if confirmation_time else "NO",
                        confirmation_time or 0, pullback_type
                    ])
                else:  # CLOSE
                    pnl_usdt = (pnl_pct / 100) * balance if pnl_pct else 0
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        ema_fast or 0, ema_slow or 0, ema_trend or 0, trend_direction or '',
                        '', '', reason or '', pnl_pct or 0, pnl_usdt,
                        '', balance, duration_hours or 0, '', '', ''
                    ])
        except Exception as e:
            self.logger.error(f"Error guardando trade: {e}")

        # Actualizar métricas
        if action == 'CLOSE' and pnl_pct is not None:
            self.update_performance_metrics(pnl_pct)

    def update_performance_metrics(self, pnl_pct):
        """Actualiza métricas de rendimiento"""
        if not self.performance_metrics:
            return

        self.performance_metrics['total_trades'] += 1
        self.performance_metrics['total_pnl'] += pnl_pct

        if pnl_pct > 0:
            self.performance_metrics['winning_trades'] += 1
            self.performance_metrics['consecutive_losses'] = 0
        else:
            self.performance_metrics['losing_trades'] += 1
            self.performance_metrics['consecutive_losses'] += 1

        if self.performance_metrics['consecutive_losses'] > self.performance_metrics['max_consecutive_losses']:
            self.performance_metrics['max_consecutive_losses'] = self.performance_metrics['consecutive_losses']

    def log_performance_summary(self):
        """Muestra resumen de performance para swing trading"""
        if not self.performance_metrics:
            return

        metrics = self.performance_metrics

        self.logger.info("="*70)
        self.logger.info("📊 RESUMEN DE PERFORMANCE SWING TRADING")
        self.logger.info("="*70)

        # Estadísticas de señales y filtros
        signal_confirmation_rate = 0
        if metrics['signals_detected'] > 0:
            signal_confirmation_rate = (metrics['signals_confirmed'] / metrics['signals_detected']) * 100

        self.logger.info(f"🔔 Señales detectadas: {metrics['signals_detected']}")
        self.logger.info(f"✅ Señales confirmadas: {metrics['signals_confirmed']}")
        self.logger.info(f"⏰ Señales expiradas: {metrics['signals_expired']}")
        self.logger.info(f"📈 Tasa de confirmación: {signal_confirmation_rate:.1f}%")
        self.logger.info(f"🎯 Filtros de tendencia aplicados: {metrics['trend_filters_applied']}")
        self.logger.info(f"📊 Confirmaciones EMA: {metrics['ema_confirmations']}")
        self.logger.info(f"🔄 Entradas por pullback: {metrics['pullback_entries']}")
        self.logger.info(f"🔧 Recuperaciones realizadas: {metrics['recoveries_performed']}")
        self.logger.info("-" * 50)

        # Estadísticas de trading
        if metrics['total_trades'] == 0:
            self.logger.info("📊 Sin trades completados aún")
        else:
            win_rate = (metrics['winning_trades'] / metrics['total_trades']) * 100
            avg_pnl = metrics['total_pnl'] / metrics['total_trades']

            self.logger.info(f"🔢 Total Swings: {metrics['total_trades']}")
            self.logger.info(f"🎯 Win Rate: {win_rate:.1f}%")
            self.logger.info(f"💰 PnL Promedio: {avg_pnl:.2f}%")
            self.logger.info(f"💰 PnL Total: {metrics['total_pnl']:.2f}%")
            self.logger.info(f"✅ Ganadores: {metrics['winning_trades']}")
            self.logger.info(f"❌ Perdedores: {metrics['losing_trades']}")
            self.logger.info(f"📉 Max Pérdidas Consecutivas: {metrics['max_consecutive_losses']}")

            # Calcular métricas adicionales para swing
            if metrics['winning_trades'] > 0 and metrics['losing_trades'] > 0 and len(self.trades_log) > 0:
                avg_win = sum([t.get('pnl_pct', 0) for t in self.trades_log if t.get('pnl_pct', 0) > 0]) / metrics['winning_trades']
                avg_loss = sum([t.get('pnl_pct', 0) for t in self.trades_log if t.get('pnl_pct', 0) < 0]) / metrics['losing_trades']
                profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

                self.logger.info(f"📈 Ganancia promedio: {avg_win:.2f}%")
                self.logger.info(f"📉 Pérdida promedio: {avg_loss:.2f}%")
                self.logger.info(f"⚖️ Factor de Ganancia: {profit_factor:.2f}")

        self.logger.info(f"💵 Balance Actual: ${self.get_balance_callback():.2f}")

        # Estado actual con información de EMAs
        if self.position_manager.in_position:
            position = self.position_manager.position
            pos_type = "RECUPERADA" if position.get('recovered') else "ACTIVA"
            duration = (datetime.now() - position['entry_time']).total_seconds() / 3600
            self.logger.info(f"📍 Posición {pos_type}: {position['side'].upper()} ({duration:.1f}h)")
            self.logger.info(f"🎯 Breakeven movido: {'SÍ' if position.get('breakeven_moved') else 'NO'}")
        elif self.signal_detector.pending_long_signal:
            self.logger.info(f"⏳ Esperando confirmación SWING LONG ({self.signal_detector.swing_wait_count}/{self.config.max_swing_wait})")
        elif self.signal_detector.pending_short_signal:
            self.logger.info(f"⏳ Esperando confirmación SWING SHORT ({self.signal_detector.swing_wait_count}/{self.config.max_swing_wait})")
        else:
            self.logger.info(f"🔍 Buscando oportunidades swing... | Tendencia actual: {self.market_state['trend_direction']}")

        # Información de EMAs actuales
        if self.market_state['last_ema_fast'] > 0:
            ema_alignment = "ALCISTA" if self.market_state['last_ema_fast'] > self.market_state['last_ema_slow'] > self.market_state['last_ema_trend'] else \
                           "BAJISTA" if self.market_state['last_ema_fast'] < self.market_state['last_ema_slow'] < self.market_state['last_ema_trend'] else "NEUTRAL"

            self.logger.info(f"📊 Alineación EMAs: {ema_alignment}")
            self.logger.info(f"📈 EMA21: ${self.market_state['last_ema_fast']:.2f} | EMA50: ${self.market_state['last_ema_slow']:.2f} | EMA200: ${self.market_state['last_ema_trend']:.2f}")

            # Separación entre EMAs
            if self.market_state['last_ema_slow'] > 0:
                fast_slow_sep = abs((self.market_state['last_ema_fast'] - self.market_state['last_ema_slow']) / self.market_state['last_ema_slow']) * 100
                self.logger.info(f"📏 Separación EMA21-EMA50: {fast_slow_sep:.2f}%")

        self.logger.info("="*70)
