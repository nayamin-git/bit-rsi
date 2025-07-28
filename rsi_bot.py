import ccxt
import pandas as pd
import numpy as np
import time
import logging
import signal
from datetime import datetime
import json
import csv
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class BinanceRSIEMABot:
    def __init__(self, api_key, api_secret, testnet=True):
        """
        Bot de trading RSI + EMA + Filtro de Tendencia para Binance - v2.0
        
        Args:
            api_key: Tu API key de Binance
            api_secret: Tu API secret de Binance  
            testnet: True para usar testnet, False para trading real
        """
        
        # IMPORTANTE: Configurar logging PRIMERO
        self.setup_logging()
        
        # Configurar variables básicas ANTES de exchange
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
        
        # Estado del bot
        self.position = None
        self.in_position = False
        self.last_signal_time = 0
        
        # NUEVOS ESTADOS PARA ESTRATEGIA EMA
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.swing_wait_count = 0
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
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': testnet,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            }
        })
        
        # Verificar conexión después de configurar todo
        self.verify_connection()
        
        # Inicializar archivos de logs al final
        self.init_log_files()
        
        # Recuperar estado y posiciones al iniciar
        self.recover_bot_state()
        
    def setup_logging(self):
        """Configura sistema de logging (compatible con Docker)"""
        logs_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
            
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        log_file = os.path.join(logs_dir, f'rsi_ema_bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info(f"🐳 RSI+EMA+Trend Bot iniciando - Logs en: {log_file}")
        
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Maneja señales de Docker (SIGTERM, SIGINT)"""
        signal_names = {2: 'SIGINT', 15: 'SIGTERM'}
        signal_name = signal_names.get(signum, f'Signal {signum}')
        
        self.logger.info(f"🐳 Recibida señal {signal_name} - Cerrando bot gracefully...")
        
        if self.in_position:
            self.logger.info("💾 Cerrando posición antes de salir...")
            self.close_position("Señal Docker")
        
        self.save_bot_state()
        self.log_performance_summary()
        
        self.logger.info("🐳 Bot cerrado correctamente")
        exit(0)
        
    def verify_connection(self):
        """Verifica la conexión con Binance"""
        try:
            self.exchange.load_markets()
            
            if self.symbol not in self.exchange.markets:
                available_symbols = [s for s in self.exchange.markets.keys() if 'BTC' in s and 'USDT' in s]
                self.logger.warning(f"Símbolo {self.symbol} no encontrado. Disponibles: {available_symbols[:5]}")
                
            balance = self.exchange.fetch_balance()
            self.logger.info(f"✅ Conexión exitosa con Binance {'Testnet' if self.testnet else 'Mainnet'}")
            
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            self.logger.info(f"💰 Balance USDT disponible: ${usdt_balance:.2f}")
            
        except Exception as e:
            self.logger.error(f"❌ Error de conexión: {e}")
            raise
    
    def calculate_ema(self, prices, period):
        """Calcula EMA (Exponential Moving Average)"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            return prices.ewm(span=period, adjust=False).mean().iloc[-1]
            
        except Exception as e:
            self.logger.error(f"Error calculando EMA: {e}")
            return 0
    
    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            delta = prices.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
        except Exception as e:
            self.logger.error(f"Error calculando RSI: {e}")
            return 50
    
    def get_market_data(self):
        """Obtiene datos del mercado para calcular RSI y EMAs"""
        try:
            # Obtener más datos para EMAs
            limit = max(self.ema_trend_period + 50, 100)
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol, 
                self.timeframe, 
                limit=limit
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Calcular indicadores
            current_price = float(df['close'].iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            current_rsi = self.calculate_rsi(df['close'])
            
            # Calcular EMAs
            ema_fast = self.calculate_ema(df['close'], self.ema_fast_period)
            ema_slow = self.calculate_ema(df['close'], self.ema_slow_period)
            ema_trend = self.calculate_ema(df['close'], self.ema_trend_period)
            
            # Determinar dirección de tendencia
            trend_direction = self.determine_trend_direction(current_price, ema_fast, ema_slow, ema_trend)
            
            # Log datos de mercado
            self.log_market_data(current_price, current_rsi, current_volume, ema_fast, ema_slow, ema_trend, trend_direction)
            
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
            if fast_slow_sep >= self.ema_separation_min:
                return 'bullish'
        
        # Bearish: EMA21 < EMA50 < EMA200 AND price < EMA200
        elif ema_fast < ema_slow and ema_slow < ema_trend and price < ema_trend:
            slow_fast_sep = ((ema_slow - ema_fast) / ema_fast) * 100
            if slow_fast_sep >= self.ema_separation_min:
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
    
    def detect_swing_signal(self, price, rsi, ema_fast, ema_slow, ema_trend, trend_direction):
        """OPTIMIZED: More flexible signal detection"""
        
        if self.pending_long_signal or self.pending_short_signal:
            return False
        
        # LONG Signal - More flexible conditions
        if (rsi < self.rsi_oversold and 
            trend_direction in ['bullish', 'weak_bullish', 'neutral'] and  # Added flexibility
            not self.in_position):
            
            # More flexible pullback check
            is_pullback, pullback_type = self.is_pullback_to_ema(price, ema_fast, ema_slow)
            
            # Accept signal even without perfect pullback if RSI is very low
            if is_pullback or not self.pullback_ema_touch or rsi < 25:
                self.pending_long_signal = True
                self.signal_trigger_price = price
                self.signal_trigger_time = datetime.now()
                self.swing_wait_count = 0
                
                self.performance_metrics['signals_detected'] += 1
                self.logger.info(f"🟡 FLEXIBLE LONG detected - RSI: {rsi:.2f} | Trend: {trend_direction}")
                return True
        
        # SHORT Signal - More flexible conditions
        elif (rsi > self.rsi_overbought and 
              trend_direction in ['bearish', 'weak_bearish', 'neutral'] and  # Added flexibility
              not self.in_position):
            
            is_pullback, pullback_type = self.is_pullback_to_ema(price, ema_fast, ema_slow)
            
            # Accept signal even without perfect pullback if RSI is very high
            if is_pullback or not self.pullback_ema_touch or rsi > 85:
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
            rsi_improved = current_rsi > self.rsi_neutral_low or current_rsi > (self.last_rsi + 5)
            price_moved_up = price_change_pct >= self.swing_confirmation_threshold
            trend_not_bearish = trend_direction != 'bearish'  # Just avoid bearish
            
            if price_moved_up and rsi_improved and trend_not_bearish:
                self.logger.info(f"✅ FLEXIBLE LONG CONFIRMED! Price: +{price_change_pct:.2f}% | RSI: {current_rsi:.2f}")
                self.reset_signal_state()
                return True, 'long'
            
            # Extended wait time
            elif self.swing_wait_count >= self.max_swing_wait:
                self.logger.warning(f"⏰ LONG signal expired after {self.max_swing_wait} periods")
                self.reset_signal_state()
                return False, None
        
        # SHORT Confirmation - More flexible
        elif self.pending_short_signal:
            price_change_pct = ((self.signal_trigger_price - current_price) / self.signal_trigger_price) * 100
            
            rsi_improved = current_rsi < self.rsi_neutral_high or current_rsi < (self.last_rsi - 5)
            price_moved_down = price_change_pct >= self.swing_confirmation_threshold
            trend_not_bullish = trend_direction != 'bullish'
            
            if price_moved_down and rsi_improved and trend_not_bullish:
                self.logger.info(f"✅ FLEXIBLE SHORT CONFIRMED! Price: -{price_change_pct:.2f}% | RSI: {current_rsi:.2f}")
                self.reset_signal_state()
                return True, 'short'
            
            elif self.swing_wait_count >= self.max_swing_wait:
                self.logger.warning(f"⏰ SHORT signal expired after {self.max_swing_wait} periods")
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
    
    def log_market_data(self, price, rsi, volume, ema_fast, ema_slow, ema_trend, trend_direction, signal=None):
        """Registra datos de mercado con EMAs"""
        timestamp = datetime.now()
        
        # Calcular PnL no realizado si estamos en posición
        unrealized_pnl = 0
        if self.in_position and self.position:
            if self.position['side'] == 'long':
                unrealized_pnl = ((price - self.position['entry_price']) / self.position['entry_price']) * 100 * self.leverage
            else:
                unrealized_pnl = ((self.position['entry_price'] - price) / self.position['entry_price']) * 100 * self.leverage
        
        # Estado de señal pendiente
        pending_signal = ""
        if self.pending_long_signal:
            pending_signal = f"LONG_WAIT_{self.swing_wait_count}/{self.max_swing_wait}"
        elif self.pending_short_signal:
            pending_signal = f"SHORT_WAIT_{self.swing_wait_count}/{self.max_swing_wait}"
        
        # Actualizar variables de estado
        self.last_rsi = rsi
        self.last_price = price
        self.last_ema_fast = ema_fast
        self.last_ema_slow = ema_slow
        self.last_ema_trend = ema_trend
        self.trend_direction = trend_direction
        
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
                'in_position': self.in_position,
                'position': serialize_datetime(self.position) if self.position else None,
                'last_signal_time': self.last_signal_time,
                'pending_long_signal': self.pending_long_signal,
                'pending_short_signal': self.pending_short_signal,
                'signal_trigger_price': self.signal_trigger_price,
                'signal_trigger_time': self.signal_trigger_time.isoformat() if self.signal_trigger_time else None,
                'swing_wait_count': self.swing_wait_count,
                'performance_metrics': self.performance_metrics,
                'last_rsi': self.last_rsi,
                'last_price': self.last_price,
                'last_ema_fast': self.last_ema_fast,
                'last_ema_slow': self.last_ema_slow,
                'last_ema_trend': self.last_ema_trend,
                'trend_direction': self.trend_direction
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Error guardando estado del bot: {e}")
    
    def load_bot_state(self):
        """Carga el estado previo del bot desde archivo JSON"""
        try:
            if not os.path.exists(self.state_file):
                self.logger.info("📄 No hay archivo de estado previo")
                return False
                
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            
            # Verificar que el estado no sea muy antiguo (máximo 48 horas para swing trading)
            state_time = datetime.fromisoformat(state_data['timestamp'])
            time_diff = datetime.now() - state_time
            
            if time_diff.total_seconds() > 172800:  # 48 horas
                self.logger.warning(f"⏰ Estado muy antiguo ({time_diff}), no se cargará")
                return False
            
            # Restaurar estado
            self.in_position = state_data.get('in_position', False)
            self.last_signal_time = state_data.get('last_signal_time', 0)
            self.pending_long_signal = state_data.get('pending_long_signal', False)
            self.pending_short_signal = state_data.get('pending_short_signal', False)
            self.signal_trigger_price = state_data.get('signal_trigger_price')
            self.swing_wait_count = state_data.get('swing_wait_count', 0)
            self.last_rsi = state_data.get('last_rsi', 50)
            self.last_price = state_data.get('last_price', 0)
            self.last_ema_fast = state_data.get('last_ema_fast', 0)
            self.last_ema_slow = state_data.get('last_ema_slow', 0)
            self.last_ema_trend = state_data.get('last_ema_trend', 0)
            self.trend_direction = state_data.get('trend_direction', 'neutral')
            
            # Restaurar signal_trigger_time
            if state_data.get('signal_trigger_time'):
                self.signal_trigger_time = datetime.fromisoformat(state_data['signal_trigger_time'])
            
            # Restaurar posición si existe
            if state_data.get('position'):
                self.position = state_data['position'].copy()
                if 'entry_time' in self.position:
                    self.position['entry_time'] = datetime.fromisoformat(self.position['entry_time'])
            
            # Restaurar métricas
            if state_data.get('performance_metrics'):
                self.performance_metrics.update(state_data['performance_metrics'])
            
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
        if state_loaded and self.in_position and exchange_position:
            self.logger.info("✅ Estado y posición recuperados correctamente")
            
        elif not state_loaded and exchange_position:
            self.logger.warning("⚠️ Posición encontrada sin estado guardado - Recuperando...")
            self.recover_position_from_exchange(exchange_position)
            
        elif state_loaded and self.in_position and not exchange_position:
            self.logger.error("❌ Estado dice posición abierta pero no existe en exchange")
            self.logger.error("🔧 Limpiando estado inconsistente...")
            self.position = None
            self.in_position = False
            
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
                if not self.testnet and self.leverage > 1:
                    self.exchange.set_sandbox_mode(False)
                    positions = self.exchange.fetch_positions([self.symbol])
                    
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
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
                
                self.logger.warning(f"🔍 Balance BTC detectado: {btc_balance:.6f} BTC (≈${btc_balance * current_price:.2f})")
                
                return {
                    'side': 'long',
                    'size': btc_balance,
                    'entryPrice': current_price,
                    'symbol': self.symbol
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
                stop_price = current_price * (1 - self.stop_loss_pct / 100)
                take_profit_price = current_price * (1 + self.take_profit_pct / 100)
            else:
                stop_price = current_price * (1 + self.stop_loss_pct / 100)
                take_profit_price = current_price * (1 - self.take_profit_pct / 100)
            
            # Crear posición para monitoreo
            self.position = {
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
            
            self.in_position = True
            
            # Log de recuperación
            with open(self.recovery_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Posición recuperada: {side} {quantity} @ ${current_price:.2f}\n")
            
            self.logger.warning(f"🔄 POSICIÓN RECUPERADA: {side.upper()} {quantity:.6f} BTC @ ${current_price:.2f}")
            self.logger.warning(f"📊 Nuevos niveles - SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")
            
            self.performance_metrics['recoveries_performed'] += 1
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error recuperando posición: {e}")
            return False
    
    def init_log_files(self):
        """Inicializa archivos CSV para análisis"""
        self.trades_csv = os.path.join(self.logs_dir, f'swing_trades_{datetime.now().strftime("%Y%m%d")}.csv')
        self.market_csv = os.path.join(self.logs_dir, f'swing_market_data_{datetime.now().strftime("%Y%m%d")}.csv')
        
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
        
        if balance < self.min_balance_usdt:
            self.logger.warning(f"Balance insuficiente: ${balance:.2f} < ${self.min_balance_usdt}")
            return 0, 0
        
        # Calcular valor de la posición (más conservador para swing)
        position_value = balance * (self.position_size_pct / 100)
        effective_position = position_value * self.leverage
        
        # Verificar mínimo notional
        if effective_position < self.min_notional_usdt:
            self.logger.warning(f"Posición muy pequeña: ${effective_position:.2f} < ${self.min_notional_usdt}")
            effective_position = self.min_notional_usdt
        
        quantity = round(effective_position / price, 6)
        final_notional = quantity * price
        
        if final_notional < self.min_notional_usdt:
            self.logger.warning(f"Notional final insuficiente: ${final_notional:.2f}")
            return 0, 0
        
        return quantity, position_value
    
    def create_test_order(self, side, quantity, price):
        """Simula una orden para testnet"""
        order_id = f"swing_test_{int(time.time())}"
        
        fake_order = {
            'id': order_id,
            'symbol': self.symbol,
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
            stop_price = price * (1 - self.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.take_profit_pct / 100)
            
            # Intentar crear orden real
            try:
                if self.testnet:
                    order = self.exchange.create_market_order(self.symbol, 'buy', quantity)
                else:
                    order = self.exchange.create_market_order(self.symbol, 'buy', quantity)
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
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Ratio: 1:{self.take_profit_pct/self.stop_loss_pct:.1f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.2f} | EMA21: ${ema_fast:.2f}")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'long', price, quantity, rsi, ema_fast, ema_slow, ema_trend, 
                          trend_direction, 'Swing Long + EMA Filter', confirmation_time=confirmation_time)
            
            self.save_bot_state()
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
            
            stop_price = price * (1 + self.stop_loss_pct / 100)
            take_profit_price = price * (1 - self.take_profit_pct / 100)
            
            try:
                if self.testnet:
                    order = self.exchange.create_market_order(self.symbol, 'sell', quantity)
                else:
                    order = self.exchange.create_market_order(self.symbol, 'sell', quantity)
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
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Ratio: 1:{self.take_profit_pct/self.stop_loss_pct:.1f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.2f} | EMA21: ${ema_fast:.2f}")
            
            self.log_trade('OPEN', 'short', price, quantity, rsi, ema_fast, ema_slow, ema_trend,
                          trend_direction, 'Swing Short + EMA Filter', confirmation_time=confirmation_time)
            
            self.save_bot_state()
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
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
            
            # Intentar crear orden de cierre
            try:
                order = self.exchange.create_market_order(self.symbol, side, self.position['quantity'])
            except Exception as order_error:
                self.logger.warning(f"Error creando orden de cierre: {order_error}")
                order = self.create_test_order(side, self.position['quantity'], current_price)
            
            # Calcular P&L
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
            
            pnl_pct *= self.leverage
            
            # Calcular duración del swing
            duration_hours = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
            
            self.logger.info(f"⭕ Posición SWING cerrada - {reason}")
            self.logger.info(f"💰 P&L: {pnl_pct:.2f}% | Duración: {duration_hours:.1f}h")
            
            # Log detallado del cierre
            ema_data = market_data if market_data else {}
            self.log_trade('CLOSE', self.position['side'], current_price, 
                          self.position['quantity'], current_rsi, 
                          ema_data.get('ema_fast', 0), ema_data.get('ema_slow', 0), 
                          ema_data.get('ema_trend', 0), ema_data.get('trend_direction', 'unknown'),
                          reason, pnl_pct, duration_hours)
            
            self.position = None
            self.in_position = False
            
            self.save_bot_state()
            return True
            
        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
            return False
    
    def update_trailing_stop_swing(self, current_price, market_data):
        """Actualiza trailing stop para swing trading"""
        if not self.in_position or not self.position:
            return
        
        if self.position['side'] == 'long':
            # Actualizar precio máximo
            if current_price > self.position['highest_price']:
                self.position['highest_price'] = current_price
                
                # Mover stop loss a breakeven cuando ganemos el threshold
                if not self.position['breakeven_moved']:
                    gain_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                    if gain_pct >= self.breakeven_threshold:
                        self.position['trailing_stop'] = self.position['entry_price'] * 1.001  # Breakeven + 0.1%
                        self.position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${self.position['trailing_stop']:.2f}")
                        return
                
                # Trailing stop normal
                if self.position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 - self.trailing_stop_distance / 100)
                    if new_trailing_stop > self.position['trailing_stop']:
                        old_stop = self.position['trailing_stop']
                        self.position['trailing_stop'] = new_trailing_stop
                        self.logger.info(f"📈 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f}")
                        
        else:  # SHORT
            if current_price < self.position['lowest_price']:
                self.position['lowest_price'] = current_price
                
                if not self.position['breakeven_moved']:
                    gain_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                    if gain_pct >= self.breakeven_threshold:
                        self.position['trailing_stop'] = self.position['entry_price'] * 0.999  # Breakeven - 0.1%
                        self.position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${self.position['trailing_stop']:.2f}")
                        return
                
                if self.position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 + self.trailing_stop_distance / 100)
                    if new_trailing_stop < self.position['trailing_stop']:
                        old_stop = self.position['trailing_stop']
                        self.position['trailing_stop'] = new_trailing_stop
                        self.logger.info(f"📉 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f}")
    
    def check_exit_conditions_swing(self, current_price, current_rsi, market_data):
        """Verifica condiciones de salida para swing trading"""
        if not self.in_position or not self.position:
            return
        
        # Actualizar trailing stop
        self.update_trailing_stop_swing(current_price, market_data)
        
        trend_direction = market_data.get('trend_direction', 'neutral')
        ema_fast = market_data.get('ema_fast', 0)
        ema_slow = market_data.get('ema_slow', 0)
        
        if self.position['side'] == 'long':
            # 1. Stop Loss de emergencia
            if current_price <= self.position['stop_loss']:
                self.close_position("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return
            
            # 2. Take Profit objetivo
            elif current_price >= self.position['take_profit']:
                self.close_position("Take Profit Objetivo", current_rsi, current_price, market_data)
                return
            
            # 3. Trailing stop dinámico
            elif current_price <= self.position['trailing_stop']:
                price_from_max = ((self.position['highest_price'] - current_price) / self.position['highest_price']) * 100
                self.close_position(f"Trailing Stop (-{price_from_max:.1f}%)", current_rsi, current_price, market_data)
                return
            
            # 4. Cambio de tendencia a bajista
            elif trend_direction == 'bearish':
                self.logger.warning("⚠️ Tendencia cambió a bajista - Evaluando salida...")
                # Solo salir si también hay señales técnicas adversas
                if current_rsi > 70 or current_price < ema_fast:
                    self.close_position("Cambio Tendencia Bajista", current_rsi, current_price, market_data)
                    return
            
            # 5. RSI muy overbought + precio bajo EMA21
            elif current_rsi > 80 and current_price < ema_fast:
                self.close_position("RSI Overbought + Bajo EMA21", current_rsi, current_price, market_data)
                return
                
        else:  # SHORT
            # 1. Stop Loss de emergencia
            if current_price >= self.position['stop_loss']:
                self.close_position("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return
            
            # 2. Take Profit objetivo
            elif current_price <= self.position['take_profit']:
                self.close_position("Take Profit Objetivo", current_rsi, current_price, market_data)
                return
            
            # 3. Trailing stop dinámico
            elif current_price >= self.position['trailing_stop']:
                price_from_min = ((current_price - self.position['lowest_price']) / self.position['lowest_price']) * 100
                self.close_position(f"Trailing Stop (+{price_from_min:.1f}%)", current_rsi, current_price, market_data)
                return
            
            # 4. Cambio de tendencia a alcista
            elif trend_direction == 'bullish':
                self.logger.warning("⚠️ Tendencia cambió a alcista - Evaluando salida...")
                if current_rsi < 30 or current_price > ema_fast:
                    self.close_position("Cambio Tendencia Alcista", current_rsi, current_price, market_data)
                    return
            
            # 5. RSI muy oversold + precio sobre EMA21
            elif current_rsi < 20 and current_price > ema_fast:
                self.close_position("RSI Oversold + Sobre EMA21", current_rsi, current_price, market_data)
                return
    
    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None, 
                  ema_fast=None, ema_slow=None, ema_trend=None, trend_direction=None,
                  reason=None, pnl_pct=None, duration_hours=None, confirmation_time=None):
        """Registra trades con datos de EMAs"""
        timestamp = datetime.now()
        balance = self.get_account_balance()
        
        try:
            with open(self.trades_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                
                if action == 'OPEN':
                    pullback_type = "Unknown"
                    if self.position and hasattr(self, '_last_pullback_type'):
                        pullback_type = self._last_pullback_type
                    
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        ema_fast or 0, ema_slow or 0, ema_trend or 0, trend_direction or '',
                        self.position['stop_loss'] if self.position else '',
                        self.position['take_profit'] if self.position else '',
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
    
    def analyze_and_trade(self):
        """Análisis principal y ejecución de trades para swing"""
        # Obtener datos del mercado
        market_data = self.get_market_data()
        if not market_data:
            return
            
        current_rsi = market_data['rsi']
        current_price = market_data['price']
        ema_fast = market_data['ema_fast']
        ema_slow = market_data['ema_slow']
        ema_trend = market_data['ema_trend']
        trend_direction = market_data['trend_direction']
        
        # Log información del mercado
        if self.in_position and self.position:
            pnl_pct = 0
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                max_price = self.position.get('highest_price', current_price)
                trailing_stop = self.position.get('trailing_stop', 0)
                
                self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Max: ${max_price:.2f} | TS: ${trailing_stop:.2f}")
                self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f}")
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                min_price = self.position.get('lowest_price', current_price)
                trailing_stop = self.position.get('trailing_stop', 0)
                
                self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Min: ${min_price:.2f} | TS: ${trailing_stop:.2f}")
                self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f}")
        else:
            ema_order = "📈" if ema_fast > ema_slow > ema_trend else "📉" if ema_fast < ema_slow < ema_trend else "🔄"
            self.logger.info(f"{ema_order} BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | Tendencia: {trend_direction}")
            self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f}")
        
        # Verificar condiciones de salida si estamos en posición
        self.check_exit_conditions_swing(current_price, current_rsi, market_data)
        
        # Si estamos en posición, no buscar nuevas señales
        if self.in_position:
            return
        
        # Verificar confirmación de señales pendientes
        confirmed, signal_type = self.check_swing_confirmation(current_price, current_rsi, trend_direction)
        
        if confirmed:
            current_time = time.time()
            
            # Calcular tiempo de confirmación
            confirmation_time_hours = 0
            if self.signal_trigger_time:
                confirmation_time_hours = (datetime.now() - self.signal_trigger_time).total_seconds() / 3600
            
            if signal_type == 'long':
                if self.open_long_position(current_price, current_rsi, ema_fast, ema_slow, 
                                         ema_trend, trend_direction, confirmation_time_hours):
                    self.last_signal_time = current_time
            elif signal_type == 'short':
                if self.open_short_position(current_price, current_rsi, ema_fast, ema_slow,
                                          ema_trend, trend_direction, confirmation_time_hours):
                    self.last_signal_time = current_time
        
        # Solo buscar nuevas señales si no hay señales pendientes y ha pasado tiempo suficiente
        elif not (self.pending_long_signal or self.pending_short_signal):
            current_time = time.time()
            if current_time - self.last_signal_time >= self.min_time_between_signals:
                self.detect_swing_signal(current_price, current_rsi, ema_fast, ema_slow, 
                                       ema_trend, trend_direction)
    
    def run(self):
        """Ejecuta el bot en un loop continuo optimizado para swing trading"""
        self.logger.info("🤖 RSI + EMA + Trend Filter Swing Bot v2.0 iniciado")
        self.logger.info(f"📊 Timeframe: {self.timeframe} | RSI({self.rsi_period}) | OS: {self.rsi_oversold} | OB: {self.rsi_overbought}")
        self.logger.info(f"📈 EMAs: Fast({self.ema_fast_period}) | Slow({self.ema_slow_period}) | Trend({self.ema_trend_period})")
        self.logger.info(f"⚡ Leverage: {self.leverage}x | Risk: {self.position_size_pct}% | SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        self.logger.info(f"🎯 Swing Confirmación: {self.swing_confirmation_threshold}% | Max espera: {self.max_swing_wait} períodos")
        self.logger.info(f"🛡️ Trailing Stop: {self.trailing_stop_distance}% | Breakeven: {self.breakeven_threshold}%")
        self.logger.info(f"💾 Estado guardado en: {self.state_file}")
        self.logger.info(f"🐳 Ejecutándose en Docker - PID: {os.getpid()}")
        
        # Para swing trading, verificar cada 30 minutos (timeframe 4h)
        check_interval = 1800  # 30 minutos en segundos
        iteration = 0
        
        try:
            while True:
                self.analyze_and_trade()
                
                # Mostrar resumen cada 4 horas (8 iteraciones de 30 min)
                iteration += 1
                if iteration % 8 == 0:
                    self.log_performance_summary()
                
                # Guardar estado cada hora (2 iteraciones)
                if iteration % 2 == 0:
                    self.save_bot_state()
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Bot detenido por el usuario (KeyboardInterrupt)")
            if self.in_position:
                self.close_position("Bot detenido")
            self.save_bot_state()
            self.log_performance_summary()
                
        except Exception as e:
            self.logger.error(f"❌ Error en el bot: {e}")
            if self.in_position:
                self.close_position("Error del bot")
            self.save_bot_state()
            raise
    
    def log_performance_summary(self):
        """Muestra resumen de performance para swing trading"""
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
            if metrics['winning_trades'] > 0 and metrics['losing_trades'] > 0:
                avg_win = sum([t.get('pnl_pct', 0) for t in self.trades_log if t.get('pnl_pct', 0) > 0]) / metrics['winning_trades']
                avg_loss = sum([t.get('pnl_pct', 0) for t in self.trades_log if t.get('pnl_pct', 0) < 0]) / metrics['losing_trades']
                profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                
                self.logger.info(f"📈 Ganancia promedio: {avg_win:.2f}%")
                self.logger.info(f"📉 Pérdida promedio: {avg_loss:.2f}%")
                self.logger.info(f"⚖️ Factor de Ganancia: {profit_factor:.2f}")
        
        self.logger.info(f"💵 Balance Actual: ${self.get_account_balance():.2f}")
        
        # Estado actual con información de EMAs
        if self.in_position:
            pos_type = "RECUPERADA" if self.position.get('recovered') else "ACTIVA"
            duration = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
            self.logger.info(f"📍 Posición {pos_type}: {self.position['side'].upper()} ({duration:.1f}h)")
            self.logger.info(f"🎯 Breakeven movido: {'SÍ' if self.position.get('breakeven_moved') else 'NO'}")
        elif self.pending_long_signal:
            self.logger.info(f"⏳ Esperando confirmación SWING LONG ({self.swing_wait_count}/{self.max_swing_wait})")
        elif self.pending_short_signal:
            self.logger.info(f"⏳ Esperando confirmación SWING SHORT ({self.swing_wait_count}/{self.max_swing_wait})")
        else:
            self.logger.info(f"🔍 Buscando oportunidades swing... | Tendencia actual: {self.trend_direction}")
        
        # Información de EMAs actuales
        if hasattr(self, 'last_ema_fast') and self.last_ema_fast > 0:
            ema_alignment = "ALCISTA" if self.last_ema_fast > self.last_ema_slow > self.last_ema_trend else \
                           "BAJISTA" if self.last_ema_fast < self.last_ema_slow < self.last_ema_trend else "NEUTRAL"
            
            self.logger.info(f"📊 Alineación EMAs: {ema_alignment}")
            self.logger.info(f"📈 EMA21: ${self.last_ema_fast:.2f} | EMA50: ${self.last_ema_slow:.2f} | EMA200: ${self.last_ema_trend:.2f}")
            
            # Separación entre EMAs
            if self.last_ema_slow > 0:
                fast_slow_sep = abs((self.last_ema_fast - self.last_ema_slow) / self.last_ema_slow) * 100
                self.logger.info(f"📏 Separación EMA21-EMA50: {fast_slow_sep:.2f}%")
        
        self.logger.info("="*70)


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
    
    print(f"🤖 Iniciando bot en modo: {'TESTNET' if USE_TESTNET else 'REAL TRADING'}")
    print("🔔 CARACTERÍSTICAS SWING TRADING v2.0:")
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
