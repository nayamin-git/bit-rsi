# ========================================
# Dockerfile
# ========================================
FROM python:3.11-slim

# Configurar variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=UTC

# Crear usuario no-root para seguridad
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Crear directorios de trabajo
WORKDIR /app
RUN mkdir -p /app/logs /app/data && \
    chown -R botuser:botuser /app

# Copiar requirements.txt primero (para cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Cambiar ownership de todos los archivos
RUN chown -R botuser:botuser /app

# Cambiar al usuario no-root
USER botuser

# Comando por defecto
CMD ["python", "rsi_bot.py"]