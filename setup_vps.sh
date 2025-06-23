#!/bin/bash

# Script de configuración automática VPS para Bot RSI Trading
# Ejecutar como: bash setup_vps.sh

set -e  # Salir si hay algún error

echo "🚀 Iniciando configuración del VPS para Bot RSI..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables de configuración
BOT_USER="botuser"
BOT_DIR="/home/$BOT_USER/rsi-trading-bot"
GITHUB_REPO="https://github.com/TU_USUARIO/tu-bot-rsi.git"  # Cambiar por tu repo

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 1. Actualizar sistema
print_status "Actualizando sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependencias básicas
print_status "Instalando dependencias..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    screen \
    supervisor \
    nginx \
    fail2ban \
    ufw \
    htop \
    curl \
    wget \
    unzip

# 3. Configurar firewall básico
print_status "Configurando firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# 4. Crear usuario para el bot (más seguro)
print_status "Creando usuario para el bot..."
if ! id "$BOT_USER" &>/dev/null; then
    sudo adduser --disabled-password --gecos "" $BOT_USER
    sudo usermod -aG sudo $BOT_USER
fi

# 5. Configurar Git (requerirá input del usuario)
print_warning "Configurando Git..."
echo -e "${BLUE}Ingresa tu nombre para Git:${NC}"
read -p "Nombre: " git_name
echo -e "${BLUE}Ingresa tu email de GitHub:${NC}"
read -p "Email: " git_email

sudo -u $BOT_USER git config --global user.name "$git_name"
sudo -u $BOT_USER git config --global user.email "$git_email"

# 6. Generar SSH key para GitHub (opcional pero recomendado)
print_status "Generando SSH key para GitHub..."
sudo -u $BOT_USER ssh-keygen -t ed25519 -C "$git_email" -f /home/$BOT_USER/.ssh/id_ed25519 -N ""

print_warning "Tu SSH key pública es:"
echo -e "${YELLOW}$(sudo cat /home/$BOT_USER/.ssh/id_ed25519.pub)${NC}"
echo ""
print_warning "Copia esta key y agrégala a tu GitHub en: Settings > SSH and GPG keys"
echo -e "${BLUE}Presiona Enter cuando hayas agregado la key a GitHub...${NC}"
read

# 7. Clonar repositorio
print_status "Clonando repositorio..."
echo -e "${BLUE}Ingresa la URL de tu repositorio GitHub:${NC}"
read -p "GitHub repo URL: " repo_url

sudo -u $BOT_USER mkdir -p $(dirname $BOT_DIR)
sudo -u $BOT_USER git clone $repo_url $BOT_DIR

# 8. Crear entorno virtual y instalar dependencias
print_status "Configurando entorno Python..."
cd $BOT_DIR
sudo -u $BOT_USER python3 -m venv venv
sudo -u $BOT_USER /bin/bash -c "source venv/bin/activate && pip install --upgrade pip"

# Instalar dependencias si existe requirements.txt
if [ -f "requirements.txt" ]; then
    sudo -u $BOT_USER /bin/bash -c "source venv/bin/activate && pip install -r requirements.txt"
else
    print_warning "No se encontró requirements.txt, instalando dependencias básicas..."
    sudo -u $BOT_USER /bin/bash -c "source venv/bin/activate && pip install ccxt pandas numpy python-dotenv"
fi

# 9. Configurar variables de entorno
print_status "Configurando variables de entorno..."
echo -e "${BLUE}Configuración de API Keys de Binance:${NC}"
read -p "Binance API Key: " binance_key
read -s -p "Binance API Secret: " binance_secret
echo ""
read -p "¿Usar testnet? (true/false): " use_testnet

sudo -u $BOT_USER tee $BOT_DIR/.env << EOF
BINANCE_API_KEY=$binance_key
BINANCE_API_SECRET=$binance_secret
USE_TESTNET=$use_testnet
EOF

# Asegurar permisos del archivo .env
sudo chmod 600 $BOT_DIR/.env
sudo chown $BOT_USER:$BOT_USER $BOT_DIR/.env

# 10. Configurar Supervisor para auto-restart
print_status "Configurando supervisor para auto-restart..."
sudo tee /etc/supervisor/conf.d/rsi_bot.conf << EOF
[program:rsi_bot]
command=$BOT_DIR/venv/bin/python $BOT_DIR/rsi_bot.py
directory=$BOT_DIR
user=$BOT_USER
autostart=true
autorestart=true
stderr_logfile=/var/log/rsi_bot.err.log
stdout_logfile=/var/log/rsi_bot.out.log
environment=PATH="$BOT_DIR/venv/bin"
EOF

# 11. Crear script de deploy automático
print_status "Creando script de deploy automático..."
sudo -u $BOT_USER tee $BOT_DIR/deploy.sh << 'EOF'
#!/bin/bash
# Script de deploy automático

echo "🔄 Iniciando deploy..."

# Ir al directorio del bot
cd $(dirname "$0")

# Backup de la versión actual
cp rsi_bot.py rsi_bot.py.backup.$(date +%s) 2>/dev/null || true

# Pull de GitHub
git pull origin main

# Actualizar dependencias si es necesario
if [ requirements.txt -nt venv/pyvenv.cfg ]; then
    echo "📦 Actualizando dependencias..."
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Reiniciar el bot
echo "🔄 Reiniciando bot..."
sudo supervisorctl restart rsi_bot

echo "✅ Deploy completado!"

# Mostrar status
sleep 2
sudo supervisorctl status rsi_bot
EOF

sudo chmod +x $BOT_DIR/deploy.sh

# 12. Configurar webhook de GitHub (opcional)
print_status "Configurando webhook endpoint..."
sudo tee /etc/nginx/sites-available/bot_webhook << EOF
server {
    listen 80;
    server_name _;
    
    location /webhook {
        proxy_pass http://localhost:9000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    
    location /status {
        return 200 "Bot Status: OK";
        add_header Content-Type text/plain;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/bot_webhook /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 13. Instalar webhook listener (Python simple)
sudo -u $BOT_USER tee $BOT_DIR/webhook_listener.py << 'EOF'
#!/usr/bin/env python3
import http.server
import socketserver
import subprocess
import json
import hmac
import hashlib
import os

PORT = 9000
SECRET = os.getenv('WEBHOOK_SECRET', 'your_secret_here')

class WebhookHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/webhook':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Verificar signature (opcional)
            signature = self.headers.get('X-Hub-Signature-256')
            if signature:
                expected = 'sha256=' + hmac.new(
                    SECRET.encode(), post_data, hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    self.send_response(401)
                    self.end_headers()
                    return
            
            # Ejecutar deploy
            try:
                result = subprocess.run(['./deploy.sh'], 
                                      cwd=os.path.dirname(__file__),
                                      capture_output=True, text=True)
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Deploy result: {result.returncode}\n{result.stdout}".encode())
                
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode())
        else:
            self.send_response(404)
            self.end_headers()

with socketserver.TCPServer(("", PORT), WebhookHandler) as httpd:
    print(f"Webhook listener running on port {PORT}")
    httpd.serve_forever()
EOF

sudo chmod +x $BOT_DIR/webhook_listener.py

# 14. Configurar supervisor para webhook
sudo tee /etc/supervisor/conf.d/webhook_listener.conf << EOF
[program:webhook_listener]
command=$BOT_DIR/venv/bin/python $BOT_DIR/webhook_listener.py
directory=$BOT_DIR
user=$BOT_USER
autostart=true
autorestart=true
stderr_logfile=/var/log/webhook.err.log
stdout_logfile=/var/log/webhook.out.log
environment=PATH="$BOT_DIR/venv/bin"
EOF

# 15. Recargar supervisor y iniciar servicios
print_status "Iniciando servicios..."
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start rsi_bot
sudo supervisorctl start webhook_listener

# 16. Crear scripts de gestión útiles
sudo -u $BOT_USER tee $BOT_DIR/bot_status.sh << 'EOF'
#!/bin/bash
echo "=== STATUS DEL BOT RSI ==="
echo ""
echo "🤖 Estado del proceso:"
sudo supervisorctl status rsi_bot

echo ""
echo "📊 Últimas 20 líneas del log:"
tail -20 /var/log/rsi_bot.out.log

echo ""
echo "💰 Balance actual:"
# Aquí podrías agregar un comando para verificar balance
echo ""
echo "📈 Logs de trades del día:"
find logs/ -name "*$(date +%Y%m%d)*" -exec echo "Archivo: {}" \; -exec tail -5 {} \; 2>/dev/null || echo "No hay logs de hoy"
EOF

sudo chmod +x $BOT_DIR/bot_status.sh

# 17. Información final
print_status "¡Configuración completada!"
echo ""
echo -e "${GREEN}=== INFORMACIÓN DEL SERVIDOR ===${NC}"
echo -e "🌐 IP del servidor: ${YELLOW}$(curl -s ifconfig.me)${NC}"
echo -e "📁 Directorio del bot: ${YELLOW}$BOT_DIR${NC}"
echo -e "👤 Usuario del bot: ${YELLOW}$BOT_USER${NC}"
echo ""
echo -e "${GREEN}=== COMANDOS ÚTILES ===${NC}"
echo -e "📊 Ver status: ${YELLOW}cd $BOT_DIR && ./bot_status.sh${NC}"
echo -e "🔄 Deploy manual: ${YELLOW}cd $BOT_DIR && ./deploy.sh${NC}"
echo -e "📝 Ver logs: ${YELLOW}sudo supervisorctl tail -f rsi_bot${NC}"
echo -e "🛑 Parar bot: ${YELLOW}sudo supervisorctl stop rsi_bot${NC}"
echo -e "▶️  Iniciar bot: ${YELLOW}sudo supervisorctl start rsi_bot${NC}"
echo ""
echo -e "${GREEN}=== CONFIGURAR WEBHOOK EN GITHUB ===${NC}"
echo -e "URL del webhook: ${YELLOW}http://$(curl -s ifconfig.me)/webhook${NC}"
echo -e "Content type: ${YELLOW}application/json${NC}"
echo -e "Events: ${YELLOW}Just the push event${NC}"
echo ""
echo -e "${YELLOW}¡Tu bot ya está corriendo! 🎉${NC}"

# Mostrar status final
sleep 2
sudo supervisorctl status