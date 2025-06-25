#!/bin/bash

# =============================================================================
# 🚀 SETUP VPS PARA BOT RSI TRADING - Version con venv mejorada
# =============================================================================

set -e  # Salir si hay errores

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] ℹ️  $1${NC}"
}

# Verificar que se ejecuta como root
if [[ $EUID -ne 0 ]]; then
   error "Este script debe ejecutarse como root"
   exit 1
fi

log "🤖 Iniciando configuración del VPS para Bot RSI Trading"

# =============================================================================
# 1. ACTUALIZAR SISTEMA
# =============================================================================
log "📦 Actualizando sistema..."
apt update && apt upgrade -y

# =============================================================================
# 2. INSTALAR DEPENDENCIAS DEL SISTEMA
# =============================================================================
log "🛠️ Instalando dependencias del sistema..."
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    build-essential \
    libssl-dev \
    libffi-dev \
    git \
    screen \
    supervisor \
    nginx \
    ufw \
    curl \
    wget \
    htop \
    vim \
    unzip

# =============================================================================
# 3. CONFIGURAR FIREWALL
# =============================================================================
log "🔥 Configurando firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80
ufw allow 443
ufw --force enable

# =============================================================================
# 4. CREAR USUARIO PARA EL BOT
# =============================================================================
log "👤 Configurando usuario del bot..."

# Preguntar por nombre del repositorio
read -p "📂 Nombre de tu repositorio en GitHub (ej: rsi-trading-bot): " REPO_NAME
read -p "👨‍💻 Tu usuario de GitHub: " GITHUB_USER

# Crear usuario si no existe
if ! id "botuser" &>/dev/null; then
    adduser --disabled-password --gecos "" botuser
    usermod -aG sudo botuser
    log "✅ Usuario 'botuser' creado"
else
    log "ℹ️ Usuario 'botuser' ya existe"
fi

# =============================================================================
# 5. CONFIGURAR GIT GLOBAL
# =============================================================================
log "🔧 Configurando Git..."
read -p "📧 Tu email para Git: " GIT_EMAIL
read -p "👤 Tu nombre para Git: " GIT_NAME

git config --global user.name "$GIT_NAME"
git config --global user.email "$GIT_EMAIL"

# =============================================================================
# 6. CONFIGURAR PROYECTO COMO BOTUSER
# =============================================================================
log "🐍 Configurando proyecto y entorno virtual..."

# Script para ejecutar como botuser
cat > /tmp/setup_bot_user.sh << EOF
#!/bin/bash

set -e

# Función para logging como botuser
log_user() {
    echo -e "\033[0;32m[botuser] \$1\033[0m"
}

error_user() {
    echo -e "\033[0;31m[botuser] ❌ \$1\033[0m"
}

cd /home/botuser

log_user "📥 Clonando repositorio..."
if [ -d "$REPO_NAME" ]; then
    log_user "📁 Directorio existe, actualizando..."
    cd $REPO_NAME
    git pull
else
    git clone https://github.com/$GITHUB_USER/$REPO_NAME.git
    cd $REPO_NAME
fi

log_user "🗑️ Limpiando entorno virtual anterior si existe..."
rm -rf venv

log_user "🐍 Creando nuevo entorno virtual con venv..."
python3 -m venv venv

log_user "⚡ Activando entorno virtual..."
source venv/bin/activate

log_user "📈 Actualizando pip..."
pip install --upgrade pip

log_user "🛠️ Instalando herramientas base..."
pip install setuptools wheel

log_user "📚 Creando requirements.txt si no existe..."
if [ ! -f requirements.txt ]; then
    cat > requirements.txt << 'REQS'
ccxt>=4.0.0
pandas>=2.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
flask>=2.3.0
requests>=2.31.0
REQS
fi

log_user "📦 Instalando dependencias del proyecto..."
pip install -r requirements.txt

log_user "✅ Verificando instalación..."
python -c "import ccxt; print('✅ CCXT OK')" || error_user "Error con CCXT"
python -c "import pandas; print('✅ Pandas OK')" || error_user "Error con Pandas"
python -c "import numpy; print('✅ Numpy OK')" || error_user "Error con Numpy"
python -c "import flask; print('✅ Flask OK')" || error_user "Error con Flask"

log_user "📝 Configurando archivo .env..."
if [ ! -f .env ]; then
    cat > .env << 'ENVFILE'
# Configuración del Bot RSI Trading
BINANCE_API_KEY=tu_testnet_api_key_aqui
BINANCE_API_SECRET=tu_testnet_secret_aqui
USE_TESTNET=true

# Configuración de trading
SYMBOL=BTC/USDT
TIMEFRAME=5m
RSI_PERIOD=14
RSI_OVERSOLD=25
RSI_OVERBOUGHT=75

# Gestión de riesgo
LEVERAGE=10
POSITION_SIZE_PCT=5
STOP_LOSS_PCT=3
TAKE_PROFIT_PCT=6

# Configuración del webhook
WEBHOOK_SECRET=tu_webhook_secret_aqui
WEBHOOK_PORT=9000

# Configuración de logs
LOG_LEVEL=INFO
ENVFILE
    
    log_user "⚠️ IMPORTANTE: Edita el archivo .env con tus API keys reales"
    log_user "📝 Comando: nano /home/botuser/$REPO_NAME/.env"
fi

log_user "🔧 Haciendo scripts ejecutables..."
chmod +x *.sh 2>/dev/null || true

log_user "✅ Configuración del usuario completada"
EOF

# Ejecutar como botuser
chmod +x /tmp/setup_bot_user.sh
sudo -u botuser bash /tmp/setup_bot_user.sh
rm /tmp/setup_bot_user.sh

# =============================================================================
# 7. CONFIGURAR SUPERVISOR
# =============================================================================
log "👮 Configurando Supervisor..."

# Configuración para el bot principal
cat > /etc/supervisor/conf.d/rsi_bot.conf << EOF
[program:rsi_bot]
command=/home/botuser/$REPO_NAME/venv/bin/python /home/botuser/$REPO_NAME/rsi_bot.py
directory=/home/botuser/$REPO_NAME
user=botuser
autostart=true
autorestart=true
stderr_logfile=/var/log/rsi_bot.err.log
stdout_logfile=/var/log/rsi_bot.out.log
environment=PATH="/home/botuser/$REPO_NAME/venv/bin"
redirect_stderr=true
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=3
EOF

# Configuración para el webhook listener
cat > /etc/supervisor/conf.d/webhook_listener.conf << EOF
[program:webhook_listener]
command=/home/botuser/$REPO_NAME/venv/bin/python /home/botuser/$REPO_NAME/webhook_listener.py
directory=/home/botuser/$REPO_NAME
user=botuser
autostart=true
autorestart=true
stderr_logfile=/var/log/webhook.err.log
stdout_logfile=/var/log/webhook.out.log
environment=PATH="/home/botuser/$REPO_NAME/venv/bin"
redirect_stderr=true
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=3
EOF

# =============================================================================
# 8. CONFIGURAR NGINX
# =============================================================================
log "🌐 Configurando Nginx..."

cat > /etc/nginx/sites-available/bot_webhook << EOF
server {
    listen 80;
    server_name _;
    
    # Webhook endpoint
    location /webhook {
        proxy_pass http://localhost:9000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Status endpoint
    location /status {
        return 200 "Bot RSI Trading - Status: OK\\nTimestamp: \$time_iso8601";
        add_header Content-Type text/plain;
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }
    
    # Logs endpoint (básico)
    location /logs {
        return 200 "Use SSH para ver logs: supervisorctl tail -f rsi_bot";
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/bot_webhook /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx

# =============================================================================
# 9. CONFIGURAR SERVICIOS Y LOGS
# =============================================================================
log "📊 Configurando servicios..."

# Crear directorio de logs si no existe
mkdir -p /var/log/trading_bot
chown botuser:botuser /var/log/trading_bot

# Recargar supervisor
supervisorctl reread
supervisorctl update

# =============================================================================
# 10. CREAR SCRIPTS ÚTILES
# =============================================================================
log "📝 Creando scripts útiles..."

# Script de status del bot
cat > /home/botuser/bot_status.sh << 'EOF'
#!/bin/bash

echo "🤖 === STATUS DEL BOT RSI TRADING ==="
echo ""

echo "📊 Status Supervisor:"
sudo supervisorctl status

echo ""
echo "🔍 Últimas líneas del log:"
sudo supervisorctl tail rsi_bot

echo ""
echo "💾 Uso de memoria:"
ps aux | grep python | grep -v grep

echo ""
echo "🌐 Status de red:"
netstat -tlnp | grep :9000

echo ""
echo "📈 Archivos de log disponibles:"
ls -la /var/log/ | grep -E "(rsi_bot|webhook)"
EOF

# Script de deploy manual
cat > /home/botuser/deploy.sh << 'EOF'
#!/bin/bash

echo "🚀 Iniciando deploy..."

cd /home/botuser/REPO_NAME_PLACEHOLDER

# Pull latest changes
git pull

# Activate venv and update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart services
sudo supervisorctl restart rsi_bot
sudo supervisorctl restart webhook_listener

echo "✅ Deploy completado"
EOF

# Reemplazar placeholder
sed -i "s/REPO_NAME_PLACEHOLDER/$REPO_NAME/g" /home/botuser/deploy.sh

# Hacer scripts ejecutables
chown botuser:botuser /home/botuser/*.sh
chmod +x /home/botuser/*.sh

# =============================================================================
# 11. MOSTRAR INFORMACIÓN FINAL
# =============================================================================
SERVER_IP=$(curl -s ifconfig.me)

log "🎉 ¡Configuración completada!"
echo ""
echo "=============================================="
echo "📋 INFORMACIÓN IMPORTANTE:"
echo "=============================================="
echo "🌐 IP del servidor: $SERVER_IP"
echo "👤 Usuario del bot: botuser"
echo "📁 Directorio: /home/botuser/$REPO_NAME"
echo "🔗 Webhook URL: http://$SERVER_IP/webhook"
echo "📊 Status URL: http://$SERVER_IP/status"
echo ""
echo "🔧 PRÓXIMOS PASOS:"
echo "1. Editar archivo .env con tus API keys:"
echo "   sudo su - botuser"
echo "   cd $REPO_NAME"
echo "   nano .env"
echo ""
echo "2. Configurar webhook en GitHub:"
echo "   - Ir a: Settings > Webhooks > Add webhook"
echo "   - URL: http://$SERVER_IP/webhook"
echo "   - Content type: application/json"
echo "   - Events: Just the push event"
echo ""
echo "3. Verificar que todo funciona:"
echo "   sudo supervisorctl status"
echo "   curl http://$SERVER_IP/status"
echo ""
echo "📚 COMANDOS ÚTILES:"
echo "   ./bot_status.sh      - Ver status del bot"
echo "   ./deploy.sh          - Deploy manual"
echo "   sudo supervisorctl tail -f rsi_bot  - Ver logs"
echo ""
warn "⚠️ RECUERDA: Configura tus API keys antes de iniciar el trading!"
echo "=============================================="