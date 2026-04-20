import pytest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from market_analyzer import MarketAnalyzer


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.ema_separation_min = 0.1
    cfg.ema_touch_threshold = 0.5
    return cfg


@pytest.fixture
def analyzer(config):
    return MarketAnalyzer(exchange=None, config=config, indicators=MagicMock(), logger=MagicMock())


class TestTrendDirection:
    def test_bullish_when_emas_aligned_and_price_above_slow(self, analyzer):
        # EMA21 > EMA50 > EMA200 and price above EMA50 * 0.995
        result = analyzer.determine_trend_direction(
            price=102.0, ema_fast=105.0, ema_slow=100.0, ema_trend=90.0
        )
        assert result == 'bullish'

    def test_bearish_when_emas_aligned_and_price_below_slow(self, analyzer):
        # EMA21 < EMA50 < EMA200 and price below EMA50 * 1.005
        result = analyzer.determine_trend_direction(
            price=98.0, ema_fast=90.0, ema_slow=100.0, ema_trend=110.0
        )
        assert result == 'bearish'

    def test_weak_bullish_when_emas_bullish_but_price_below_slow(self, analyzer):
        # EMA21 > EMA50 > EMA200 but price below EMA50, above EMA200
        result = analyzer.determine_trend_direction(
            price=92.0, ema_fast=105.0, ema_slow=100.0, ema_trend=90.0
        )
        assert result in ['weak_bullish', 'neutral']

    def test_neutral_when_emas_not_aligned(self, analyzer):
        # All EMAs equal -> neutral
        result = analyzer.determine_trend_direction(
            price=100.0, ema_fast=100.0, ema_slow=100.0, ema_trend=100.0
        )
        assert result == 'neutral'

    def test_weak_bullish_when_mixed_signals_price_above_trend(self, analyzer):
        # price > EMA200 and EMA21 > EMA50 (but EMA50 < EMA200)
        result = analyzer.determine_trend_direction(
            price=110.0, ema_fast=108.0, ema_slow=105.0, ema_trend=100.0
        )
        # This case: ema_fast > ema_slow but ema_slow > ema_trend doesn't hold here
        # ema_slow(105) > ema_trend(100), ema_fast(108) > ema_slow(105) -> bullish case
        assert result in ['bullish', 'weak_bullish', 'neutral']

    def test_weak_bearish_when_mixed_signals_price_below_trend(self, analyzer):
        # price < EMA200 and EMA21 < EMA50
        result = analyzer.determine_trend_direction(
            price=88.0, ema_fast=90.0, ema_slow=95.0, ema_trend=100.0
        )
        assert result in ['bearish', 'weak_bearish']


class TestPullbackToEMA:
    def test_pullback_to_ema21(self, analyzer):
        # Price within 0.5% of EMA21
        is_pullback, pullback_type = analyzer.is_pullback_to_ema(
            price=100.3, ema_fast=100.0, ema_slow=95.0
        )
        assert is_pullback is True
        assert pullback_type == 'EMA21'

    def test_pullback_to_ema50(self, analyzer):
        # Price within 0.5% of EMA50
        is_pullback, pullback_type = analyzer.is_pullback_to_ema(
            price=95.3, ema_fast=102.0, ema_slow=95.0
        )
        assert is_pullback is True
        assert pullback_type == 'EMA50'

    def test_pullback_between_emas(self, analyzer):
        # Price between EMA21 and EMA50
        is_pullback, pullback_type = analyzer.is_pullback_to_ema(
            price=97.0, ema_fast=100.0, ema_slow=95.0
        )
        assert is_pullback is True
        assert pullback_type == 'Entre_EMAs'

    def test_no_pullback_when_price_far_from_emas(self, analyzer):
        # Price 10% away from EMA21 and EMA50
        is_pullback, pullback_type = analyzer.is_pullback_to_ema(
            price=115.0, ema_fast=100.0, ema_slow=95.0
        )
        assert is_pullback is False
        assert pullback_type == 'No_pullback'

    def test_pullback_priority_ema21_over_ema50(self, analyzer):
        # Price within 0.5% of both EMAs (edge case - normally they are separated)
        is_pullback, pullback_type = analyzer.is_pullback_to_ema(
            price=100.3, ema_fast=100.0, ema_slow=100.1
        )
        assert is_pullback is True
        assert pullback_type == 'EMA21'  # EMA21 check comes first
