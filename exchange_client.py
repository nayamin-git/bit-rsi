import ccxt


class ExchangeClient:
    """
    Cliente de exchange - Gestiona la conexión con Binance via CCXT
    """

    def __init__(self, api_key, api_secret, config, logger):
        """
        Args:
            api_key: API key de Binance
            api_secret: API secret de Binance
            config: Configuración del bot
            logger: Logger para registrar información
        """
        self.config = config
        self.logger = logger

        # Configurar exchange con CCXT
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': config.testnet,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            }
        })

    def verify_connection(self):
        """Verifica la conexión con Binance"""
        try:
            self.exchange.load_markets()

            if self.config.symbol not in self.exchange.markets:
                available_symbols = [s for s in self.exchange.markets.keys() if 'BTC' in s and 'USDT' in s]
                self.logger.warning(f"Símbolo {self.config.symbol} no encontrado. Disponibles: {available_symbols[:5]}")

            balance = self.exchange.fetch_balance()
            self.logger.info(f"✅ Conexión exitosa con Binance {'Testnet' if self.config.testnet else 'Mainnet'}")

            usdt_balance = balance.get('USDT', {}).get('free', 0)
            self.logger.info(f"💰 Balance USDT disponible: ${usdt_balance:.2f}")

        except Exception as e:
            self.logger.error(f"❌ Error de conexión: {e}")
            raise
