import logging
import signal
import os
from datetime import datetime


class LoggingManager:
    """
    Gestor de logging y manejo de señales del sistema
    """

    def __init__(self, logs_dir, close_callback=None, save_state_callback=None, log_summary_callback=None):
        """
        Args:
            logs_dir: Directorio donde se guardarán los logs
            close_callback: Función callback para cerrar posiciones
            save_state_callback: Función callback para guardar estado
            log_summary_callback: Función callback para registrar resumen de performance
        """
        self.logs_dir = logs_dir
        self.close_callback = close_callback
        self.save_state_callback = save_state_callback
        self.log_summary_callback = log_summary_callback
        self.logger = None
        self.in_position_callback = None

    def set_in_position_callback(self, callback):
        """Establece callback para verificar si hay posición abierta"""
        self.in_position_callback = callback

    def setup_logging(self):
        """Configura sistema de logging (compatible con Docker)"""
        os.makedirs(self.logs_dir, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        log_file = os.path.join(self.logs_dir, f'rsi_ema_bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.logger.info(f"🐳 RSI+EMA+Trend Bot iniciando - Logs en: {log_file}")

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        return self.logger

    def _signal_handler(self, signum, frame):
        """Maneja señales de Docker (SIGTERM, SIGINT)"""
        signal_names = {2: 'SIGINT', 15: 'SIGTERM'}
        signal_name = signal_names.get(signum, f'Signal {signum}')

        self.logger.info(f"🐳 Recibida señal {signal_name} - Cerrando bot gracefully...")

        # Verificar si hay posición abierta usando el callback
        in_position = self.in_position_callback() if self.in_position_callback else False

        if in_position and self.close_callback:
            self.logger.info("💾 Cerrando posición antes de salir...")
            self.close_callback("Señal Docker")

        if self.save_state_callback:
            self.save_state_callback()

        if self.log_summary_callback:
            self.log_summary_callback()

        self.logger.info("🐳 Bot cerrado correctamente")
        exit(0)
