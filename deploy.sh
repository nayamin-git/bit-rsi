#!/bin/bash

# Script de deploy automático para Bot RSI
# Se ejecuta automáticamente cuando haces push a GitHub

set -e  # Salir si hay error

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔄 Iniciando deploy del Bot RSI...${NC}"

# Obtener directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

# Backup de la versión actual
echo -e "${YELLOW}📦 Creando backup...${NC}"
if [ -f "rsi_bot.py" ]; then
    cp rsi_bot.py "rsi_bot.py.backup.$(date +%s)" 2>/dev/null || true
fi

# Mostrar estado actual antes del deploy
echo -e "${YELLOW}📊 Estado actual del bot:${NC}"
sudo supervisorctl status rsi_bot || echo "Bot no está corriendo"

# Pull de GitHub
echo -e "${YELLOW}📥 Descargando cambios de GitHub...${NC}"
git fetch origin
git reset --hard origin/main

# Verificar si hay cambios en requirements.txt
echo -e "${YELLOW}🔍 Verificando dependencias...${NC}"
if [ -f "requirements.txt" ]; then
    if [ ! -f "venv/pyvenv.cfg" ] || [ requirements.txt -nt venv/pyvenv.cfg ]; then
        echo -e "${YELLOW}📦 Actualizando dependencias Python...${NC}"
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        # Actualizar timestamp del venv
        touch venv/pyvenv.cfg
    else
        echo -e "${GREEN}✅ Dependencias actualizadas${NC}"
    fi
fi

# Verificar que el archivo principal existe
if [ ! -f "rsi_bot.py" ]; then
    echo -e "${RED}❌ Error: rsi_bot.py no encontrado${NC}"
    exit 1
fi

# Verificar configuración
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Error: Archivo .env no encontrado${NC}"
    echo -e "${YELLOW}💡 Copia .env.example a .env y configura tus API keys${NC}"
    exit 1
fi

# Verificar sintaxis de Python
echo -e "${YELLOW}🔍 Verificando sintaxis del código...${NC}"
if ! python3 -m py_compile rsi_bot.py; then
    echo -e "${RED}❌ Error de sintaxis en rsi_bot.py${NC}"
    exit 1
fi

# Parar el bot actual
echo -e "${YELLOW}🛑 Deteniendo bot actual...${NC}"
sudo supervisorctl stop rsi_bot || echo "Bot ya estaba detenido"

# Pequeña pausa para asegurar que se detuvo
sleep 2

# Reiniciar el bot
echo -e "${YELLOW}🚀 Iniciando bot actualizado...${NC}"
sudo supervisorctl start rsi_bot

# Verificar que inició correctamente
sleep 3
if sudo supervisorctl status rsi_bot | grep -q "RUNNING"; then
    echo -e "${GREEN}✅ Bot iniciado correctamente${NC}"
else
    echo -e "${RED}❌ Error al iniciar el bot${NC}"
    echo -e "${YELLOW}📋 Últimas líneas del log de error:${NC}"
    sudo tail -10 /var/log/rsi_bot.err.log || echo "No hay log de errores"
    exit 1
fi

# Mostrar información del deploy
echo -e "${GREEN}=== DEPLOY COMPLETADO ===${NC}"
echo -e "🕐 Timestamp: $(date)"
echo -e "🔄 Commit: $(git rev-parse --short HEAD)"
echo -e "📝 Mensaje: $(git log -1 --pretty=%B)"
echo -e "👤 Autor: $(git log -1 --pretty=format:'%an <%ae>')"

# Mostrar status del bot
echo ""
echo -e "${YELLOW}📊 Status actual del bot:${NC}"
sudo supervisorctl status rsi_bot

# Mostrar últimas líneas del log
echo ""
echo -e "${YELLOW}📋 Últimas 5 líneas del log:${NC}"
sudo tail -5 /var/log/rsi_bot.out.log || echo "No hay logs disponibles"

# Log del deploy
echo "$(date): Deploy completado - Commit: $(git rev-parse --short HEAD)" >> deploy.log

echo -e "${GREEN}🎉 ¡Deploy completado exitosamente!${NC}"