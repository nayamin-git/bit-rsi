#!/bin/bash

PID_FILE="bot.pid"

if [ ! -f $PID_FILE ]; then
    echo "❌ No se encontró archivo PID. El bot no parece estar corriendo."
    exit 1
fi

BOT_PID=$(cat $PID_FILE)

if ps -p $BOT_PID > /dev/null; then
    echo "🛑 Deteniendo bot (PID: $BOT_PID)..."
    kill $BOT_PID
    
    # Esperar 5 segundos para shutdown graceful
    sleep 5
    
    # Verificar si aún está corriendo
    if ps -p $BOT_PID > /dev/null; then
        echo "⚡ Forzando parada del bot..."
        kill -9 $BOT_PID
    fi
    
    rm $PID_FILE
    echo "✅ Bot detenido exitosamente"
else
    echo "❌ El proceso $BOT_PID no está corriendo"
    rm $PID_FILE
fi