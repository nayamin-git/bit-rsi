.PHONY: build up down logs restart clean backup restore

# Variables
COMPOSE_FILE = docker-compose.yml
SERVICE_NAME = rsi-bot

# Comandos principales
build:
	@echo "🔨 Construyendo imagen Docker..."
	docker-compose -f $(COMPOSE_FILE) build

up:
	@echo "🚀 Iniciando bot..."
	docker-compose -f $(COMPOSE_FILE) up -d

down:
	@echo "🛑 Deteniendo bot..."
	docker-compose -f $(COMPOSE_FILE) down

restart:
	@echo "🔄 Reiniciando bot..."
	docker-compose -f $(COMPOSE_FILE) restart

logs:
	@echo "📋 Mostrando logs..."
	docker-compose -f $(COMPOSE_FILE) logs -f $(SERVICE_NAME)

logs-tail:
	@echo "📋 Mostrando últimos logs..."
	docker-compose -f $(COMPOSE_FILE) logs --tail=100 -f $(SERVICE_NAME)

status:
	@echo "📊 Estado del bot..."
	docker-compose -f $(COMPOSE_FILE) ps

clean:
	@echo "🧹 Limpiando contenedores e imágenes..."
	docker-compose -f $(COMPOSE_FILE) down -v
	docker system prune -f

backup:
	@echo "💾 Creando backup de logs y datos..."
	@mkdir -p backups
	@tar -czf backups/bot-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz logs data .env
	@echo "✅ Backup creado en backups/"

restore:
	@echo "📥 Para restaurar un backup:"
	@echo "tar -xzf backups/BACKUP_FILE.tar.gz"

shell:
	@echo "🐚 Accediendo al contenedor..."
	docker-compose -f $(COMPOSE_FILE) exec $(SERVICE_NAME) /bin/bash

# Comandos de desarrollo
dev-build:
	@echo "🔨 Build para desarrollo..."
	docker-compose -f $(COMPOSE_FILE) build --no-cache

dev-up:
	@echo "🚀 Iniciando en modo desarrollo..."
	docker-compose -f $(COMPOSE_FILE) up

# Comandos de monitoreo
monitor:
	@echo "📊 Monitoreando recursos..."
	docker stats $(shell docker-compose -f $(COMPOSE_FILE) ps -q)

health:
	@echo "🏥 Verificando salud del contenedor..."
	docker-compose -f $(COMPOSE_FILE) ps
	@echo ""
	@docker inspect --format='{{.State.Health.Status}}' rsi-trading-bot
