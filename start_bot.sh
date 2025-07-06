#!/bin/bash

# Configuración
BOT_FILE="rsi_bot.py"
LOG_DIR="logs"
PID_FILE="bot.pid"

# Crear directorio de logs si no existe
mkdir -p $LOG_DIR

# Verificar si el bot ya está corriendo
if [ -f $PID_FILE ]; then
    OLD_PID=$(cat $PID_FILE)
    if ps -p $OLD_PID > /dev/null; then
        echo "❌ El bot ya está corriendo (PID: $OLD_PID)"
        echo "Para detenerlo: kill $OLD_PID"
        exit 1
    else
        echo "🧹 Limpiando PID file obsoleto"
        rm $PID_FILE
    fi
fi

# Mostrar configuración
echo "🤖 Iniciando Bot RSI..."
echo "📂 Archivo: $BOT_FILE"
echo "📝 Logs: $LOG_DIR/"
echo "⏰ Inicio: $(date)"

# Ejecutar el bot con nohup
nohup python3 -u $BOT_FILE > $LOG_DIR/bot_output.log 2> $LOG_DIR/bot_error.log &

# Guardar PID
BOT_PID=$!
echo $BOT_PID > $PID_FILE

echo "✅ Bot iniciado con PID: $BOT_PID"
echo "📊 Ver logs: tail -f $LOG_DIR/bot_output.log"
echo "❌ Ver errores: tail -f $LOG_DIR/bot_error.log"
echo "🛑 Detener bot: kill $BOT_PID"
echo "📋 Estado: ps -p $BOT_PID"