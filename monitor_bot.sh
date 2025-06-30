#!/bin/bash

PID_FILE="bot.pid"

echo "📊 MONITOR DEL BOT RSI"
echo "====================="

# Verificar si está corriendo
if [ -f $PID_FILE ]; then
    BOT_PID=$(cat $PID_FILE)
    if ps -p $BOT_PID > /dev/null; then
        echo "✅ Bot está corriendo (PID: $BOT_PID)"
        
        # Mostrar uso de CPU y memoria
        echo "💻 Uso de recursos:"
        ps -p $BOT_PID -o pid,pcpu,pmem,etime,cmd
        
        # Mostrar últimas líneas de log
        echo ""
        echo "📝 Últimas 5 líneas de log:"
        if [ -f "logs/bot_output.log" ]; then
            tail -n 5 logs/bot_output.log
        fi
        
        # Mostrar errores recientes si existen
        if [ -f "logs/bot_error.log" ] && [ -s "logs/bot_error.log" ]; then
            echo ""
            echo "❌ Últimos errores:"
            tail -n 3 logs/bot_error.log
        fi
        
    else
        echo "❌ Bot no está corriendo (PID obsoleto: $BOT_PID)"
        rm $PID_FILE
    fi
else
    echo "❌ Bot no está corriendo (no hay archivo PID)"
fi

echo ""
echo "🔧 Comandos útiles:"
echo "   ./start_bot.sh     - Iniciar bot"
echo "   ./stop_bot.sh      - Detener bot"
echo "   ./monitor_bot.sh   - Ver este monitor"
echo "   tail -f logs/bot_output.log - Ver logs en tiempo real"
