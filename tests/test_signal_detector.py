import pytest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from signal_detector import SignalDetector


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.rsi_oversold = 40
    cfg.rsi_overbought = 65
    cfg.rsi_neutral_low = 45
    cfg.rsi_neutral_high = 55
    cfg.swing_confirmation_threshold = 0.15
    cfg.max_swing_wait = 12
    cfg.pullback_ema_touch = False
    return cfg


@pytest.fixture
def market_analyzer():
    ma = MagicMock()
    ma.is_pullback_to_ema.return_value = (True, 'EMA21')
    return ma


@pytest.fixture
def performance_metrics():
    return {
        'signals_detected': 0,
        'signals_confirmed': 0,
        'signals_expired': 0,
    }


@pytest.fixture
def detector(config, market_analyzer, performance_metrics):
    return SignalDetector(config, MagicMock(), market_analyzer, performance_metrics)


class TestDetectSwingSignal:
    def test_detects_long_when_rsi_oversold_and_bullish_trend(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=False
        )
        assert result is True
        assert detector.pending_long_signal is True
        assert detector.signal_trigger_price == 100.0

    def test_detects_long_in_neutral_trend(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='neutral', in_position=False
        )
        assert result is True

    def test_no_long_when_in_position(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=True
        )
        assert result is False
        assert detector.pending_long_signal is False

    def test_no_signal_when_rsi_neutral(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=50.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=False
        )
        assert result is False

    def test_no_long_when_trend_bearish(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bearish', in_position=False
        )
        assert result is False

    def test_detects_short_when_rsi_overbought_and_bearish_trend(self, detector):
        result = detector.detect_swing_signal(
            price=100.0, rsi=70.0, ema_fast=99.0, ema_slow=101.0,
            ema_trend=105.0, trend_direction='bearish', in_position=False
        )
        assert result is True
        assert detector.pending_short_signal is True

    def test_no_new_signal_when_pending_long_exists(self, detector):
        # Set up a pending long
        detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=False
        )
        # Second attempt should be ignored
        result = detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=False
        )
        assert result is False

    def test_increments_signals_detected_metric(self, detector, performance_metrics):
        detector.detect_swing_signal(
            price=100.0, rsi=35.0, ema_fast=101.0, ema_slow=99.0,
            ema_trend=95.0, trend_direction='bullish', in_position=False
        )
        assert performance_metrics['signals_detected'] == 1


class TestCheckSwingConfirmation:
    def test_confirms_long_when_price_up_and_rsi_improved(self, detector):
        detector.pending_long_signal = True
        detector.signal_trigger_price = 100.0
        detector.last_rsi = 38.0

        confirmed, direction = detector.check_swing_confirmation(
            current_price=100.2, current_rsi=47.0, trend_direction='bullish'
        )
        assert confirmed is True
        assert direction == 'long'

    def test_no_confirmation_when_price_not_moved_enough(self, detector):
        detector.pending_long_signal = True
        detector.signal_trigger_price = 100.0
        detector.last_rsi = 38.0

        confirmed, direction = detector.check_swing_confirmation(
            current_price=100.1, current_rsi=47.0, trend_direction='bullish'
        )
        assert confirmed is False

    def test_long_signal_expires_after_max_wait(self, detector, config):
        detector.pending_long_signal = True
        detector.signal_trigger_price = 100.0
        detector.swing_wait_count = config.max_swing_wait - 1

        confirmed, direction = detector.check_swing_confirmation(
            current_price=100.0, current_rsi=38.0, trend_direction='bearish'
        )
        assert confirmed is False
        assert direction is None
        assert detector.pending_long_signal is False

    def test_confirms_short_when_price_down_and_rsi_improved(self, detector):
        detector.pending_short_signal = True
        detector.signal_trigger_price = 100.0
        detector.last_rsi = 68.0

        confirmed, direction = detector.check_swing_confirmation(
            current_price=99.8, current_rsi=53.0, trend_direction='bearish'
        )
        assert confirmed is True
        assert direction == 'short'

    def test_short_signal_expires_after_max_wait(self, detector, config):
        detector.pending_short_signal = True
        detector.signal_trigger_price = 100.0
        detector.swing_wait_count = config.max_swing_wait - 1

        confirmed, direction = detector.check_swing_confirmation(
            current_price=100.0, current_rsi=68.0, trend_direction='bullish'
        )
        assert confirmed is False
        assert detector.pending_short_signal is False

    def test_returns_false_without_any_pending_signal(self, detector):
        confirmed, direction = detector.check_swing_confirmation(
            current_price=100.0, current_rsi=50.0, trend_direction='neutral'
        )
        assert confirmed is False
        assert direction is None

    def test_resets_state_after_confirmation(self, detector):
        detector.pending_long_signal = True
        detector.signal_trigger_price = 100.0
        detector.last_rsi = 38.0
        detector.swing_wait_count = 3

        detector.check_swing_confirmation(
            current_price=100.2, current_rsi=47.0, trend_direction='bullish'
        )
        assert detector.pending_long_signal is False
        assert detector.signal_trigger_price is None
        assert detector.swing_wait_count == 0


class TestResetSignalState:
    def test_clears_all_signal_state(self, detector):
        detector.pending_long_signal = True
        detector.signal_trigger_price = 100.0
        detector.swing_wait_count = 5

        detector.reset_signal_state()

        assert detector.pending_long_signal is False
        assert detector.pending_short_signal is False
        assert detector.signal_trigger_price is None
        assert detector.signal_trigger_time is None
        assert detector.swing_wait_count == 0

    def test_update_last_rsi(self, detector):
        detector.update_last_rsi(42.5)
        assert detector.last_rsi == 42.5
