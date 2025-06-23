"""
Configuración centralizada para el Bot RSI Trading
Todas las configuraciones se pueden sobrescribir con variables de entorno
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class Config:
    """Configuración del bot"""
    
    # API Configuration
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    # Trading Configuration
    SYMBOL = os.getenv('SYMBOL', 'BTC/USDT')
    TIMEFRAME = os.getenv('TIMEFRAME', '5m')
    
    # RSI Configuration
    RSI_PERIOD = int(os.getenv('RSI_PERIOD', '14'))
    RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', '25'))
    RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', '75'))
    
    # Risk Management
    LEVERAGE = int(os.getenv('LEVERAGE', '10'))
    POSITION_SIZE_PCT = float(os.getenv('POSITION_SIZE_PCT', '5'))
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '3'))
    TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', '6'))
    
    # Bot Behavior
    MIN_SIGNAL_INTERVAL = int(os.getenv('MIN_SIGNAL_INTERVAL', '300'))  # 5 minutes
    MAX_RESTARTS = int(os.getenv('MAX_RESTARTS', '5'))
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '30'))  # seconds
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '30'))
    
    # Webhook
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'default_secret_change_me')
    WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '9000'))
    
    # Safety Features
    MAX_CONSECUTIVE_LOSSES = int(os.getenv('MAX_CONSECUTIVE_LOSSES', '5'))
    DAILY_LOSS_LIMIT_PCT = float(os.getenv('DAILY_LOSS_LIMIT_PCT', '10'))
    
    @classmethod
    def validate(cls):
        """Validar configuración"""
        errors = []
        
        if not cls.BINANCE_API_KEY:
            errors.append("BINANCE_API_KEY is required")
        
        if not cls.BINANCE_API_SECRET:
            errors.append("BINANCE_API_SECRET is required")
        
        if cls.LEVERAGE < 1 or cls.LEVERAGE > 125:
            errors.append("LEVERAGE must be between 1 and 125")
        
        if cls.POSITION_SIZE_PCT <= 0 or cls.POSITION_SIZE_PCT > 100:
            errors.append("POSITION_SIZE_PCT must be between 0 and 100")
        
        if cls.RSI_OVERSOLD >= cls.RSI_OVERBOUGHT:
            errors.append("RSI_OVERSOLD must be less than RSI_OVERBOUGHT")
        
        return errors
    
    @classmethod
    def print_config(cls):
        """Imprimir configuración actual (sin mostrar secrets)"""
        print("=" * 50)
        print("BOT RSI TRADING - CONFIGURACIÓN")
        print("=" * 50)
        print(f"Symbol: {cls.SYMBOL}")
        print(f"Timeframe: {cls.TIMEFRAME}")
        print(f"Testnet: {cls.USE_TESTNET}")
        print(f"RSI Period: {cls.RSI_PERIOD}")
        print(f"RSI Oversold: {cls.RSI_OVERSOLD}")
        print(f"RSI Overbought: {cls.RSI_OVERBOUGHT}")
        print(f"Leverage: {cls.LEVERAGE}x")
        print(f"Position Size: {cls.POSITION_SIZE_PCT}%")
        print(f"Stop Loss: {cls.STOP_LOSS_PCT}%")
        print(f"Take Profit: {cls.TAKE_PROFIT_PCT}%")
        print(f"API Key: {'*' * 8 if cls.BINANCE_API_KEY else 'NOT SET'}")
        print("=" * 50)