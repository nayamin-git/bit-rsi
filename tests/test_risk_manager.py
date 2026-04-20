import pytest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from risk_manager import RiskManager


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.breakeven_threshold = 1.0
    cfg.trailing_stop_distance = 1.5
    return cfg


def make_long_position(entry=100.0, stop_loss=98.0, take_profit=104.0, trailing_stop=98.0):
    return {
        'side': 'long',
        'entry_price': entry,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'trailing_stop': trailing_stop,
        'highest_price': entry,
        'lowest_price': entry,
        'breakeven_moved': False,
    }


def make_short_position(entry=100.0, stop_loss=102.0, take_profit=96.0, trailing_stop=102.0):
    return {
        'side': 'short',
        'entry_price': entry,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'trailing_stop': trailing_stop,
        'highest_price': entry,
        'lowest_price': entry,
        'breakeven_moved': False,
    }


@pytest.fixture
def position_manager():
    pm = MagicMock()
    pm.in_position = True
    return pm


@pytest.fixture
def close_callback():
    return MagicMock()


@pytest.fixture
def risk_manager(config, position_manager, close_callback):
    return RiskManager(config, MagicMock(), position_manager, close_callback)


def make_market_data(trend='neutral', ema_fast=99.0, ema_slow=98.0):
    return {'trend_direction': trend, 'ema_fast': ema_fast, 'ema_slow': ema_slow}


class TestLongExitConditions:
    def test_stop_loss_triggers_close(self, risk_manager, position_manager, close_callback):
        position_manager.position = make_long_position(stop_loss=98.0)
        risk_manager.check_exit_conditions_swing(97.5, 45.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Stop Loss' in close_callback.call_args[0][0]

    def test_take_profit_triggers_close(self, risk_manager, position_manager, close_callback):
        position_manager.position = make_long_position(take_profit=104.0)
        risk_manager.check_exit_conditions_swing(105.0, 75.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Take Profit' in close_callback.call_args[0][0]

    def test_trailing_stop_triggers_close(self, risk_manager, position_manager, close_callback):
        pos = make_long_position(trailing_stop=99.0)
        pos['breakeven_moved'] = True
        pos['highest_price'] = 103.0
        position_manager.position = pos
        risk_manager.check_exit_conditions_swing(98.5, 45.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Trailing Stop' in close_callback.call_args[0][0]

    def test_bearish_trend_with_rsi_overbought_triggers_close(self, risk_manager, position_manager, close_callback):
        pos = make_long_position()
        pos['highest_price'] = 100.0
        position_manager.position = pos
        # RSI > 70 triggers exit on bearish trend
        risk_manager.check_exit_conditions_swing(
            100.5, 75.0, make_market_data(trend='bearish', ema_fast=99.0)
        )
        close_callback.assert_called_once()

    def test_no_exit_when_price_within_range(self, risk_manager, position_manager, close_callback):
        pos = make_long_position(stop_loss=98.0, take_profit=104.0, trailing_stop=98.0)
        pos['highest_price'] = 101.0
        position_manager.position = pos
        risk_manager.check_exit_conditions_swing(
            101.5, 55.0, make_market_data(trend='bullish', ema_fast=101.0)
        )
        close_callback.assert_not_called()

    def test_no_exit_when_not_in_position(self, risk_manager, position_manager, close_callback):
        position_manager.in_position = False
        position_manager.position = None
        risk_manager.check_exit_conditions_swing(97.0, 45.0, make_market_data())
        close_callback.assert_not_called()


class TestShortExitConditions:
    def test_stop_loss_triggers_close(self, risk_manager, position_manager, close_callback):
        position_manager.position = make_short_position(stop_loss=102.0)
        risk_manager.check_exit_conditions_swing(103.0, 55.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Stop Loss' in close_callback.call_args[0][0]

    def test_take_profit_triggers_close(self, risk_manager, position_manager, close_callback):
        position_manager.position = make_short_position(take_profit=96.0)
        risk_manager.check_exit_conditions_swing(95.0, 25.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Take Profit' in close_callback.call_args[0][0]

    def test_trailing_stop_triggers_close(self, risk_manager, position_manager, close_callback):
        pos = make_short_position(trailing_stop=101.0)
        pos['breakeven_moved'] = True
        pos['lowest_price'] = 97.0
        position_manager.position = pos
        risk_manager.check_exit_conditions_swing(101.5, 55.0, make_market_data())
        close_callback.assert_called_once()
        assert 'Trailing Stop' in close_callback.call_args[0][0]

    def test_no_exit_when_price_within_range(self, risk_manager, position_manager, close_callback):
        pos = make_short_position(stop_loss=102.0, take_profit=96.0, trailing_stop=102.0)
        pos['lowest_price'] = 99.0
        position_manager.position = pos
        risk_manager.check_exit_conditions_swing(
            98.5, 45.0, make_market_data(trend='bearish', ema_fast=99.0)
        )
        close_callback.assert_not_called()


class TestTrailingStopUpdate:
    def test_moves_to_breakeven_when_gain_exceeds_threshold(self, risk_manager, position_manager, config):
        config.breakeven_threshold = 1.0
        pos = make_long_position(entry=100.0)
        position_manager.position = pos

        risk_manager.update_trailing_stop_swing(current_price=101.5, market_data={})

        assert pos['breakeven_moved'] is True
        assert pos['trailing_stop'] > 100.0

    def test_trailing_stop_updates_on_new_high(self, risk_manager, position_manager, config):
        config.trailing_stop_distance = 1.5
        pos = make_long_position(entry=100.0, trailing_stop=99.0)
        pos['breakeven_moved'] = True
        pos['highest_price'] = 102.0
        position_manager.position = pos

        risk_manager.update_trailing_stop_swing(current_price=105.0, market_data={})

        expected = 105.0 * (1 - 1.5 / 100)
        assert pos['trailing_stop'] == pytest.approx(expected)

    def test_trailing_stop_not_lowered_on_pullback(self, risk_manager, position_manager, config):
        config.trailing_stop_distance = 1.5
        pos = make_long_position(entry=100.0, trailing_stop=103.0)
        pos['breakeven_moved'] = True
        pos['highest_price'] = 105.0
        position_manager.position = pos

        # Price pulls back but trailing stop should not decrease
        risk_manager.update_trailing_stop_swing(current_price=103.5, market_data={})

        assert pos['trailing_stop'] == 103.0  # Unchanged

    def test_short_moves_to_breakeven_on_gain(self, risk_manager, position_manager, config):
        config.breakeven_threshold = 1.0
        pos = make_short_position(entry=100.0)
        position_manager.position = pos

        risk_manager.update_trailing_stop_swing(current_price=98.5, market_data={})

        assert pos['breakeven_moved'] is True
        assert pos['trailing_stop'] < 100.0

    def test_no_update_when_not_in_position(self, risk_manager, position_manager):
        position_manager.in_position = False
        position_manager.position = None
        risk_manager.update_trailing_stop_swing(current_price=105.0, market_data={})
        # Should not raise any exception
