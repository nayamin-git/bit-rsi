#!/bin/bash

# Script para monitorear el status completo del Bot RSI

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  BOT RSI TRADING - STATUS      ${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# 1. Estado del proceso principal
echo -e "${YELLOW}🤖 ESTADO DEL BOT:${NC}"
if sudo supervisorctl status rsi_bot | grep -q "RUNNING"; then
    echo -e "${GREEN}✅ Bot está corriendo${NC}"
    uptime_info=$(sudo supervisorctl status rsi_bot | awk '{print $4, $5}')
    echo -e "⏰ Uptime: $uptime_info"
else
    echo -e "${RED}❌ Bot NO está corriendo${NC}"
    sudo supervisorctl status rsi_bot
fi

echo ""

# 2. Información del servidor
echo -e "${YELLOW}🌐 INFORMACIÓN DEL SERVIDOR:${NC}"
echo -e "📍 IP: $(curl -s ifconfig.me 2>/dev/null || echo 'No disponible')"
echo -e "💾 Uso de memoria: $(free -h | awk 'NR==2{printf "%.1f%% (%s usado de %s)", $3*100/$2, $3, $2}')"
echo -e "💽 Espacio en disco: $(df -h . | awk 'NR==2{printf "%s usado de %s (%s disponible)", $3, $2, $4}')"
echo -e "⚡ Load average: $(uptime | awk -F'load average:' '{print $2}')"

echo ""

# 3. Logs recientes del bot
echo -e "${YELLOW}📋 ÚLTIMOS LOGS DEL BOT:${NC}"
if [ -f "/var/log/rsi_bot.out.log" ]; then
    tail -10 /var/log/rsi_bot.out.log | while read line; do
        if [[ $line == *"ERROR"* ]]; then
            echo -e "${RED}$line${NC}"
        elif [[ $line == *"LONG"* ]] || [[ $line == *"SHORT"* ]]; then
            echo -e "${GREEN}$line${NC}"
        else
            echo "$line"
        fi
    done
else
    echo -e "${RED}❌ No se encontraron logs${NC}"
fi

echo ""

# 4. Errores recientes
echo -e "${YELLOW}⚠️  ERRORES RECIENTES:${NC}"
if [ -f "/var/log/rsi_bot.err.log" ]; then
    if [ -s "/var/log/rsi_bot.err.log" ]; then
        echo -e "${RED}$(tail -5 /var/log/rsi_bot.err.log)${NC}"
    else
        echo -e "${GREEN}✅ No hay errores recientes${NC}"
    fi
else
    echo -e "${GREEN}✅ No hay archivo de errores${NC}"
fi

echo ""

# 5. Archivos de logs del bot (si existen)
echo -e "${YELLOW}📊 LOGS DEL TRADING (HOY):${NC}"
today=$(date +%Y%m%d)
log_dir="logs"

if [ -d "$log_dir" ]; then
    trades_today="$log_dir/trades_detail_$today.csv"
    market_today="$log_dir/market_data_$today.csv"
    
    if [ -f "$trades_today" ]; then
        trade_count=$(wc -l < "$trades_today")
        echo -e "📈 Trades de hoy: $((trade_count - 1)) trades" # -1 por el header
        
        # Mostrar últimos trades si hay
        if [ $trade_count -gt 1 ]; then
            echo -e "${BLUE}📝 Últimos 3 trades:${NC}"
            tail -3 "$trades_today" | while IFS=',' read -r timestamp action side price quantity rsi stop_loss take_profit reason pnl_pct pnl_usdt balance_before balance_after duration; do
                if [[ $action == "CLOSE" ]]; then
                    if (( $(echo "$pnl_pct > 0" | bc -l) )); then
                        echo -e "${GREEN}✅ $side $action: $pnl_pct% ($reason)${NC}"
                    else
                        echo -e "${RED}❌ $side $action: $pnl_pct% ($reason)${NC}"
                    fi
                fi
            done 2>/dev/null || echo "Error leyendo trades"
        fi
    else
        echo -e "📈 No hay trades registrados hoy"
    fi
    
    if [ -f "$market_today" ]; then
        data_points=$(wc -l < "$market_today")
        echo -e "📊 Puntos de datos de mercado: $((data_points - 1))"
    fi
else
    echo -e "${YELLOW}⚠️  Directorio de logs no encontrado${NC}"
fi

echo ""

# 6. Estado de la conexión a Binance
echo -e "${YELLOW}🔗 CONECTIVIDAD:${NC}"
if ping -c 1 api.binance.com &> /dev/null; then
    echo -e "${GREEN}✅ Conexión a Binance: OK${NC}"
else
    echo -e "${RED}❌ Sin conexión a Binance${NC}"
fi

# 7. Proceso webhook (si existe)
echo ""
echo -e "${YELLOW}🪝 WEBHOOK STATUS:${NC}"
if sudo supervisorctl status webhook_listener | grep -q "RUNNING"; then
    echo -e "${GREEN}✅ Webhook listener activo${NC}"
else
    echo -e "${YELLOW}⚠️  Webhook listener no está corriendo${NC}"
fi

echo ""

# 8. Información de Git
echo -e "${YELLOW}📚 VERSIÓN DEL CÓDIGO:${NC}"
if [ -d ".git" ]; then
    echo -e "🔄 Último commit: $(git log -1 --pretty=format:'%h - %s (%cr)' 2>/dev/null || echo 'No disponible')"
    echo -e "🌿 Branch actual: $(git branch --show-current 2>/dev/null || echo 'No disponible')"
    
    # Verificar si hay cambios pendientes
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Hay cambios no commitados${NC}"
    fi
    
    # Verificar si está actualizado con origin
    git fetch --dry-run 2>/dev/null || true
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse @{u} 2>/dev/null)" ]; then
        echo -e "${YELLOW}⚠️  Hay actualizaciones disponibles en GitHub${NC}"
    else
        echo -e "${GREEN}✅ Código actualizado${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No es un repositorio Git${NC}"
fi

echo ""

# 9. Comandos útiles
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  COMANDOS ÚTILES                ${NC}"
echo -e "${BLUE}================================${NC}"
echo -e "${YELLOW}🔄 Deploy manual:${NC} ./deploy.sh"
echo -e "${YELLOW}📝 Ver logs en vivo:${NC} sudo supervisorctl tail -f rsi_bot"
echo -e "${YELLOW}🛑 Parar bot:${NC} sudo supervisorctl stop rsi_bot"
echo -e "${YELLOW}▶️  Iniciar bot:${NC} sudo supervisorctl start rsi_bot"
echo -e "${YELLOW}🔄 Reiniciar bot:${NC} sudo supervisorctl restart rsi_bot"
echo -e "${YELLOW}📊 Ver todos los procesos:${NC} sudo supervisorctl status"

echo ""
echo -e "${GREEN}✨ Status check completado - $(date)${NC}"