import ccxt
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
import time
import logging
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class SimpleRSIBot:
    def __init__(self):
        self.setup_logging()
        self.setup_exchange()
        self.symbol = 'BTC/USDT'
        self.timeframe = '5m'
        self.rsi_period = 14
        self.rsi_oversold = 25
        self.rsi_overbought = 75
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)

    def setup_exchange(self):
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'sandbox': True,
            'enableRateLimit': True,
        })
        
    def get_rsi(self):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            rsi_indicator = RSIIndicator(close=df['close'], window=self.rsi_period)
            rsi = rsi_indicator.rsi().iloc[-1]
            price = df['close'].iloc[-1]
            
            return price, rsi
        except Exception as e:
            self.logger.error(f"Error obteniendo RSI: {e}")
            return None, None
    
    def place_simple_order(self, side):
        """Orden simplificada para testing"""
        try:
            # Solo para testing - NO usar dinero real
            balance = self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            
            if usdt_balance < 10:
                self.logger.warning("⚠️ Balance insuficiente para testing")
                return None
                
            # Cantidad mínima para testing
            quantity = 0.001  # 0.001 BTC para testing
            
            self.logger.info(f"🧪 SIMULANDO orden {side}: {quantity} BTC")
            self.logger.info(f"💰 Balance disponible: {usdt_balance:.2f} USDT")
            
            # En modo testnet, solo logear la orden
            order_info = {
                'side': side,
                'amount': quantity,
                'symbol': self.symbol,
                'status': 'simulated',
                'timestamp': datetime.now().isoformat()
            }
            
            self.logger.info(f"✅ Orden SIMULADA: {order_info}")
            return order_info
            
        except Exception as e:
            self.logger.error(f"❌ Error en orden: {e}")
            return None
    
    def run(self):
        self.logger.info("🤖 Bot RSI Simple iniciado")
        self.logger.info(f"📊 Configuración: RSI({self.rsi_period}) | OS: {self.rsi_oversold} | OB: {self.rsi_overbought}")
        
        last_signal_time = 0
        
        while True:
            try:
                price, rsi = self.get_rsi()
                
                if price and rsi:
                    self.logger.info(f"📈 BTC: ${price:,.2f} | RSI: {rsi:.2f}")
                    
                    current_time = time.time()
                    
                    # Evitar spam de señales (mínimo 5 minutos entre señales)
                    if current_time - last_signal_time > 300:
                        
                        if rsi < self.rsi_oversold:
                            self.logger.info(f"🟢 Señal COMPRA detectada - RSI: {rsi:.2f}")
                            order = self.place_simple_order('BUY')
                            if order:
                                last_signal_time = current_time
                                
                        elif rsi > self.rsi_overbought:
                            self.logger.info(f"🔴 Señal VENTA detectada - RSI: {rsi:.2f}")
                            order = self.place_simple_order('SELL')
                            if order:
                                last_signal_time = current_time
                
                time.sleep(30)  # Esperar 30 segundos
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Bot detenido por usuario")
                break
            except Exception as e:
                self.logger.error(f"Error en loop principal: {e}")
                time.sleep(10)

if __name__ == "__main__":
    bot = SimpleRSIBot()
    bot.run()
