import pytest
import csv
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import Analytics


@pytest.fixture
def tmp_config(tmp_path):
    cfg = MagicMock()
    cfg.logs_dir = str(tmp_path)
    cfg.max_swing_wait = 12
    return cfg


@pytest.fixture
def analytics(tmp_config):
    position_manager = MagicMock()
    position_manager.in_position = False
    position_manager.position = None

    signal_detector = MagicMock()
    signal_detector.pending_long_signal = False
    signal_detector.pending_short_signal = False
    signal_detector.swing_wait_count = 0

    a = Analytics(
        tmp_config,
        logger=MagicMock(),
        position_manager=position_manager,
        signal_detector=signal_detector,
        get_balance_callback=lambda: 596.31,
    )
    a.set_performance_metrics({
        'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
        'total_pnl': 0, 'max_drawdown': 0, 'consecutive_losses': 0,
        'max_consecutive_losses': 0, 'signals_detected': 0,
        'signals_confirmed': 0, 'signals_expired': 0,
        'recoveries_performed': 0, 'trend_filters_applied': 0,
        'ema_confirmations': 0, 'pullback_entries': 0,
    })
    a.init_log_files()
    return a


class TestLogMarketData:
    def _row(self, analytics, **kwargs):
        defaults = dict(
            timestamp=datetime(2026, 5, 1, 12, 0, 0),
            price=77000.0, rsi=55.0, volume=1.5,
            ema_fast=76800.0, ema_slow=76700.0, ema_trend=74000.0,
            trend_direction='bullish', signal=None,
            in_position=False, position_side=None,
            unrealized_pnl_pct=0.0, pending_signal='',
        )
        defaults.update(kwargs)
        analytics.log_market_data(**defaults)

    def test_writes_row_to_csv(self, analytics, tmp_config):
        self._row(analytics)
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        # 1 header + 1 data row
        assert len(rows) == 2

    def test_csv_row_contains_price(self, analytics):
        self._row(analytics, price=77123.45)
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert '77123.45' in rows[1]

    def test_csv_row_contains_trend_direction(self, analytics):
        self._row(analytics, trend_direction='weak_bullish')
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert 'weak_bullish' in rows[1]

    def test_csv_row_contains_rsi(self, analytics):
        self._row(analytics, rsi=38.5)
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert '38.50' in rows[1]

    def test_multiple_rows_accumulate(self, analytics):
        self._row(analytics, price=75000.0)
        self._row(analytics, price=76000.0)
        self._row(analytics, price=77000.0)
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 4  # header + 3 data rows

    def test_pending_signal_written(self, analytics):
        self._row(analytics, pending_signal='LONG_WAIT_3/12')
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert 'LONG_WAIT_3/12' in rows[1]

    def test_in_position_true_written(self, analytics):
        self._row(analytics, in_position=True, position_side='long', unrealized_pnl_pct=1.5)
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert 'True' in rows[1]
        assert 'long' in rows[1]

    def test_no_crash_when_market_csv_is_none(self, analytics):
        analytics.market_csv = None
        self._row(analytics)  # should not raise

    def test_error_is_logged_not_raised(self, analytics):
        analytics.market_csv = '/nonexistent_dir/file.csv'
        self._row(analytics)  # should not raise, just log error
        analytics.logger.error.assert_called_once()


class TestInitLogFiles:
    def test_creates_csv_files(self, analytics):
        assert os.path.exists(analytics.trades_csv)
        assert os.path.exists(analytics.market_csv)

    def test_market_csv_has_header(self, analytics):
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert rows[0][0] == 'timestamp'
        assert 'price' in rows[0]
        assert 'rsi' in rows[0]

    def test_does_not_overwrite_existing_file(self, analytics):
        # Write a data row, then reinit — header-only check should still show the row
        with open(analytics.market_csv, 'a', newline='') as f:
            csv.writer(f).writerow(['existing_data'])
        analytics.init_log_files()
        with open(analytics.market_csv, newline='') as f:
            rows = list(csv.reader(f))
        assert any('existing_data' in r for r in rows)
