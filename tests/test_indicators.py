import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicators import TechnicalIndicators


@pytest.fixture
def indicators():
    return TechnicalIndicators()


class TestRSI:
    def test_rsi_oversold_when_prices_falling(self, indicators):
        prices = pd.Series([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86], dtype=float)
        rsi = indicators.calculate_rsi(prices)
        assert rsi < 40

    def test_rsi_overbought_when_prices_rising(self, indicators):
        prices = pd.Series([80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100, 102, 104, 106, 108], dtype=float)
        rsi = indicators.calculate_rsi(prices)
        assert rsi > 60

    def test_rsi_neutral_with_alternating_prices(self, indicators):
        prices = pd.Series([100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100], dtype=float)
        rsi = indicators.calculate_rsi(prices)
        assert 40 <= rsi <= 60

    def test_rsi_returns_50_on_insufficient_data(self, indicators):
        prices = pd.Series([100, 101, 102], dtype=float)
        rsi = indicators.calculate_rsi(prices, period=14)
        assert rsi == 50

    def test_rsi_accepts_list(self, indicators):
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86]
        rsi = indicators.calculate_rsi(prices)
        assert isinstance(rsi, float)
        assert 0 <= rsi <= 100

    def test_rsi_accepts_numpy_array(self, indicators):
        prices = np.array([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86], dtype=float)
        rsi = indicators.calculate_rsi(prices)
        assert 0 <= rsi <= 100

    def test_rsi_within_valid_range(self, indicators):
        prices = pd.Series(range(1, 20), dtype=float)
        rsi = indicators.calculate_rsi(prices)
        assert 0 <= rsi <= 100

    def test_rsi_returns_50_on_error(self, indicators):
        rsi = indicators.calculate_rsi([])
        assert rsi == 50


class TestEMA:
    def test_ema_returns_float(self, indicators):
        prices = [100, 101, 102, 103, 104]
        ema = indicators.calculate_ema(prices, period=3)
        assert isinstance(ema, float)

    def test_ema_fast_above_slow_in_uptrend(self, indicators):
        prices = list(range(80, 110))
        ema_fast = indicators.calculate_ema(prices, period=5)
        ema_slow = indicators.calculate_ema(prices, period=20)
        assert ema_fast > ema_slow

    def test_ema_slow_above_fast_in_downtrend(self, indicators):
        prices = list(range(110, 80, -1))
        ema_fast = indicators.calculate_ema(prices, period=5)
        ema_slow = indicators.calculate_ema(prices, period=20)
        assert ema_slow > ema_fast

    def test_ema_tracks_recent_prices_more_than_old(self, indicators):
        prices = [100] * 10 + [120] * 10
        ema_short = indicators.calculate_ema(prices, period=3)
        ema_long = indicators.calculate_ema(prices, period=10)
        assert ema_short > ema_long

    def test_ema_accepts_list(self, indicators):
        prices = [100, 101, 102, 103, 104]
        ema = indicators.calculate_ema(prices, period=3)
        assert ema > 0

    def test_ema_accepts_numpy_array(self, indicators):
        prices = np.array([100, 101, 102, 103, 104], dtype=float)
        ema = indicators.calculate_ema(prices, period=3)
        assert ema > 0

    def test_ema_returns_0_on_error(self, indicators):
        ema = indicators.calculate_ema([], period=3)
        assert ema == 0

    def test_ema_stable_with_flat_prices(self, indicators):
        prices = [100.0] * 20
        ema = indicators.calculate_ema(prices, period=10)
        assert abs(ema - 100.0) < 0.01
