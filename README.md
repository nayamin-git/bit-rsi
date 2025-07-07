# ========================================
# Instrucciones de uso
# ========================================

# SETUP INICIAL:
# 1. Crea la estructura de directorios:
mkdir rsi-bot-docker
cd rsi-bot-docker

# 2. Crea los archivos necesarios:
# - Dockerfile
# - docker-compose.yml  
# - requirements.txt
# - rsi_bot.py (tu código Python)
# - .env (desde .env.example)
# - Makefile (opcional pero recomendado)

# 3. Configura tus credenciales en .env:
cp .env.example .env
# Edita .env con tus credenciales reales

# COMANDOS PRINCIPALES:

# Construir la imagen:
make build
# O: docker-compose build

# Iniciar el bot:
make up
# O: docker-compose up -d

# Ver logs en tiempo real:
make logs
# O: docker-compose logs -f rsi-bot

# Detener el bot:
make down
# O: docker-compose down

# Reiniciar el bot:
make restart
# O: docker-compose restart

# Ver estado:
make status
# O: docker-compose ps

# Crear backup:
make backup

# Limpiar todo:
make clean

# ESTRUCTURA DE DIRECTORIOS FINAL:
rsi-bot-docker/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── rsi_bot.py
├── .env
├── .env.example
├── Makefile
├── .dockerignore
├── logs/           # ← Persistente (volumen)
├── data/           # ← Persistente (volumen) 
└── backups/        # ← Backups automáticos