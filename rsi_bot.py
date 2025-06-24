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
        Bot de trading RSI agresivo para Binance
        
        Args:
            api_key: Tu API key de Binance
            api_secret: Tu API secret de Binance  
            testnet: True para usar testnet, False para trading real
        """
        
        # Configuración del exchange
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': testnet,  # Usar testnet para pruebas
            'enableRateLimit': True,
        })
        
        # Configuración de la estrategia RSI agresiva
        self.symbol = 'BTC/USDT'
        self.timeframe = '5m'  # 5 minutos para señales frecuentes
        self.rsi_period = 14
        self.rsi_oversold = 25  # Más agresivo que 30
        self.rsi_overbought = 75  # Más agresivo que 70
        
        # Gestión de riesgo
        self.leverage = 10  # Apalancamiento
        self.position_size_pct = 5  # 5% del capital por trade
        self.stop_loss_pct = 3  # Stop loss al 3%
        self.take_profit_pct = 6  # Take profit al 6%
        
        # Estado del bot
        self.position = None
        self.in_position = False
        self.last_signal_time = 0
        
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
            'peak_balance': 0
        }
        
        # Configurar logging detallado
        self.setup_logging()
        
        # Inicializar archivos de logs
        self.init_log_files()
        
    def setup_logging(self):
        """Configura sistema de logging avanzado"""
        # Crear directorio de logs si no existe
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # Logger principal
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Formatter detallado
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para archivo general
        file_handler = logging.FileHandler(f'logs/rsi_bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler.setFormatter(formatter)
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Handler específico para trades
        trade_handler = logging.FileHandler(f'logs/trades_{datetime.now().strftime("%Y%m%d")}.log')
        trade_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Logger específico para trades
        self.trade_logger = logging.getLogger('trades')
        self.trade_logger.setLevel(logging.INFO)
        self.trade_logger.addHandler(trade_handler)
        
    def init_log_files(self):
        """Inicializa archivos CSV para análisis detallado"""
        self.trades_csv = f'logs/trades_detail_{datetime.now().strftime("%Y%m%d")}.csv'
        self.market_csv = f'logs/market_data_{datetime.now().strftime("%Y%m%d")}.csv'
        self.performance_csv = f'logs/performance_{datetime.now().strftime("%Y%m%d")}.csv'
        
        # Crear headers para archivo de trades
        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'action', 'side', 'price', 'quantity', 'rsi', 
                    'stop_loss', 'take_profit', 'reason', 'pnl_pct', 'pnl_usdt',
                    'balance_before', 'balance_after', 'trade_duration_mins'
                ])
        
        # Crear headers para archivo de datos de mercado
        if not os.path.exists(self.market_csv):
            with open(self.market_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'price', 'rsi', 'volume', 'signal', 'in_position',
                    'position_side', 'unrealized_pnl_pct'
                ])
                
        # Crear headers para métricas de performance
        if not os.path.exists(self.performance_csv):
            with open(self.performance_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'total_trades', 'win_rate', 'total_pnl_pct', 
                    'avg_win_pct', 'avg_loss_pct', 'max_drawdown_pct',
                    'sharpe_ratio', 'profit_factor', 'current_balance'
                ])
                
    def log_market_data(self, price, rsi, volume, signal=None):
        """Registra datos de mercado para análisis"""
        timestamp = datetime.now()
        
        # Calcular PnL no realizado si estamos en posición
        unrealized_pnl = 0
        if self.in_position:
            if self.position['side'] == 'long':
                unrealized_pnl = ((price - self.position['entry_price']) / self.position['entry_price']) * 100 * self.leverage
            else:
                unrealized_pnl = ((self.position['entry_price'] - price) / self.position['entry_price']) * 100 * self.leverage
        
        # Guardar en CSV
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
                unrealized_pnl
            ])
            
        # Log en memoria para análisis en tiempo real
        self.market_data_log.append({
            'timestamp': timestamp,
            'price': price,
            'rsi': rsi,
            'signal': signal,
            'unrealized_pnl': unrealized_pnl
        })
        
        # Mantener solo los últimos 1000 registros en memoria
        if len(self.market_data_log) > 1000:
            self.market_data_log = self.market_data_log[-1000:]
            
    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None, reason=None, pnl_pct=None):
        """Registra trades detallados para análisis"""
        timestamp = datetime.now()
        balance = self.get_account_balance()
        
        trade_data = {
            'timestamp': timestamp,
            'action': action,  # 'OPEN' o 'CLOSE'
            'side': side,
            'price': price,
            'quantity': quantity,
            'rsi': rsi,
            'reason': reason,
            'pnl_pct': pnl_pct,
            'balance': balance
        }
        
        # Calcular duración del trade si es cierre
        trade_duration = 0
        if action == 'CLOSE' and self.trades_log:
            last_open = next((t for t in reversed(self.trades_log) if t['action'] == 'OPEN'), None)
            if last_open:
                trade_duration = (timestamp - last_open['timestamp']).total_seconds() / 60
        
        # Guardar en CSV detallado
        with open(self.trades_csv, 'a', newline='') as f:
            writer = csv.writer(f)
            
            if action == 'OPEN':
                writer.writerow([
                    timestamp.isoformat(), action, side, price, quantity, rsi,
                    self.position['stop_loss'] if self.position else '',
                    self.position['take_profit'] if self.position else '',
                    reason or '', '', '', balance, '', ''
                ])
            else:  # CLOSE
                pnl_usdt = (pnl_pct / 100) * balance if pnl_pct else 0
                writer.writerow([
                    timestamp.isoformat(), action, side, price, quantity, rsi,
                    '', '', reason or '', pnl_pct or 0, pnl_usdt,
                    '', balance, trade_duration
                ])
        
        # Log detallado en archivo de trades
        if action == 'OPEN':
            self.trade_logger.info(f"🔴 TRADE OPENED | {side.upper()} | Price: ${price:.2f} | RSI: {rsi:.2f} | Qty: {quantity:.6f}")
            self.trade_logger.info(f"📊 SL: ${self.position['stop_loss']:.2f} | TP: ${self.position['take_profit']:.2f} | Balance: ${balance:.2f}")
        else:
            self.trade_logger.info(f"🟢 TRADE CLOSED | {reason} | PnL: {pnl_pct:.2f}% | Duration: {trade_duration:.1f}min | Balance: ${balance:.2f}")
        
        # Guardar en memoria
        self.trades_log.append(trade_data)
        
        # Actualizar métricas
        self.update_performance_metrics(action, pnl_pct)
        
    def update_performance_metrics(self, action, pnl_pct=None):
        """Actualiza métricas de rendimiento"""
        if action == 'CLOSE' and pnl_pct is not None:
            self.performance_metrics['total_trades'] += 1
            self.performance_metrics['total_pnl'] += pnl_pct
            
            current_balance = self.get_account_balance()
            
            # Inicializar balance inicial
            if self.performance_metrics['start_balance'] == 0:
                self.performance_metrics['start_balance'] = current_balance
                self.performance_metrics['peak_balance'] = current_balance
            
            # Actualizar peak balance
            if current_balance > self.performance_metrics['peak_balance']:
                self.performance_metrics['peak_balance'] = current_balance
            
            # Calcular drawdown
            drawdown = ((self.performance_metrics['peak_balance'] - current_balance) / 
                       self.performance_metrics['peak_balance']) * 100
            
            if drawdown > self.performance_metrics['max_drawdown']:
                self.performance_metrics['max_drawdown'] = drawdown
            
            # Trades ganadores/perdedores
            if pnl_pct > 0:
                self.performance_metrics['winning_trades'] += 1
                self.performance_metrics['consecutive_losses'] = 0
            else:
                self.performance_metrics['losing_trades'] += 1
                self.performance_metrics['consecutive_losses'] += 1
                
                if self.performance_metrics['consecutive_losses'] > self.performance_metrics['max_consecutive_losses']:
                    self.performance_metrics['max_consecutive_losses'] = self.performance_metrics['consecutive_losses']
            
            # Log métricas cada 10 trades
            if self.performance_metrics['total_trades'] % 10 == 0:
                self.log_performance_summary()
                
    def log_performance_summary(self):
        """Registra resumen de performance"""
        metrics = self.performance_metrics
        total_trades = metrics['total_trades']
        
        if total_trades == 0:
            return
            
        # Calcular estadísticas
        win_rate = (metrics['winning_trades'] / total_trades) * 100
        avg_pnl = metrics['total_pnl'] / total_trades
        
        # Calcular promedio de ganancias y pérdidas
        winning_trades = [t for t in self.trades_log if t['action'] == 'CLOSE' and t.get('pnl_pct', 0) > 0]
        losing_trades = [t for t in self.trades_log if t['action'] == 'CLOSE' and t.get('pnl_pct', 0) < 0]
        
        avg_win = np.mean([t.get('pnl_pct', 0) for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.get('pnl_pct', 0) for t in losing_trades]) if losing_trades else 0
        
        # Profit factor
        total_wins = sum([t.get('pnl_pct', 0) for t in winning_trades])
        total_losses = abs(sum([t.get('pnl_pct', 0) for t in losing_trades]))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Sharpe ratio aproximado (simplificado)
        pnl_values = [t.get('pnl_pct', 0) for t in self.trades_log if t['action'] == 'CLOSE']
        sharpe = (np.mean(pnl_values) / np.std(pnl_values)) if len(pnl_values) > 1 and np.std(pnl_values) > 0 else 0
        
        current_balance = self.get_account_balance()
        total_return = ((current_balance - metrics['start_balance']) / metrics['start_balance']) * 100 if metrics['start_balance'] > 0 else 0
        
        # Log en consola
        self.logger.info("="*60)
        self.logger.info("📊 PERFORMANCE SUMMARY")
        self.logger.info("="*60)
        self.logger.info(f"🔢 Total Trades: {total_trades}")
        self.logger.info(f"🎯 Win Rate: {win_rate:.1f}%")
        self.logger.info(f"💰 Total Return: {total_return:.2f}%")
        self.logger.info(f"📈 Avg Win: {avg_win:.2f}% | Avg Loss: {avg_loss:.2f}%")
        self.logger.info(f"⚡ Profit Factor: {profit_factor:.2f}")
        self.logger.info(f"📉 Max Drawdown: {metrics['max_drawdown']:.2f}%")
        self.logger.info(f"❌ Max Consecutive Losses: {metrics['max_consecutive_losses']}")
        self.logger.info(f"📊 Sharpe Ratio: {sharpe:.2f}")
        self.logger.info(f"💵 Current Balance: ${current_balance:.2f}")
        self.logger.info("="*60)
        
        # Guardar en CSV de performance
        with open(self.performance_csv, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                total_trades,
                win_rate,
                total_return,
                avg_win,
                avg_loss,
                metrics['max_drawdown'],
                sharpe,
                profit_factor,
                current_balance
            ])
            
    def log_signal_analysis(self, rsi, price, signal_type=None):
        """Registra análisis de señales para optimización futura"""
        if signal_type:
            self.logger.info(f"🔍 SIGNAL ANALYSIS | Type: {signal_type} | RSI: {rsi:.2f} | Price: ${price:.2f}")
            
            # Analizar contexto del mercado
            if len(self.market_data_log) >= 10:
                recent_prices = [d['price'] for d in self.market_data_log[-10:]]
                price_trend = 'UP' if recent_prices[-1] > recent_prices[0] else 'DOWN'
                volatility = np.std(recent_prices) / np.mean(recent_prices) * 100
                
                self.logger.info(f"📈 Market Context | Trend: {price_trend} | Volatility: {volatility:.2f}%")
                
                # Log para análisis posterior
                with open(f'logs/signals_{datetime.now().strftime("%Y%m%d")}.log', 'a') as f:
                    f.write(f"{datetime.now().isoformat()},{signal_type},{rsi:.2f},{price:.2f},{price_trend},{volatility:.2f}\n")
        
    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI (Relative Strength Index)"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = pd.Series(gains).rolling(window=period).mean()
        avg_losses = pd.Series(losses).rolling(window=period).mean()
        
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]  # Retorna el último valor de RSI
    
    def get_market_data(self):
        """Obtiene datos del mercado para calcular RSI"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol, 
                self.timeframe, 
                limit=50  # 50 períodos para cálculo de RSI
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Log datos de mercado
            current_price = df['close'].iloc[-1]
            current_volume = df['volume'].iloc[-1]
            current_rsi = self.calculate_rsi(df['close'].values) if len(df) >= self.rsi_period + 1 else 0
            
            # Registrar datos de mercado
            self.log_market_data(current_price, current_rsi, current_volume)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error obteniendo datos del mercado: {e}")
            return None
    
    def get_account_balance(self):
        """Obtiene el balance de la cuenta"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance['USDT']['free']
            return float(usdt_balance)
            
        except Exception as e:
            self.logger.error(f"Error obteniendo balance: {e}")
            return 0
    
    def calculate_position_size(self, price):
        """Calcula el tamaño de la posición basado en el riesgo"""
        balance = self.get_account_balance()
        position_value = balance * (self.position_size_pct / 100)
        
        # Con apalancamiento
        leveraged_position = position_value * self.leverage
        quantity = leveraged_position / price
        
        return quantity, position_value
    
    def open_long_position(self, price, rsi):
        """Abre posición LONG"""
        try:
            quantity, position_value = self.calculate_position_size(price)
            
            # Calcular precios de stop loss y take profit
            stop_price = price * (1 - self.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.take_profit_pct / 100)
            
            # Orden de apertura
            order = self.exchange.create_market_order(
                self.symbol,
                'buy',
                quantity,
                price,
                params={'leverage': self.leverage}
            )
            
            self.position = {
                'side': 'long',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi
            }
            
            self.in_position = True
            
            self.logger.info(f"✅ LONG abierto: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 Stop Loss: ${stop_price:.2f} | Take Profit: ${take_profit_price:.2f}")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'long', price, quantity, rsi, 'RSI Oversold Signal')
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición LONG: {e}")
            return False
    
    def open_short_position(self, price, rsi):
        """Abre posición SHORT"""
        try:
            quantity, position_value = self.calculate_position_size(price)
            
            # Calcular precios de stop loss y take profit  
            stop_price = price * (1 + self.stop_loss_pct / 100)
            take_profit_price = price * (1 - self.take_profit_pct / 100)
            
            # Orden de apertura
            order = self.exchange.create_market_order(
                self.symbol,
                'sell',
                quantity,
                price,
                params={'leverage': self.leverage}
            )
            
            self.position = {
                'side': 'short',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi
            }
            
            self.in_position = True
            
            self.logger.info(f"✅ SHORT abierto: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 Stop Loss: ${stop_price:.2f} | Take Profit: ${take_profit_price:.2f}")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'short', price, quantity, rsi, 'RSI Overbought Signal')
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición SHORT: {e}")
            return False
    
    def close_position(self, reason="Manual", current_rsi=None):
        """Cierra la posición actual"""
        if not self.in_position:
            return
            
        try:
            side = 'sell' if self.position['side'] == 'long' else 'buy'
            
            order = self.exchange.create_market_order(
                self.symbol,
                side,
                self.position['quantity']
            )
            
            current_price = self.exchange.fetch_ticker(self.symbol)['last']
            
            # Calcular P&L
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
            
            # Aplicar apalancamiento al P&L
            pnl_pct *= self.leverage
            
            self.logger.info(f"🔴 Posición cerrada - {reason}")
            self.logger.info(f"💰 P&L: {pnl_pct:.2f}% (con {self.leverage}x leverage)")
            
            # Log detallado del cierre
            self.log_trade('CLOSE', self.position['side'], current_price, 
                          self.position['quantity'], current_rsi, reason, pnl_pct)
            
            self.position = None
            self.in_position = False
            
        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
    
    def check_exit_conditions(self, current_price, current_rsi):
        """Verifica condiciones de salida (stop loss / take profit)"""
        if not self.in_position:
            return
            
        if self.position['side'] == 'long':
            # Stop loss o take profit para LONG
            if current_price <= self.position['stop_loss']:
                self.close_position("Stop Loss", current_rsi)
            elif current_price >= self.position['take_profit']:
                self.close_position("Take Profit", current_rsi)
                
        else:  # SHORT
            # Stop loss o take profit para SHORT
            if current_price >= self.position['stop_loss']:
                self.close_position("Stop Loss", current_rsi)
            elif current_price <= self.position['take_profit']:
                self.close_position("Take Profit", current_rsi)
    
    def analyze_and_trade(self):
        """Análisis principal y ejecución de trades"""
        
        # Obtener datos del mercado
        df = self.get_market_data()
        if df is None or len(df) < self.rsi_period + 1:
            return
            
        # Calcular RSI
        current_rsi = self.calculate_rsi(df['close'].values)
        current_price = df['close'].iloc[-1]
        
        self.logger.info(f"📈 BTC: ${current_price:.2f} | RSI: {current_rsi:.2f}")
        
        # Verificar condiciones de salida si estamos en posición
        self.check_exit_conditions(current_price, current_rsi)
        
        # Evitar señales muy frecuentes (mínimo 5 minutos entre señales)
        current_time = time.time()
        if current_time - self.last_signal_time < 300:  # 5 minutos
            return
            
        # Señales de entrada (solo si no estamos en posición)
        if not self.in_position:
            
            # Señal LONG (RSI oversold)
            if current_rsi < self.rsi_oversold:
                self.logger.info(f"🟢 Señal LONG detectada - RSI: {current_rsi:.2f}")
                self.log_signal_analysis(current_rsi, current_price, 'LONG_SIGNAL')
                if self.open_long_position(current_price, current_rsi):
                    self.last_signal_time = current_time
                    
            # Señal SHORT (RSI overbought)
            elif current_rsi > self.rsi_overbought:
                self.logger.info(f"🔴 Señal SHORT detectada - RSI: {current_rsi:.2f}")
                self.log_signal_analysis(current_rsi, current_price, 'SHORT_SIGNAL')
                if self.open_short_position(current_price, current_rsi):
                    self.last_signal_time = current_time
    
    def run(self):
        """Ejecuta el bot en un loop continuo"""
        self.logger.info("🤖 Bot RSI Agresivo iniciado")
        self.logger.info(f"📊 Configuración: RSI({self.rsi_period}) | OS: {self.rsi_oversold} | OB: {self.rsi_overbought}")
        self.logger.info(f"⚡ Apalancamiento: {self.leverage}x | Risk: {self.position_size_pct}% | SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        
        try:
            while True:
                self.analyze_and_trade()
                time.sleep(30)  # Verificar cada 30 segundos
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Bot detenido por el usuario")
            if self.in_position:
                self.close_position("Bot detenido")
                
        except Exception as e:
            self.logger.error(f"Error en el bot: {e}")
            if self.in_position:
                self.close_position("Error del bot")

# Ejemplo de uso
if __name__ == "__main__":
    
    # ⚠️ CONFIGURACIÓN CON VARIABLES DE ENTORNO ⚠️
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    if not API_KEY or not API_SECRET:
        print("❌ ERROR: Variables de entorno no configuradas")
        print("Configura BINANCE_API_KEY y BINANCE_API_SECRET")
        exit(1)
    
    print(f"🤖 Iniciando bot en modo: {'TESTNET' if USE_TESTNET else 'REAL TRADING'}")
    
    # Auto-restart en caso de errores críticos
    restart_count = 0
    max_restarts = 5
    
    while restart_count < max_restarts:
        try:
            # Crear y ejecutar el bot
            bot = BinanceRSIBot(
                api_key=API_KEY,
                api_secret=API_SECRET, 
                testnet=USE_TESTNET
            )
            
            bot.run()
            break  # Si termina normalmente, salir del loop
            
        except KeyboardInterrupt:
            print("🛑 Bot detenido por el usuario")
            break
            
        except Exception as e:
            restart_count += 1
            print(f"❌ Error crítico ({restart_count}/{max_restarts}): {e}")
            
            if restart_count < max_restarts:
                wait_time = min(60 * restart_count, 300)  # Max 5 minutos
                print(f"🔄 Reiniciando en {wait_time} segundos...")
                time.sleep(wait_time)
            else:
                print("💀 Máximo de reinicios alcanzado. Bot detenido.")
                break