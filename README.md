# Bot RSI Trading para Binance

Bot de trading automatizado que utiliza el indicador RSI (Relative Strength Index) para operar Bitcoin en Binance con estrategia agresiva.

## 🚀 Características

- **Estrategia RSI agresiva**: Señales en RSI < 25 (oversold) y RSI > 75 (overbought)
- **Trading con apalancamiento**: Hasta 10x leverage configurable
- **Gestión de riesgo**: Stop loss y take profit automáticos
- **Logs detallados**: Tracking completo de trades y performance
- **Auto-restart**: Reinicio automático en caso de errores
- **Deploy automático**: Integración con GitHub para updates

## 📊 Configuración de Trading

| Parámetro | Valor por defecto | Descripción |
|-----------|-------------------|-------------|
| RSI Oversold | 25 | Señal de compra (LONG) |
| RSI Overbought | 75 | Señal de venta (SHORT) |
| Timeframe | 5m | Análisis cada 5 minutos |
| Leverage | 10x | Apalancamiento |
| Position Size | 5% | Porcentaje del capital por trade |
| Stop Loss | 3% | Pérdida máxima por trade |
| Take Profit | 6% | Ganancia objetivo por trade |

## 🛠️ Instalación Local

### Prerrequisitos

- Python 3.8+
- Cuenta en Binance con API keys
- Git

### Pasos

1. **Clonar repositorio**
```bash
git clone https://github.com/tu-usuario/tu-bot-rsi.git
cd tu-bot-rsi
```

2. **Crear entorno virtual**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
# Editar .env con tus API keys de Binance
```

5. **Ejecutar bot**
```bash
python rsi_bot.py
```

## ☁️ Deploy en VPS

### Configuración automática

1. **Crear VPS** (recomendado: DigitalOcean $5/mes)

2. **Ejecutar script de setup**
```bash
wget https://raw.githubusercontent.com/tu-usuario/tu-bot-rsi/main/setup_vps.sh
chmod +x setup_vps.sh
sudo bash setup_vps.sh
```

3. **Configurar webhook en GitHub**
   - Ir a tu repo > Settings > Webhooks
   - Add webhook: `http://TU_IP_VPS/webhook`
   - Content type: `application/json`
   - Events: `Just the push event`

### Comandos útiles en VPS

```bash
# Ver status del bot
./bot_status.sh

# Deploy manual
./deploy.sh

# Ver logs en tiempo real
sudo supervisorctl tail -f rsi_bot

# Parar/iniciar bot
sudo supervisorctl stop rsi_bot
sudo supervisorctl start rsi_bot
```

## 📈 Logs y Monitoreo

El bot genera varios tipos de logs para análisis:

### Archivos de log
- `logs/rsi_bot_YYYYMMDD.log` - Log general del bot
- `logs/trades_YYYYMMDD.log` - Log específico de trades
- `logs/trades_detail_YYYYMMDD.csv` - Datos detallados de trades
- `logs/market_data_YYYYMMDD.csv` - Datos de mercado y RSI
- `logs/performance_YYYYMMDD.csv` - Métricas de rendimiento

### Métricas disponibles
- Win rate (porcentaje de trades ganadores)
- Profit factor
- Drawdown máximo
- Sharpe ratio
- Trades consecutivos perdedores

## 🔧 Configuración

### Variables de entorno

Copia `.env.example` a `.env` y configura:

```bash
# API Keys de Binance (OBLIGATORIO)
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret

# Configuración básica
USE_TESTNET=true  # Cambiar a false para trading real
SYMBOL=BTC/USDT
LEVERAGE=10

# Niveles RSI (ajustables)
RSI_OVERSOLD=25
RSI_OVERBOUGHT=75

# Gestión de riesgo
STOP_LOSS_PCT=3
TAKE_PROFIT_PCT=6
POSITION_SIZE_PCT=5
```

### Personalización

Puedes modificar la estrategia editando estos parámetros en `rsi_bot.py`:

```python
# Configuración RSI más conservadora
self.rsi_oversold = 30
self.rsi_overbought = 70

# Menor riesgo
self.leverage = 5
self.position_size_pct = 2
```

## ⚠️ Advertencias Importantes

- **USAR TESTNET PRIMERO**: Siempre prueba con `USE_TESTNET=true`
- **Riesgo de liquidación**: El apalancamiento puede causar pérdidas totales
- **Mercado 24/7**: Las criptomonedas operan continuamente
- **Volatilidad alta**: Bitcoin puede moverse 10%+ en minutos
- **No garantías**: El trading implica riesgo de pérdidas

## 📋 Checklist Antes de Trading Real

- [ ] Bot probado en testnet por al menos 1 semana
- [ ] Stop loss y take profit funcionando correctamente
- [ ] Logs y monitoreo configurados
- [ ] Entiendes completamente los riesgos
- [ ] Capital que puedes permitirte perder
- [ ] VPS con IP fija configurado
- [ ] Alerts configurados para errores críticos

## 🆘 Solución de Problemas

### Bot no inicia
```bash
# Verificar logs
sudo supervisorctl tail rsi_bot

# Verificar variables de entorno
cat .env

# Reiniciar manualmente
sudo supervisorctl restart rsi_bot
```

### Errores de API
- Verificar que API keys sean correctas
- Confirmar permisos de trading en Binance
- Revisar que IP no esté bloqueada

### Problemas de conexión
- Verificar conectividad: `ping api.binance.com`
- Revisar firewall del VPS
- Confirmar que el bot tenga acceso a internet

## 📞 Soporte

Si tienes problemas:

1. Revisa los logs: `tail -f logs/rsi_bot_$(date +%Y%m%d).log`
2. Verifica la configuración en `.env`
3. Consulta issues en GitHub
4. Crea un nuevo issue con detalles del error

## 📜 Licencia

MIT License - Uso bajo tu propio riesgo

## 🤝 Contribuciones

Las contribuciones son bienvenidas:

1. Fork el proyecto
2. Crea una branch: `git checkout -b feature/nueva-funcionalidad`
3. Commit: `git commit -m 'Agregar nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Abre un Pull Request

---

**⚠️ DISCLAIMER**: Este bot es para fines educativos. El trading de criptomonedas implica riesgo de pérdidas. Úsalo bajo tu propia responsabilidad.