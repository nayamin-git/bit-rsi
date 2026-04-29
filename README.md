# BTC/USDT RSI + EMA Swing Bot

Bot de swing trading para BTC/USDT en timeframe 4h, con validación inteligente de señales mediante Claude AI. Opera en Binance (producción o testnet) usando Docker.

---

## Estrategia

La estrategia combina tres EMAs y el RSI para identificar pullbacks en tendencia y entrar con confirmación.

### Indicadores
| Indicador | Parámetro | Rol |
|-----------|-----------|-----|
| EMA21 | fast | Señal rápida de tendencia |
| EMA50 | slow | Tendencia de mediano plazo |
| EMA200 | trend | Filtro de tendencia principal |
| RSI | 14 periodos | Oscilador de momentum |

### Clasificación de tendencia
- **bullish**: EMA21 > EMA50 > EMA200 y precio > EMA50 × 0.995
- **weak_bullish**: estructura alcista con precio rezagado o señales mixtas por encima de EMA200
- **bearish**: EMA21 < EMA50 < EMA200 y precio < EMA50 × 1.005
- **weak_bearish**: estructura bajista con precio por encima de EMA200
- **neutral**: sin alineación clara

### Condiciones de entrada
**LONG:** tendencia `bullish`/`weak_bullish` + RSI < 40 (o zona neutra 45-55 con pullback a EMA) + confirmación ≥ 0.15% al alza  
**SHORT:** tendencia `bearish`/`weak_bearish` + RSI > 65 (o zona neutra con rechazo) + confirmación ≥ 0.15% a la baja

### Gestión de riesgo
| Parámetro | Valor base |
|-----------|-----------|
| Stop Loss | 2.0% |
| Take Profit | 4.0% (ratio 1:2) |
| Trailing Stop | 1.5% |
| Breakeven | +1.0% de ganancia |
| Tamaño posición | 3% del balance |

---

## Claude AI — Tres capas de inteligencia

El bot integra Claude Opus como capa de decisión sobre los indicadores técnicos. Se activa cuando hay `ANTHROPIC_API_KEY` configurada; si no, el bot opera normalmente sin ella.

### 1. Validación de señales
Antes de abrir cada posición, Claude evalúa el contexto técnico y decide CONFIRMAR o RECHAZAR.

```
Señal técnica detectada
        │
        ▼
Claude: ¿CONFIRMAR o RECHAZAR?
        │                │
     CONFIRM           REJECT
        │                │
  Abrir posición    Descartar señal
```

**Log:**
```
🤖 Claude CONFIRMÓ LONG (confianza: 87%): Alineación EMA sólida, RSI en zona de sobreventa real.
🤖 Claude RECHAZÓ SHORT (confianza: 72%): RSI borderline y separación EMA insuficiente para confirmar.
```

### 2. Escaneo proactivo de mercado (cada 4h)
Aunque no haya señal activa, Claude analiza el estado del mercado y reporta bias, niveles clave y si hay un setup formándose.

```
🤖 Claude [📈 LONG 78%] — SETUP FORMÁNDOSE: RSI convergiendo a sobreventa con precio apoyándose en EMA21.
🤖 Niveles clave: EMA21 $66,500 soporte crítico, vigilar EMA50 $65,000
```

### 3. Ajuste dinámico de parámetros (cada 4h)
Claude detecta el régimen de mercado y ajusta los parámetros del bot dentro de límites seguros predefinidos.

| Régimen | Lógica aplicada |
|---------|----------------|
| `trending` | RSI más laxo, TP mayor, trailing ajustado para capturar movimiento |
| `ranging` | RSI más estricto, TP reducido, confirmación más exigente |
| `volatile` | Confirmación alta, SL más amplio, breakeven rápido |

**Límites de seguridad (Claude no puede salir de estos rangos):**
| Parámetro | Mín | Base | Máx |
|-----------|-----|------|-----|
| `rsi_oversold` | 30 | 40 | 45 |
| `rsi_overbought` | 60 | 65 | 75 |
| `stop_loss_pct` | 1.0% | 2.0% | 3.5% |
| `take_profit_pct` | 2.5% | 4.0% | 7.0% |
| `swing_confirmation_threshold` | 0.10% | 0.15% | 0.40% |
| `trailing_stop_distance` | 0.8% | 1.5% | 3.0% |
| `breakeven_threshold` | 0.5% | 1.0% | 2.0% |

**Log cuando cambia algo:**
```
🤖 Claude ajustó parámetros [trending]: rsi_oversold: 40 → 35, take_profit_pct: 4.0 → 6.0
🤖 Motivo: Tendencia alcista sólida con EMAs bien alineadas, se amplían objetivos de beneficio.
```

---

## Estructura del proyecto

```
bit-rsi/
├── rsi_bot.py           # Orquestador principal y loop de trading
├── claude_advisor.py    # Integración Claude AI (validación, escaneo, parámetros)
├── config.py            # Configuración centralizada y parámetros ajustables
├── signal_detector.py   # Detección y confirmación de señales RSI+EMA
├── market_analyzer.py   # Clasificación de tendencia y datos de mercado
├── indicators.py        # Cálculo de EMA y RSI
├── risk_manager.py      # Stop loss, take profit, trailing stop, breakeven
├── position_manager.py  # Apertura y cierre de posiciones en Binance
├── exchange_client.py   # Cliente ccxt para Binance
├── analytics.py         # Métricas de rendimiento
├── state_manager.py     # Persistencia de estado entre reinicios
├── logging_manager.py   # Sistema de logging
├── tests/               # Suite de tests unitarios (92 tests)
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

---

## Setup

### Requisitos
- Docker y Docker Compose
- Cuenta en Binance (o Binance Testnet para pruebas)
- API Key de Anthropic (opcional, para Claude AI)

### 1. Configurar credenciales

Crea el archivo `.env` en la raíz del proyecto:

```env
# Binance
BINANCE_API_KEY=tu_api_key
BINANCE_SECRET_KEY=tu_secret_key

# Claude AI (opcional)
ANTHROPIC_API_KEY=sk-ant-...

# Modo testnet (True/False)
TESTNET=True
```

Para obtener claves de testnet: https://testnet.binancefuture.com

### 2. Construir y arrancar

```bash
make build    # Construye la imagen Docker
make up       # Inicia el bot en segundo plano
make logs     # Sigue los logs en tiempo real
```

### 3. Verificar que funciona

```bash
make status   # Estado del contenedor
make health   # Health check
```

---

## Comandos

```bash
make build        # Construir imagen
make up           # Iniciar bot (background)
make down         # Detener bot
make restart      # Reiniciar bot
make logs         # Logs en tiempo real
make logs-tail    # Últimos 100 logs
make status       # Estado del contenedor
make health       # Health check
make monitor      # Uso de CPU/RAM
make shell        # Acceder al contenedor
make backup       # Backup de logs, datos y .env
make clean        # Eliminar contenedores e imágenes
```

---

## Configuración

Todos los parámetros están en `config.py`. Los más relevantes:

```python
# Modo de operación
testnet = True                  # False para dinero real

# RSI
rsi_oversold = 40               # Umbral de sobreventa para LONG
rsi_overbought = 65             # Umbral de sobrecompra para SHORT

# Riesgo
stop_loss_pct = 2.0             # Stop loss en %
take_profit_pct = 4.0           # Take profit en %
trailing_stop_distance = 1.5    # Trailing stop en %
breakeven_threshold = 1.0       # Activar breakeven tras +X%

# Claude AI
use_claude_advisor = True       # Activar integración Claude
claude_scan_interval = 14400    # Escaneo proactivo cada 4h (segundos)
```

---

## Tests

```bash
# Dentro del contenedor
make shell
pytest tests/ -v

# Localmente (requiere dependencias instaladas)
pip install -r requirements.txt
pytest tests/ -v
```

La suite cubre: señales, confirmaciones, gestión de riesgo, analytics, integración Claude (con mocks).

---

## Persistencia

Los datos sobreviven reinicios del contenedor mediante volúmenes Docker:

| Directorio | Contenido |
|------------|-----------|
| `./logs/` | Logs del bot |
| `./data/` | Estado de posiciones y métricas |
| `./backups/` | Backups manuales (`make backup`) |
