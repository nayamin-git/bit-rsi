import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_manager import StateManager


@pytest.fixture
def tmp_config(tmp_path):
    cfg = MagicMock()
    cfg.testnet = False
    cfg.leverage = 1
    cfg.symbol = 'BTC/USDT'
    cfg.state_file = str(tmp_path / 'bot_state.json')
    cfg.recovery_file = str(tmp_path / 'recovery_log.txt')
    cfg.stop_loss_pct = 2.0
    cfg.take_profit_pct = 4.0
    return cfg


@pytest.fixture
def position_manager():
    pm = MagicMock()
    pm.in_position = False
    pm.position = None
    return pm


@pytest.fixture
def signal_detector():
    sd = MagicMock()
    sd.pending_long_signal = False
    sd.pending_short_signal = False
    sd.signal_trigger_price = None
    sd.signal_trigger_time = None
    sd.swing_wait_count = 0
    return sd


@pytest.fixture
def state_manager(tmp_config, position_manager, signal_detector):
    exchange = MagicMock()
    performance_metrics = {'recoveries_performed': 0}
    return StateManager(
        tmp_config, MagicMock(), exchange, position_manager, signal_detector, performance_metrics
    )


def open_long_position(quantity=0.00018):
    return {
        'side': 'long',
        'entry_price': 80000.0,
        'quantity': quantity,
        'stop_loss': 78000.0,
        'take_profit': 84000.0,
    }


class TestVerifyPositionOnExchange:
    def test_spot_position_confirmed_when_balance_covers_quantity(self, state_manager):
        position = open_long_position(quantity=0.00018)
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.00018}}

        assert state_manager.verify_position_on_exchange(position) is True

    def test_spot_position_confirmed_within_fee_tolerance(self, state_manager):
        position = open_long_position(quantity=0.00018)
        # 4% menos que la cantidad original, dentro de la tolerancia del 5%
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.0001728}}

        assert state_manager.verify_position_on_exchange(position) is True

    def test_spot_position_not_found_when_balance_is_empty(self, state_manager):
        position = open_long_position(quantity=0.00018)
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.0}}

        assert state_manager.verify_position_on_exchange(position) is False

    def test_does_not_use_dust_threshold_for_small_real_positions(self, state_manager):
        """Una posición real (~0.0002 BTC) es mucho menor que el umbral de dust
        (0.001 BTC) usado por check_exchange_positions; debe confirmarse igual."""
        position = open_long_position(quantity=0.0002)
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.0002}}

        assert state_manager.verify_position_on_exchange(position) is True

    def test_exchange_error_defaults_to_trusting_state(self, state_manager):
        position = open_long_position()
        state_manager.exchange.fetch_balance.side_effect = Exception("network error")

        assert state_manager.verify_position_on_exchange(position) is True

    def test_futures_position_detected_via_fetch_positions(self, state_manager):
        state_manager.config.leverage = 5
        position = open_long_position()
        state_manager.exchange.fetch_positions.return_value = [{'size': 0.5, 'side': 'long', 'entryPrice': 80000}]

        assert state_manager.verify_position_on_exchange(position) is True

    def test_futures_position_not_found(self, state_manager):
        state_manager.config.leverage = 5
        position = open_long_position()
        state_manager.exchange.fetch_positions.return_value = [{'size': 0, 'side': 'long', 'entryPrice': 80000}]

        assert state_manager.verify_position_on_exchange(position) is False


class TestRecoverBotState:
    def test_loaded_position_verified_keeps_tracking(self, state_manager, position_manager):
        state_manager.load_bot_state = MagicMock(return_value=True)
        state_manager.save_bot_state = MagicMock()
        state_manager.check_exchange_positions = MagicMock()
        position_manager.in_position = True
        position_manager.position = open_long_position(quantity=0.00018)
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.00018}}

        state_manager.recover_bot_state()

        assert position_manager.in_position is True
        assert position_manager.position is not None
        state_manager.check_exchange_positions.assert_not_called()

    def test_loaded_position_unverified_wipes_state_and_checks_dust(self, state_manager, position_manager):
        state_manager.load_bot_state = MagicMock(return_value=True)
        state_manager.save_bot_state = MagicMock()
        state_manager.check_exchange_positions = MagicMock(return_value=None)
        position_manager.in_position = True
        position_manager.position = open_long_position(quantity=0.00018)
        state_manager.exchange.fetch_balance.return_value = {'BTC': {'free': 0.0}}

        state_manager.recover_bot_state()

        assert position_manager.in_position is False
        assert position_manager.position is None
        state_manager.check_exchange_positions.assert_called_once()

    def test_no_state_and_no_exchange_position_is_clean(self, state_manager, position_manager):
        state_manager.load_bot_state = MagicMock(return_value=False)
        state_manager.save_bot_state = MagicMock()
        state_manager.check_exchange_positions = MagicMock(return_value=None)
        state_manager.recover_position_from_exchange = MagicMock()

        state_manager.recover_bot_state()

        state_manager.recover_position_from_exchange.assert_not_called()

    def test_no_state_but_orphaned_exchange_position_triggers_recovery(self, state_manager, position_manager):
        state_manager.load_bot_state = MagicMock(return_value=False)
        state_manager.save_bot_state = MagicMock()
        exchange_position = {'side': 'long', 'size': 0.5, 'entryPrice': 80000}
        state_manager.check_exchange_positions = MagicMock(return_value=exchange_position)
        state_manager.recover_position_from_exchange = MagicMock()

        state_manager.recover_bot_state()

        state_manager.recover_position_from_exchange.assert_called_once_with(exchange_position)
