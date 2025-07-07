#!/bin/bash
set -e

echo "🤖 Iniciando RSI Trading Bot en Docker..."
echo "📅 Fecha: $(date)"
echo "🌍 Timezone: $TZ"

# Verificar que existen las credenciales
if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_API_SECRET" ]]; then
    echo "❌ ERROR: Variables de entorno BINANCE_API_KEY y BINANCE_API_SECRET son requeridas"
    exit 1
fi

# Crear directorios si no existen
mkdir -p /app/logs /app/data

# Función para manejo graceful de señales
cleanup() {
    echo "🛑 Recibida señal de parada..."
    echo "💾 Guardando estado del bot..."
    # El bot Python maneja su propio cleanup
    exit 0
}

# Configurar traps para señales
trap cleanup SIGTERM SIGINT

echo "✅ Configuración validada"
echo "🚀 Ejecutando bot..."

# Ejecutar el bot
exec python rsi_bot.py
