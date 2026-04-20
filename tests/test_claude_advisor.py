import pytest
import json
from unittest.mock import MagicMock, patch, PropertyMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


MARKET_DATA = {
    'price': 67000.0,
    'rsi': 38.5,
    'volume': 1.234,
    'ema_fast': 66500.0,
    'ema_slow': 65000.0,
    'ema_trend': 60000.0,
    'trend_direction': 'bullish',
}


def _make_mock_response(action, confidence, reasoning):
    """Build a mock anthropic response object."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps({
        "action": action,
        "confidence": confidence,
        "reasoning": reasoning,
    })
    response = MagicMock()
    response.content = [text_block]
    return response


@pytest.fixture
def advisor():
    from claude_advisor import ClaudeAdvisor
    with patch("claude_advisor.anthropic.Anthropic"):
        adv = ClaudeAdvisor(logger=MagicMock())
    return adv


class TestClaudeAdvisorConfirm:
    def test_confirm_long_signal(self, advisor):
        advisor.client.messages.create.return_value = _make_mock_response(
            "CONFIRM", 85, "Alineación EMA sólida con RSI en sobreventa."
        )
        from claude_advisor import TradeDecision
        result = advisor.validate_signal("long", MARKET_DATA)
        assert result is not None
        assert result.action == "CONFIRM"
        assert result.confidence == 85

    def test_reject_long_signal(self, advisor):
        advisor.client.messages.create.return_value = _make_mock_response(
            "REJECT", 70, "RSI borderline y separación EMA insuficiente."
        )
        result = advisor.validate_signal("long", MARKET_DATA)
        assert result is not None
        assert result.action == "REJECT"
        assert result.confidence == 70
        assert "RSI" in result.reasoning

    def test_confirm_short_signal(self, advisor):
        short_data = {**MARKET_DATA, 'rsi': 72.0, 'trend_direction': 'bearish'}
        advisor.client.messages.create.return_value = _make_mock_response(
            "CONFIRM", 80, "Tendencia bajista clara con RSI sobrecomprado."
        )
        result = advisor.validate_signal("short", short_data)
        assert result is not None
        assert result.action == "CONFIRM"

    def test_returns_none_on_api_error(self, advisor):
        advisor.client.messages.create.side_effect = Exception("API timeout")
        result = advisor.validate_signal("long", MARKET_DATA)
        assert result is None

    def test_returns_none_on_json_parse_error(self, advisor):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "not valid json {"
        response = MagicMock()
        response.content = [text_block]
        advisor.client.messages.create.return_value = response
        result = advisor.validate_signal("long", MARKET_DATA)
        assert result is None

    def test_warning_logged_on_api_error(self, advisor):
        advisor.client.messages.create.side_effect = Exception("network error")
        advisor.validate_signal("long", MARKET_DATA)
        advisor.logger.warning.assert_called_once()
        call_args = advisor.logger.warning.call_args[0][0]
        assert "ClaudeAdvisor" in call_args

    def test_uses_opus_model(self, advisor):
        advisor.client.messages.create.return_value = _make_mock_response("CONFIRM", 90, "ok")
        advisor.validate_signal("long", MARKET_DATA)
        call_kwargs = advisor.client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"

    def test_uses_adaptive_thinking(self, advisor):
        advisor.client.messages.create.return_value = _make_mock_response("CONFIRM", 90, "ok")
        advisor.validate_signal("long", MARKET_DATA)
        call_kwargs = advisor.client.messages.create.call_args[1]
        assert call_kwargs["thinking"] == {"type": "adaptive"}

    def test_system_prompt_has_cache_control(self, advisor):
        advisor.client.messages.create.return_value = _make_mock_response("CONFIRM", 90, "ok")
        advisor.validate_signal("long", MARKET_DATA)
        call_kwargs = advisor.client.messages.create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}


class TestPromptBuilding:
    def test_prompt_includes_signal_direction_long(self, advisor):
        prompt = advisor._build_prompt("long", MARKET_DATA)
        assert "LONG" in prompt

    def test_prompt_includes_signal_direction_short(self, advisor):
        prompt = advisor._build_prompt("short", MARKET_DATA)
        assert "SHORT" in prompt

    def test_prompt_includes_price(self, advisor):
        prompt = advisor._build_prompt("long", MARKET_DATA)
        assert "67,000" in prompt or "67000" in prompt

    def test_prompt_includes_rsi(self, advisor):
        prompt = advisor._build_prompt("long", MARKET_DATA)
        assert "38.5" in prompt

    def test_prompt_includes_trend_direction(self, advisor):
        prompt = advisor._build_prompt("long", MARKET_DATA)
        assert "bullish" in prompt

    def test_prompt_includes_ema_separations(self, advisor):
        prompt = advisor._build_prompt("long", MARKET_DATA)
        assert "EMA21 vs EMA50" in prompt


class TestMarketContext:
    def _make_context_response(self, bias, confidence, setup_forming, key_levels, reasoning):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = json.dumps({
            "bias": bias,
            "confidence": confidence,
            "setup_forming": setup_forming,
            "key_levels": key_levels,
            "reasoning": reasoning,
        })
        response = MagicMock()
        response.content = [text_block]
        return response

    def test_returns_market_context_with_long_bias(self, advisor):
        advisor.client.messages.create.return_value = self._make_context_response(
            "long", 75, True, "EMA21: $66500, EMA50: $65000", "RSI converging to oversold."
        )
        from claude_advisor import MarketContext
        result = advisor.analyze_market_context(MARKET_DATA)
        assert result is not None
        assert isinstance(result, MarketContext)
        assert result.bias == "long"
        assert result.confidence == 75
        assert result.setup_forming is True

    def test_returns_neutral_context(self, advisor):
        advisor.client.messages.create.return_value = self._make_context_response(
            "neutral", 40, False, "Price mid-range between EMAs", "No clear direction."
        )
        result = advisor.analyze_market_context(MARKET_DATA)
        assert result is not None
        assert result.bias == "neutral"
        assert result.setup_forming is False

    def test_returns_none_on_api_error(self, advisor):
        advisor.client.messages.create.side_effect = Exception("timeout")
        result = advisor.analyze_market_context(MARKET_DATA)
        assert result is None

    def test_warning_logged_on_context_error(self, advisor):
        advisor.client.messages.create.side_effect = Exception("connection error")
        advisor.analyze_market_context(MARKET_DATA)
        advisor.logger.warning.assert_called_once()

    def test_context_prompt_includes_no_signal_phrase(self, advisor):
        prompt = advisor._build_context_prompt(MARKET_DATA)
        assert "No hay señal" in prompt or "no hay" in prompt.lower()

    def test_context_prompt_includes_all_ema_values(self, advisor):
        prompt = advisor._build_context_prompt(MARKET_DATA)
        assert "66,500" in prompt or "66500" in prompt
        assert "65,000" in prompt or "65000" in prompt
        assert "60,000" in prompt or "60000" in prompt

    def test_uses_same_model_as_validate(self, advisor):
        advisor.client.messages.create.return_value = self._make_context_response(
            "short", 60, False, "EMA resistance", "Bearish structure."
        )
        advisor.analyze_market_context(MARKET_DATA)
        call_kwargs = advisor.client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"

    def test_context_uses_cached_system_prompt(self, advisor):
        advisor.client.messages.create.return_value = self._make_context_response(
            "long", 80, True, "Support at EMA21", "Bullish setup."
        )
        advisor.analyze_market_context(MARKET_DATA)
        call_kwargs = advisor.client.messages.create.call_args[1]
        assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


class TestClaudeAdvisorInit:
    def test_init_creates_anthropic_client(self):
        from claude_advisor import ClaudeAdvisor
        with patch("claude_advisor.anthropic.Anthropic") as mock_cls:
            ClaudeAdvisor(logger=MagicMock())
            mock_cls.assert_called_once()

    def test_graceful_without_api_key(self):
        """ClaudeAdvisor can be instantiated even if key validation happens later."""
        from claude_advisor import ClaudeAdvisor
        with patch("claude_advisor.anthropic.Anthropic"):
            adv = ClaudeAdvisor(logger=MagicMock())
            assert adv is not None
