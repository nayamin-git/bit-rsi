import json
import os
from dataclasses import dataclass
from typing import Optional

import anthropic

_SYSTEM_PROMPT = """Eres un experto en trading técnico de criptomonedas, especializado en análisis de BTC/USDT en timeframe 4h usando la estrategia RSI + EMA.

## Estrategia del bot

**Indicadores:**
- EMA21 (fast): señal rápida de tendencia
- EMA50 (slow): tendencia de mediano plazo
- EMA200 (trend): filtro de tendencia principal
- RSI(14): oscilador de momentum

**Clasificación de tendencia:**
- `bullish`: EMA21 > EMA50 > EMA200 Y precio > EMA50 × 0.995
- `weak_bullish`: EMAs con estructura alcista pero precio rezagado, o señales mixtas con precio > EMA200
- `bearish`: EMA21 < EMA50 < EMA200 Y precio < EMA50 × 1.005
- `weak_bearish`: EMAs con estructura bajista pero precio por encima de EMA200, o mixto
- `neutral`: EMAs sin alineación clara

**Condiciones de entrada LONG:**
1. Tendencia `bullish` o `weak_bullish`
2. RSI < 40 (sobreventa) o RSI en zona neutra (45-55) con pullback a EMA
3. Pullback a EMA21, EMA50, o precio entre ambas EMAs
4. Confirmación: precio sube ≥ 0.15% desde trigger + RSI mejora

**Condiciones de entrada SHORT:**
1. Tendencia `bearish` o `weak_bearish`
2. RSI > 65 (sobrecompra) o RSI en zona neutra con rechazo
3. Precio rechazado en EMA21, EMA50
4. Confirmación: precio baja ≥ 0.15% desde trigger + RSI deteriora

**Gestión de riesgo:**
- Stop Loss: 2% desde entrada
- Take Profit: 4% desde entrada (ratio 1:2)
- Trailing Stop: 1.5%, Breakeven en +1%

## Tu rol

Puedes ser consultado en dos modos:
1. **Validar señal confirmada** — evalúa si CONFIRMAR o RECHAZAR una señal que el bot ya activó.
2. **Escanear mercado** — analiza el estado actual y detecta si se está formando una oportunidad aunque los indicadores técnicos aún no hayan disparado señal.

**Evalúa basándote en:**
- ¿La alineación de EMAs es sólida o marginal?
- ¿El RSI está en zona de interés o convergiendo hacia ella?
- ¿La separación entre EMAs confirma momentum?
- ¿Hay divergencias preocupantes?
- ¿El precio está en una zona técnica relevante (soporte/resistencia EMA)?

**Responde SOLO con JSON válido, sin texto adicional.**"""


@dataclass
class TradeDecision:
    action: str       # "CONFIRM" | "REJECT"
    confidence: int   # 0-100
    reasoning: str


@dataclass
class MarketContext:
    bias: str         # "long" | "short" | "neutral"
    confidence: int   # 0-100
    setup_forming: bool
    key_levels: str
    reasoning: str


class ClaudeAdvisor:
    def __init__(self, logger):
        self.client = anthropic.Anthropic()
        self.logger = logger

    def validate_signal(self, signal_type: str, market_data: dict) -> Optional[TradeDecision]:
        try:
            user_message = self._build_prompt(signal_type, market_data)
            response = self.client.messages.create(
                model="claude-opus-4-7",
                max_tokens=512,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=[{"role": "user", "content": user_message}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "trade_decision",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "action": {"type": "string", "enum": ["CONFIRM", "REJECT"]},
                                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                                    "reasoning": {"type": "string"}
                                },
                                "required": ["action", "confidence", "reasoning"],
                                "additionalProperties": False
                            }
                        }
                    }
                }
            )
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            return TradeDecision(**data)
        except Exception as e:
            self.logger.warning(f"ClaudeAdvisor no disponible (bot continúa normalmente): {e}")
            return None

    def analyze_market_context(self, market_data: dict) -> Optional[MarketContext]:
        """Escaneo proactivo: Claude analiza el mercado aunque no haya señal técnica activa."""
        try:
            user_message = self._build_context_prompt(market_data)
            response = self.client.messages.create(
                model="claude-opus-4-7",
                max_tokens=512,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=[{"role": "user", "content": user_message}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "market_context",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "bias": {"type": "string", "enum": ["long", "short", "neutral"]},
                                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                                    "setup_forming": {"type": "boolean"},
                                    "key_levels": {"type": "string"},
                                    "reasoning": {"type": "string"}
                                },
                                "required": ["bias", "confidence", "setup_forming", "key_levels", "reasoning"],
                                "additionalProperties": False
                            }
                        }
                    }
                }
            )
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            return MarketContext(**data)
        except Exception as e:
            self.logger.warning(f"ClaudeAdvisor contexto no disponible (bot continúa normalmente): {e}")
            return None

    def _build_prompt(self, signal_type: str, market_data: dict) -> str:
        direction = "LONG (compra)" if signal_type == "long" else "SHORT (venta)"
        ema_fast = market_data.get('ema_fast', 0)
        ema_slow = market_data.get('ema_slow', 0)
        ema_trend = market_data.get('ema_trend', 0)
        price = market_data.get('price', 0)

        fast_slow_sep = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow > 0 else 0
        slow_trend_sep = ((ema_slow - ema_trend) / ema_trend * 100) if ema_trend > 0 else 0
        price_vs_fast = ((price - ema_fast) / ema_fast * 100) if ema_fast > 0 else 0

        return f"""El bot ha confirmado una señal de entrada {direction}.

**Datos de mercado actuales:**
- Precio BTC: ${price:,.2f}
- RSI(14): {market_data.get('rsi', 0):.1f}
- Volumen actual: {market_data.get('volume', 0):.4f} BTC
- Tendencia detectada: {market_data.get('trend_direction', 'unknown')}

**EMAs:**
- EMA21 (fast): ${ema_fast:,.2f}
- EMA50 (slow): ${ema_slow:,.2f}
- EMA200 (trend): ${ema_trend:,.2f}

**Separaciones:**
- EMA21 vs EMA50: {fast_slow_sep:+.3f}%
- EMA50 vs EMA200: {slow_trend_sep:+.3f}%
- Precio vs EMA21: {price_vs_fast:+.3f}%

¿Debo CONFIRMAR o RECHAZAR esta señal {direction}?"""

    def _build_context_prompt(self, market_data: dict) -> str:
        ema_fast = market_data.get('ema_fast', 0)
        ema_slow = market_data.get('ema_slow', 0)
        ema_trend = market_data.get('ema_trend', 0)
        price = market_data.get('price', 0)

        fast_slow_sep = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow > 0 else 0
        slow_trend_sep = ((ema_slow - ema_trend) / ema_trend * 100) if ema_trend > 0 else 0
        price_vs_fast = ((price - ema_fast) / ema_fast * 100) if ema_fast > 0 else 0
        price_vs_slow = ((price - ema_slow) / ema_slow * 100) if ema_slow > 0 else 0

        return f"""No hay señal técnica activa actualmente. Analiza el estado del mercado.

**Snapshot actual BTC/USDT 4h:**
- Precio: ${price:,.2f}
- RSI(14): {market_data.get('rsi', 0):.1f}
- Volumen: {market_data.get('volume', 0):.4f} BTC
- Tendencia clasificada: {market_data.get('trend_direction', 'unknown')}

**EMAs:**
- EMA21: ${ema_fast:,.2f} | Precio vs EMA21: {price_vs_fast:+.3f}%
- EMA50: ${ema_slow:,.2f} | Precio vs EMA50: {price_vs_slow:+.3f}%
- EMA200: ${ema_trend:,.2f}

**Separaciones:**
- EMA21 vs EMA50: {fast_slow_sep:+.3f}%
- EMA50 vs EMA200: {slow_trend_sep:+.3f}%

Responde:
- `bias`: dirección técnica dominante ("long", "short" o "neutral")
- `confidence`: tu nivel de convicción (0-100)
- `setup_forming`: ¿se está construyendo una oportunidad de entrada próxima? (true/false)
- `key_levels`: niveles clave a vigilar (EMAs, zonas de precio) en una línea corta
- `reasoning`: explicación breve de tu análisis (máx 2 oraciones)"""
