# Dockerfile para Bot RSI Trading
# Permite ejecutar el bot en contenedores Docker

FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad
RUN useradd --create-home --shell /bin/bash botuser

# Configurar directorio de trabajo
WORKDIR /app

# Copiar requirements primero para aprovechar cache de Docker
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del bot
COPY . .

# Crear directorio de logs
RUN mkdir -p logs && chown -R botuser:botuser /app

# Cambiar a usuario no-root
USER botuser

# Comando por defecto
CMD ["python", "rsi_bot.py"]

# Metadata
LABEL maintainer="tu-email@ejemplo.com"
LABEL description="Bot RSI Trading para Binance"
LABEL version="1.0"