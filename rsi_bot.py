import ccxt
import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import json
import csv
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class BinanceRSIBot:
    def __init__(self, api_key, api_secret, testnet=True):
        """
        Bot de trading RSI para Binance - Versión con Recuperación de Posiciones
        
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
        self.timeframe = '5m'
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        # Gestión de riesgo mejorada
        self.leverage = 1 if testnet else 5  # Sin leverage en testnet para simplicidad
        self.position_size_pct = 2  # 2% del capital por trade
        self.stop_loss_pct = 2  # Stop loss al 2%
        self.take_profit_pct = 4  # Take profit al 4%
        self.min_balance_usdt = 10  # Balance mínimo para operar
        
        # NUEVAS VARIABLES PARA CONFIRMACIÓN DE MOVIMIENTO
        self.confirmation_threshold = 0.1  # % de movimiento mínimo para confirmar
        self.max_confirmation_wait = 10  # Máximo 10 períodos esperando confirmación
        
        # ARCHIVOS DE PERSISTENCIA
        self.state_file = f'logs/bot_state_{datetime.now().strftime("%Y%m%d")}.json'
        self.recovery_file = f'logs/recovery_log_{datetime.now().strftime("%Y%m%d")}.txt'
        
        # Estado del bot
        self.position = None
        self.in_position = False
        self.last_signal_time = 0
        
        # NUEVOS ESTADOS PARA CONFIRMACIÓN
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.confirmation_wait_count = 0
        self.last_rsi = 50
        self.last_price = 0
        
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
            'start_balance': 0,
            'peak_balance': 0,
            'signals_detected': 0,
            'signals_confirmed': 0,
            'signals_expired': 0,
            'recoveries_performed': 0
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
        
        # 🔥 RECUPERAR ESTADO Y POSICIONES AL INICIAR
        self.recover_bot_state()
        
    def verify_connection(self):
        """Verifica la conexión con Binance"""
        try:
            # Verificar conexión
            self.exchange.load_markets()
            
            # Verificar si el símbolo existe
            if self.symbol not in self.exchange.markets:
                available_symbols = [s for s in self.exchange.markets.keys() if 'BTC' in s and 'USDT' in s]
                self.logger.warning(f"Símbolo {self.symbol} no encontrado. Disponibles: {available_symbols[:5]}")
                
            # Verificar permisos de la API
            balance = self.exchange.fetch_balance()
            self.logger.info(f"✅ Conexión exitosa con Binance {'Testnet' if self.testnet else 'Mainnet'}")
            
            # Log de balance inicial
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            self.logger.info(f"💰 Balance USDT disponible: ${usdt_balance:.2f}")
            
        except ccxt.AuthenticationError as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"❌ Error de autenticación: {e}")
                self.logger.error("Verifica tus API keys y permisos")
            else:
                print(f"❌ Error de autenticación: {e}")
            raise
        except ccxt.NetworkError as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"❌ Error de red: {e}")
            else:
                print(f"❌ Error de red: {e}")
            raise
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"❌ Error de conexión: {e}")
            else:
                print(f"❌ Error de conexión: {e}")
            raise
    
    def setup_logging(self):
        """Configura sistema de logging"""
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # Logger principal
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Limpiar handlers existentes
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para archivo
        file_handler = logging.FileHandler(f'logs/rsi_bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler.setFormatter(formatter)
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def init_log_files(self):
        """Inicializa archivos CSV para análisis"""
        self.trades_csv = f'logs/trades_detail_{datetime.now().strftime("%Y%m%d")}.csv'
        self.market_csv = f'logs/market_data_{datetime.now().strftime("%Y%m%d")}.csv'
        
        # Crear headers para archivo de trades
        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'action', 'side', 'price', 'quantity', 'rsi', 
                    'stop_loss', 'take_profit', 'reason', 'pnl_pct', 'pnl_usdt',
                    'balance_before', 'balance_after', 'trade_duration_mins',
                    'signal_confirmed', 'confirmation_time_mins', 'recovered'
                ])
        
        # Crear headers para archivo de datos de mercado
        if not os.path.exists(self.market_csv):
            with open(self.market_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'price', 'rsi', 'volume', 'signal', 'in_position',
                    'position_side', 'unrealized_pnl_pct', 'pending_signal',
                    'confirmation_status'
                ])
    
    def save_bot_state(self):
        """Guarda el estado actual del bot en archivo JSON"""
        try:
            state_data = {
                'timestamp': datetime.now().isoformat(),
                'in_position': self.in_position,
                'position': self.position,
                'last_signal_time': self.last_signal_time,
                'pending_long_signal': self.pending_long_signal,
                'pending_short_signal': self.pending_short_signal,
                'signal_trigger_price': self.signal_trigger_price,
                'signal_trigger_time': self.signal_trigger_time.isoformat() if self.signal_trigger_time else None,
                'confirmation_wait_count': self.confirmation_wait_count,
                'performance_metrics': self.performance_metrics,
                'last_rsi': self.last_rsi,
                'last_price': self.last_price
            }
            
            # Convertir datetime objects en position si existen
            if self.position and 'entry_time' in self.position:
                state_data['position']['entry_time'] = self.position['entry_time'].isoformat()
            
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
            
            # Verificar que el estado no sea muy antiguo (máximo 24 horas)
            state_time = datetime.fromisoformat(state_data['timestamp'])
            time_diff = datetime.now() - state_time
            
            if time_diff.total_seconds() > 86400:  # 24 horas
                self.logger.warning(f"⏰ Estado muy antiguo ({time_diff}), no se cargará")
                return False
            
            # Restaurar estado
            self.in_position = state_data.get('in_position', False)
            self.last_signal_time = state_data.get('last_signal_time', 0)
            self.pending_long_signal = state_data.get('pending_long_signal', False)
            self.pending_short_signal = state_data.get('pending_short_signal', False)
            self.signal_trigger_price = state_data.get('signal_trigger_price')
            self.confirmation_wait_count = state_data.get('confirmation_wait_count', 0)
            self.last_rsi = state_data.get('last_rsi', 50)
            self.last_price = state_data.get('last_price', 0)
            
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
    
    def check_exchange_positions(self):
        """Verifica posiciones reales en el exchange"""
        try:
            # Para futuros con apalancamiento
            try:
                if not self.testnet and self.leverage > 1:
                    # Configurar para futuros
                    self.exchange.set_sandbox_mode(False)
                    positions = self.exchange.fetch_positions([self.symbol])
                    
                    for pos in positions:
                        if pos['size'] > 0:  # Hay una posición abierta
                            self.logger.warning(f"🔍 Posición detectada en exchange: {pos['side']} {pos['size']} @ {pos['entryPrice']}")
                            return pos
            except:
                pass  # Si falla futuros, intentar spot
            
            # Para spot trading
            balance = self.exchange.fetch_balance()
            btc_balance = float(balance.get('BTC', {}).get('free', 0))
            
            if btc_balance > 0.001:  # Más de 0.001 BTC
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
                
                self.logger.warning(f"🔍 Balance BTC detectado: {btc_balance:.6f} BTC (≈${btc_balance * current_price:.2f})")
                
                # Crear posición ficticia para monitorear
                return {
                    'side': 'long',  # Asumimos long si tenemos BTC
                    'size': btc_balance,
                    'entryPrice': current_price,  # Precio actual como referencia
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
                'entry_time': datetime.now(),  # Tiempo de recuperación
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': f"recovered_{int(time.time())}",
                'entry_rsi': 50,  # RSI neutro ya que no sabemos el original
                'recovered': True
            }
            
            self.in_position = True
            
            # Log de recuperación
            with open(self.recovery_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Posición recuperada: {side} {quantity} @ ${current_price:.2f}\n")
            
            self.logger.warning(f"🔄 POSICIÓN RECUPERADA: {side.upper()} {quantity:.6f} BTC @ ${current_price:.2f}")
            self.logger.warning(f"📊 Nuevos niveles - SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")
            
            # Actualizar métricas
            self.performance_metrics['recoveries_performed'] += 1
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error recuperando posición: {e}")
            return False
    
    def recover_bot_state(self):
        """Proceso completo de recuperación del estado del bot"""
        self.logger.info("🔄 Iniciando recuperación de estado...")
        
        # 1. Intentar cargar estado desde archivo
        state_loaded = self.load_bot_state()
        
        # 2. Verificar posiciones reales en el exchange
        exchange_position = self.check_exchange_positions()
        
        # 3. Reconciliar estado
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
        
        # 4. Guardar estado actualizado
        self.save_bot_state()
        
        self.logger.info("🔄 Recuperación completada")
                
    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI usando TA-Lib o pandas"""
        try:
            # Convertir a pandas Series si es necesario
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            # Calcular cambios
            delta = prices.diff()
            
            # Separar ganancias y pérdidas
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Calcular promedios móviles
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            # Calcular RS y RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
        except Exception as e:
            self.logger.error(f"Error calculando RSI: {e}")
            return 50  # Valor neutral en caso de error
    
    def get_market_data(self):
        """Obtiene datos del mercado para calcular RSI"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol, 
                self.timeframe, 
                limit=50
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Calcular RSI
            current_price = float(df['close'].iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            current_rsi = self.calculate_rsi(df['close'])
            
            # Log datos de mercado
            self.log_market_data(current_price, current_rsi, current_volume)
            
            return {
                'price': current_price,
                'rsi': current_rsi,
                'volume': current_volume,
                'dataframe': df
            }
            
        except Exception as e:
            self.logger.error(f"Error obteniendo datos del mercado: {e}")
            return None
    
    def log_market_data(self, price, rsi, volume, signal=None):
        """Registra datos de mercado"""
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
        confirmation_status = ""
        
        if self.pending_long_signal:
            pending_signal = "LONG_WAITING"
            confirmation_status = f"Wait_{self.confirmation_wait_count}/{self.max_confirmation_wait}"
        elif self.pending_short_signal:
            pending_signal = "SHORT_WAITING"
            confirmation_status = f"Wait_{self.confirmation_wait_count}/{self.max_confirmation_wait}"
        
        # Guardar en CSV
        try:
            with open(self.market_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp.isoformat(),
                    price,
                    rsi,
                    volume,
                    signal or '',
                    self.in_position,
                    self.position['side'] if self.in_position else '',
                    unrealized_pnl,
                    pending_signal,
                    confirmation_status
                ])
        except Exception as e:
            self.logger.error(f"Error guardando datos de mercado: {e}")
            
        # Log en memoria
        self.market_data_log.append({
            'timestamp': timestamp,
            'price': price,
            'rsi': rsi,
            'signal': signal,
            'unrealized_pnl': unrealized_pnl,
            'pending_signal': pending_signal
        })
        
        # Mantener solo los últimos 1000 registros
        if len(self.market_data_log) > 1000:
            self.market_data_log = self.market_data_log[-1000:]
        
        # Guardar estado cada 10 iteraciones
        if len(self.market_data_log) % 10 == 0:
            self.save_bot_state()
    
    def reset_signal_state(self):
        """Resetea el estado de señales pendientes"""
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.confirmation_wait_count = 0
    
    def detect_rsi_signal(self, current_rsi, current_price):
        """Detecta señales iniciales de RSI"""
        signal_detected = False
        
        # Detectar señal LONG (RSI oversold)
        if current_rsi < self.rsi_oversold and not self.pending_long_signal and not self.pending_short_signal:
            self.pending_long_signal = True
            self.signal_trigger_price = current_price
            self.signal_trigger_time = datetime.now()
            self.confirmation_wait_count = 0
            signal_detected = True
            
            self.performance_metrics['signals_detected'] += 1
            self.logger.info(f"🟡 Señal LONG detectada (RSI: {current_rsi:.2f}) - Esperando confirmación...")
            self.logger.info(f"📍 Precio trigger: ${current_price:.2f} - Esperando subida de {self.confirmation_threshold}%")
            
        # Detectar señal SHORT (RSI overbought)
        elif current_rsi > self.rsi_overbought and not self.pending_long_signal and not self.pending_short_signal:
            self.pending_short_signal = True
            self.signal_trigger_price = current_price
            self.signal_trigger_time = datetime.now()
            self.confirmation_wait_count = 0
            signal_detected = True
            
            self.performance_metrics['signals_detected'] += 1
            self.logger.info(f"🟡 Señal SHORT detectada (RSI: {current_rsi:.2f}) - Esperando confirmación...")
            self.logger.info(f"📍 Precio trigger: ${current_price:.2f} - Esperando bajada de {self.confirmation_threshold}%")
        
        return signal_detected
    
    def check_signal_confirmation(self, current_price, current_rsi):
        """Verifica si la señal pendiente se confirma"""
        if not (self.pending_long_signal or self.pending_short_signal):
            return False, None
            
        self.confirmation_wait_count += 1
        
        # Verificar confirmación LONG (precio sube después de oversold)
        if self.pending_long_signal:
            price_change_pct = ((current_price - self.signal_trigger_price) / self.signal_trigger_price) * 100
            
            if price_change_pct >= self.confirmation_threshold:
                self.logger.info(f"✅ Señal LONG CONFIRMADA! Precio subió {price_change_pct:.2f}%")
                self.performance_metrics['signals_confirmed'] += 1
                self.reset_signal_state()
                return True, 'long'
                
            elif self.confirmation_wait_count >= self.max_confirmation_wait:
                self.logger.warning(f"⏰ Señal LONG EXPIRADA - Sin confirmación en {self.max_confirmation_wait} períodos")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
                
            elif current_rsi > self.rsi_oversold + 5:  # RSI se aleja mucho del oversold sin movimiento de precio
                self.logger.warning(f"❌ Señal LONG CANCELADA - RSI subió sin movimiento de precio confirmatorio")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
        
        # Verificar confirmación SHORT (precio baja después de overbought)
        elif self.pending_short_signal:
            price_change_pct = ((self.signal_trigger_price - current_price) / self.signal_trigger_price) * 100
            
            if price_change_pct >= self.confirmation_threshold:
                self.logger.info(f"✅ Señal SHORT CONFIRMADA! Precio bajó {price_change_pct:.2f}%")
                self.performance_metrics['signals_confirmed'] += 1
                self.reset_signal_state()
                return True, 'short'
                
            elif self.confirmation_wait_count >= self.max_confirmation_wait:
                self.logger.warning(f"⏰ Señal SHORT EXPIRADA - Sin confirmación en {self.max_confirmation_wait} períodos")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
                
            elif current_rsi < self.rsi_overbought - 5:  # RSI se aleja mucho del overbought sin movimiento de precio
                self.logger.warning(f"❌ Señal SHORT CANCELADA - RSI bajó sin movimiento de precio confirmatorio")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
        
        # Mostrar progreso cada 3 períodos
        if self.confirmation_wait_count % 3 == 0:
            signal_type = "LONG" if self.pending_long_signal else "SHORT"
            remaining = self.max_confirmation_wait - self.confirmation_wait_count
            price_change = ((current_price - self.signal_trigger_price) / self.signal_trigger_price) * 100
            if self.pending_short_signal:
                price_change = -price_change
                
            self.logger.info(f"⏳ Esperando confirmación {signal_type}: {self.confirmation_wait_count}/{self.max_confirmation_wait} | "
                           f"Cambio precio: {price_change:+.2f}% (necesario: {self.confirmation_threshold:+.2f}%)")
        
        return False, None
    
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
        """Calcula el tamaño de la posición"""
        balance = self.get_account_balance()
        
        if balance < self.min_balance_usdt:
            self.logger.warning(f"Balance insuficiente: ${balance:.2f} < ${self.min_balance_usdt}")
            return 0, 0
        
        # Calcular valor de la posición
        position_value = balance * (self.position_size_pct / 100)
        
        # Con apalancamiento (si está habilitado)
        effective_position = position_value * self.leverage
        
        # Calcular cantidad de BTC
        quantity = effective_position / price
        
        # Redondear a 6 decimales (típico para BTC)
        quantity = round(quantity, 6)
        
        return quantity, position_value
    
    def create_test_order(self, side, quantity, price):
        """Simula una orden para testnet cuando hay problemas de balance"""
        order_id = f"test_{int(time.time())}"
        
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
    
    def open_long_position(self, price, rsi, confirmation_time=None):
        """Abre posición LONG"""
        try:
            quantity, position_value = self.calculate_position_size(price)
            
            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False
            
            # Calcular precios de stop loss y take profit
            stop_price = price * (1 - self.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.take_profit_pct / 100)
            
            # Intentar crear orden real primero
            try:
                if self.testnet:
                    # En testnet, a veces necesitamos simular
                    order = self.exchange.create_market_order(
                        self.symbol,
                        'buy',
                        quantity
                    )
                else:
                    order = self.exchange.create_market_order(
                        self.symbol,
                        'buy',
                        quantity,
                        None,  # precio market
                        None,  # sin params adicionales por ahora
                    )
            except Exception as order_error:
                self.logger.warning(f"Error creando orden real: {order_error}")
                # Crear orden simulada
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
                'confirmation_time': confirmation_time,
                'recovered': False
            }
            
            self.in_position = True
            
            self.logger.info(f"🟢 LONG EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'long', price, quantity, rsi, 'RSI Oversold + Confirmación', confirmation_time=confirmation_time)
            
            # Guardar estado inmediatamente después de abrir posición
            self.save_bot_state()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición LONG: {e}")
            return False
    
    def open_short_position(self, price, rsi, confirmation_time=None):
        """Abre posición SHORT"""
        try:
            quantity, position_value = self.calculate_position_size(price)
            
            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False
            
            # Calcular precios de stop loss y take profit  
            stop_price = price * (1 + self.stop_loss_pct / 100)
            take_profit_price = price * (1 - self.take_profit_pct / 100)
            
            # Intentar crear orden real primero
            try:
                if self.testnet:
                    order = self.exchange.create_market_order(
                        self.symbol,
                        'sell',
                        quantity
                    )
                else:
                    order = self.exchange.create_market_order(
                        self.symbol,
                        'sell',
                        quantity,
                        None,
                    )
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
                'confirmation_time': confirmation_time,
                'recovered': False
            }
            
            self.in_position = True
            
            self.logger.info(f"🔴 SHORT EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'short', price, quantity, rsi, 'RSI Overbought + Confirmación', confirmation_time=confirmation_time)
            
            # Guardar estado inmediatamente después de abrir posición
            self.save_bot_state()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición SHORT: {e}")
            return False
    
    def close_position(self, reason="Manual", current_rsi=None, current_price=None):
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
                order = self.exchange.create_market_order(
                    self.symbol,
                    side,
                    self.position['quantity']
                )
            except Exception as order_error:
                self.logger.warning(f"Error creando orden de cierre: {order_error}")
                order = self.create_test_order(side, self.position['quantity'], current_price)
            
            # Calcular P&L
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
            
            # Aplicar apalancamiento al P&L
            pnl_pct *= self.leverage
            
            self.logger.info(f"⭕ Posición cerrada - {reason}")
            self.logger.info(f"💰 P&L: {pnl_pct:.2f}% (con {self.leverage}x leverage)")
            
            # Log detallado del cierre
            self.log_trade('CLOSE', self.position['side'], current_price, 
                          self.position['quantity'], current_rsi, reason, pnl_pct)
            
            self.position = None
            self.in_position = False
            
            # Guardar estado inmediatamente después de cerrar posición
            self.save_bot_state()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
            return False
    
    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None, reason=None, pnl_pct=None, confirmation_time=None):
        """Registra trades detallados"""
        timestamp = datetime.now()
        balance = self.get_account_balance()
        
        trade_data = {
            'timestamp': timestamp,
            'action': action,
            'side': side,
            'price': price,
            'quantity': quantity,
            'rsi': rsi,
            'reason': reason,
            'pnl_pct': pnl_pct,
            'balance': balance,
            'confirmation_time': confirmation_time
        }
        
        # Calcular duración del trade si es cierre
        trade_duration = 0
        confirmation_time_mins = 0
        is_recovered = False
        
        if action == 'CLOSE' and self.trades_log:
            last_open = next((t for t in reversed(self.trades_log) if t['action'] == 'OPEN'), None)
            if last_open:
                trade_duration = (timestamp - last_open['timestamp']).total_seconds() / 60
                if last_open.get('confirmation_time'):
                    confirmation_time_mins = last_open['confirmation_time']
        
        if action == 'OPEN' and self.position and self.position.get('recovered'):
            is_recovered = True
        
        # Guardar en CSV
        try:
            with open(self.trades_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                
                if action == 'OPEN':
                    signal_confirmed = "YES" if confirmation_time is not None else "NO"
                    conf_time = confirmation_time if confirmation_time else 0
                    recovered = "YES" if is_recovered else "NO"
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        self.position['stop_loss'] if self.position else '',
                        self.position['take_profit'] if self.position else '',
                        reason or '', '', '', balance, '', '',
                        signal_confirmed, conf_time, recovered
                    ])
                else:  # CLOSE
                    pnl_usdt = (pnl_pct / 100) * balance if pnl_pct else 0
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        '', '', reason or '', pnl_pct or 0, pnl_usdt,
                        '', balance, trade_duration, '', confirmation_time_mins, ''
                    ])
        except Exception as e:
            self.logger.error(f"Error guardando trade: {e}")
        
        # Guardar en memoria
        self.trades_log.append(trade_data)
        
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
    
    def check_exit_conditions(self, current_price, current_rsi):
        """Verifica condiciones de salida"""
        if not self.in_position or not self.position:
            return
            
        if self.position['side'] == 'long':
            if current_price <= self.position['stop_loss']:
                self.close_position("Stop Loss", current_rsi, current_price)
            elif current_price >= self.position['take_profit']:
                self.close_position("Take Profit", current_rsi, current_price)
        else:  # SHORT
            if current_price >= self.position['stop_loss']:
                self.close_position("Stop Loss", current_rsi, current_price)
            elif current_price <= self.position['take_profit']:
                self.close_position("Take Profit", current_rsi, current_price)
    
    def analyze_and_trade(self):
        """Análisis principal y ejecución de trades"""
        # Obtener datos del mercado
        market_data = self.get_market_data()
        if not market_data:
            return
            
        current_rsi = market_data['rsi']
        current_price = market_data['price']
        
        self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.2f}")
        
        # Verificar condiciones de salida si estamos en posición
        self.check_exit_conditions(current_price, current_rsi)
        
        # Si estamos en posición, no buscar nuevas señales
        if self.in_position:
            return
        
        # Verificar confirmación de señales pendientes
        confirmed, signal_type = self.check_signal_confirmation(current_price, current_rsi)
        
        if confirmed:
            current_time = time.time()
            
            # Calcular tiempo de confirmación
            confirmation_time_mins = 0
            if self.signal_trigger_time:
                confirmation_time_mins = (datetime.now() - self.signal_trigger_time).total_seconds() / 60
            
            if signal_type == 'long':
                if self.open_long_position(current_price, current_rsi, confirmation_time_mins):
                    self.last_signal_time = current_time
            elif signal_type == 'short':
                if self.open_short_position(current_price, current_rsi, confirmation_time_mins):
                    self.last_signal_time = current_time
        
        # Solo buscar nuevas señales si no hay señales pendientes y ha pasado tiempo suficiente
        elif not (self.pending_long_signal or self.pending_short_signal):
            current_time = time.time()
            if current_time - self.last_signal_time >= 300:  # 5 minutos
                self.detect_rsi_signal(current_rsi, current_price)
        
        # Actualizar datos históricos
        self.last_rsi = current_rsi
        self.last_price = current_price
    
    def run(self):
        """Ejecuta el bot en un loop continuo"""
        self.logger.info("🤖 Bot RSI con Recuperación de Posiciones iniciado")
        self.logger.info(f"📊 Config: RSI({self.rsi_period}) | OS: {self.rsi_oversold} | OB: {self.rsi_overbought}")
        self.logger.info(f"⚡ Leverage: {self.leverage}x | Risk: {self.position_size_pct}% | SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        self.logger.info(f"🔔 Confirmación: {self.confirmation_threshold}% movimiento | Max espera: {self.max_confirmation_wait} períodos")
        self.logger.info(f"💾 Estado guardado en: {self.state_file}")
        
        # Mostrar performance cada 20 iteraciones
        iteration = 0
        
        try:
            while True:
                self.analyze_and_trade()
                
                # Mostrar resumen cada 10 minutos aproximadamente
                iteration += 1
                if iteration % 20 == 0:
                    self.log_performance_summary()
                
                time.sleep(30)  # Verificar cada 30 segundos
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Bot detenido por el usuario")
            if self.in_position:
                self.close_position("Bot detenido")
            self.save_bot_state()
            self.log_performance_summary()
                
        except Exception as e:
            self.logger.error(f"Error en el bot: {e}")
            if self.in_position:
                self.close_position("Error del bot")
            self.save_bot_state()
    
    def log_performance_summary(self):
        """Muestra resumen de performance"""
        metrics = self.performance_metrics
        
        self.logger.info("="*60)
        self.logger.info("📊 RESUMEN DE PERFORMANCE")
        self.logger.info("="*60)
        
        # Estadísticas de señales
        signal_confirmation_rate = 0
        if metrics['signals_detected'] > 0:
            signal_confirmation_rate = (metrics['signals_confirmed'] / metrics['signals_detected']) * 100
        
        self.logger.info(f"🔔 Señales detectadas: {metrics['signals_detected']}")
        self.logger.info(f"✅ Señales confirmadas: {metrics['signals_confirmed']}")
        self.logger.info(f"⏰ Señales expiradas: {metrics['signals_expired']}")
        self.logger.info(f"📈 Tasa de confirmación: {signal_confirmation_rate:.1f}%")
        self.logger.info(f"🔄 Recuperaciones realizadas: {metrics['recoveries_performed']}")
        self.logger.info("-" * 40)
        
        if metrics['total_trades'] == 0:
            self.logger.info("📊 Sin trades completados aún")
        else:
            win_rate = (metrics['winning_trades'] / metrics['total_trades']) * 100
            avg_pnl = metrics['total_pnl'] / metrics['total_trades']
            
            self.logger.info(f"🔢 Total Trades: {metrics['total_trades']}")
            self.logger.info(f"🎯 Win Rate: {win_rate:.1f}%")
            self.logger.info(f"💰 PnL Promedio: {avg_pnl:.2f}%")
            self.logger.info(f"💰 PnL Total: {metrics['total_pnl']:.2f}%")
            self.logger.info(f"✅ Ganadores: {metrics['winning_trades']}")
            self.logger.info(f"❌ Perdedores: {metrics['losing_trades']}")
            self.logger.info(f"📉 Max Pérdidas Consecutivas: {metrics['max_consecutive_losses']}")
        
        self.logger.info(f"💵 Balance Actual: ${self.get_account_balance():.2f}")
        
        # Estado actual
        if self.in_position:
            pos_type = "RECUPERADA" if self.position.get('recovered') else "ACTIVA"
            self.logger.info(f"📍 Posición {pos_type}: {self.position['side'].upper()}")
        elif self.pending_long_signal:
            self.logger.info(f"⏳ Esperando confirmación LONG ({self.confirmation_wait_count}/{self.max_confirmation_wait})")
        elif self.pending_short_signal:
            self.logger.info(f"⏳ Esperando confirmación SHORT ({self.confirmation_wait_count}/{self.max_confirmation_wait})")
        else:
            self.logger.info("🔍 Buscando oportunidades...")
        
        self.logger.info("="*60)

# Ejemplo de uso
if __name__ == "__main__":
    
    # Configuración con variables de entorno
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    if not API_KEY or not API_SECRET:
        print("❌ ERROR: Variables de entorno no configuradas")
        print("Configura BINANCE_API_KEY y BINANCE_API_SECRET en un archivo .env")
        exit(1)
    
    print(f"🤖 Iniciando bot en modo: {'TESTNET' if USE_TESTNET else 'REAL TRADING'}")
    print("🔔 NUEVO: Sistema de confirmación de movimiento activado")
    print("💾 NUEVO: Sistema de recuperación de posiciones activado")
    
    if not USE_TESTNET:
        print("⚠️  ADVERTENCIA: Vas a usar DINERO REAL")
        confirmation = input("¿Estás seguro? (yes/no): ")
        if confirmation.lower() != 'yes':
            print("🛑 Bot cancelado por seguridad")
            exit(1)
    
    # Auto-restart en caso de errores
    restart_count = 0
    max_restarts = 3
    
    while restart_count < max_restarts:
        try:
            bot = BinanceRSIBot(
                api_key=API_KEY,
                api_secret=API_SECRET, 
                testnet=USE_TESTNET
            )
            
            bot.run()
            break  # Salir del loop si termina normalmente
            
        except KeyboardInterrupt:
            print("🛑 Bot detenido por el usuario")
            break
            
        except Exception as e:
            restart_count += 1
            print(f"❌ Error crítico ({restart_count}/{max_restarts}): {e}")
            
            if restart_count < max_restarts:
                wait_time = 30 * restart_count
                print(f"🔄 Reiniciando en {wait_time} segundos...")
                time.sleep(wait_time)
            else:
                print("💀 Máximo de reinicios alcanzado. Bot detenido.")
                break