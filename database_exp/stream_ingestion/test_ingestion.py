"""聚焦事务、归档边界、错误解析和单目录可复制性。"""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

import accounts
from accounts.transform import apply_fills, mark_to_market, value_accounts
import market
import mock_source
import news
import settings
import storage


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = duckdb.connect(str(self.root / "test.duckdb"))
        storage.create_tables(self.db)
        self.start = datetime(2026, 10, 26, 9, tzinfo=timezone.utc)
        self.params = dict(market_params=settings.MARKET, trade_params=settings.TRADES,
                           account_params=settings.ACCOUNTS, news_params=settings.NEWS)
        self.state = mock_source.initial_state(**self.params)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def counts(self):
        return [self.db.execute(f"SELECT count(*) FROM {module.TABLE_NAME}").fetchall()[0][0] for module in storage.TABLE_MODULES]

    def batch(self, tick):
        batch, self.state = mock_source.read_tick(tick, self.start, state=self.state, seed=42, **self.params)
        return batch

    def write(self, tick, batch):
        return storage.write_tick(self.db, batch, tick=tick, received_at=self.start, ingested_at=self.start,
                                  market_params=settings.MARKET, trade_params=settings.TRADES, account_params=settings.ACCOUNTS)

    def export(self, start, end):
        return storage.export_batch(self.db, self.root, start_tick=start, end_tick=end,
                                    simulation_start=self.start, tick_seconds=1, export_seconds=300)

    def test_invalid_account_rolls_back_quotes_and_trades(self):
        batch = self.batch(0)
        cash = batch.account_records[0]["cash_cents"]
        batch.account_records[0]["cash_cents"] = None
        with self.assertRaises(duckdb.ConstraintException):
            self.write(0, batch)
        self.assertEqual(self.counts(), [0, 0, 0])
        batch.account_records[0]["cash_cents"] = cash
        self.write(0, batch)
        self.assertEqual(self.counts(), [2, 2, 2])

    def test_duplicate_trade_rolls_back_new_quotes(self):
        first = self.batch(0)
        self.write(0, first)
        second = replace(self.batch(1), trade_records=first.trade_records)
        with self.assertRaises(duckdb.ConstraintException):
            self.write(1, second)
        self.assertEqual(self.counts(), [2, 2, 2])

    def test_empty_trade_file_and_exclusive_boundary(self):
        for tick in range(6):
            self.write(tick, self.batch(tick))
        name = self.export(1, 5)
        count = self.db.execute("SELECT count(*) FROM read_parquet(?)", [str(self.root / name / "team_trades.parquet")]).fetchall()[0][0]
        ticks = self.db.execute("SELECT DISTINCT tick FROM read_parquet(?) ORDER BY tick", [str(self.root / name / "market_quotes.parquet")]).fetchall()
        self.assertEqual(count, 0)
        self.assertEqual(ticks, [(1,), (2,), (3,), (4,)])
        self.assertEqual(self.counts(), [12, 4, 12])
        with self.assertRaises(FileExistsError):
            self.export(1, 5)

    def test_failed_export_publishes_no_partial_batch(self):
        self.write(0, self.batch(0))
        with patch.object(accounts, "export_parquet", side_effect=OSError("模拟第三个文件失败")):
            with self.assertRaises(OSError):
                self.export(0, 1)
        self.assertFalse(list(self.root.glob("batch_*")))
        self.assertFalse(list(self.root.glob(".batch_*")))
        self.assertEqual(self.counts(), [2, 2, 2])

    def test_pure_simulation_is_repeatable_and_preserves_inputs(self):
        original_state, original_params = deepcopy(self.state), deepcopy(self.params)
        first = mock_source.read_tick(0, self.start, state=self.state, seed=42, **self.params)
        second = mock_source.read_tick(0, self.start, state=self.state, seed=42, **self.params)
        self.assertEqual(first[0], second[0])
        np.testing.assert_equal(first[1], second[1])
        np.testing.assert_equal(self.state, original_state)
        self.assertEqual(self.params, original_params)
        batch, updated = first
        snapshots = deepcopy(batch.account_records)
        self.assertFalse(np.shares_memory(updated["accounts"]["positions"], self.state["accounts"]["positions"]))
        updated["accounts"]["positions"][0, 0] = 999
        self.assertEqual(batch.account_records, snapshots)
        np.testing.assert_equal(self.state, original_state)

    def test_numpy_duplicate_fill_indices_and_symbol_alignment(self):
        state = self.state["accounts"]
        before = deepcopy(state)
        for values in (state["cash"], state["positions"]):
            values.setflags(write=False)
        fills = [dict(team_id="TEAM_A", instrument_id="ALPHA", side=side,
                      quantity=quantity, price_cents=price, fee_cents=1)
                 for side, quantity, price in [("BUY", 5, 100), ("BUY", 3, 110), ("SELL", 2, 120)]]
        updated = apply_fills(state, fills)
        self.assertEqual(updated["positions"].tolist(), [[6, 0], [0, 0]])
        self.assertEqual(updated["cash"].tolist(), [settings.ACCOUNTS.initial_cash_cents - 593, settings.ACCOUNTS.initial_cash_cents])
        np.testing.assert_equal(state, before)
        quotes = [dict(instrument_id="BETA", bid_cents=50, ask_cents=52),
                  dict(instrument_id="ALPHA", bid_cents=100, ask_cents=102)]
        records = value_accounts(self.start, state=updated, quotes=quotes, params=settings.ACCOUNTS)
        self.assertEqual(records[0]["pnl_cents"], 13)

    def test_int64_overflow_is_rejected_before_arithmetic(self):
        with self.assertRaises(OverflowError):
            mark_to_market(np.array([0], dtype=np.int64),
                           np.array([[2]], dtype=np.int64), np.array([2**62], dtype=np.int64))
        with self.assertRaises(OverflowError):
            apply_fills(self.state["accounts"], [dict(team_id="TEAM_A", instrument_id="ALPHA", side="BUY",
                        quantity=2**62, price_cents=3, fee_cents=0)])

    def test_column_input_preserves_json_timezone_and_large_integers(self):
        from datetime import timedelta
        instant = self.start.astimezone(timezone(timedelta(hours=8)))
        context = dict(tick=0, received_at=instant, ingested_at=instant, params=settings.ACCOUNTS)
        amount = 2**53 + 1
        record = dict(event_time=instant, team_id="TEAM_A", cash_cents=amount,
                      positions={"ALPHA": 3}, equity_cents=amount, pnl_cents=0)
        columns = accounts.records_to_columns([record], **context)
        columns["positions"] = np.array(['{"ALPHA": 3}'])  # direct Unicode input also remains a JSON object
        original = deepcopy(columns)
        for values in columns.values():
            values.setflags(write=False)
        accounts.write_columns(self.db, columns)
        row = self.db.execute("SELECT event_time, cash_cents, json_type(positions), positions FROM account_snapshots").fetchall()[0]
        self.assertEqual(row, (self.start, amount, "OBJECT", '{"ALPHA": 3}'))
        np.testing.assert_equal(columns, original)
        with self.assertRaises(ValueError):
            accounts.write_columns(self.db, {**columns, "cash_cents": np.array([], dtype=np.int64)})

    def test_bulk_records_match_scalar_mapping(self):
        records = [dict(event_time=self.start, instrument_id=f"S{i}", bid_cents=2**53 + i,
                        ask_cents=2**53 + i + 2, bid_size=10, ask_size=20) for i in range(1000)]
        context = dict(tick=0, received_at=self.start, ingested_at=self.start, params=settings.MARKET)
        market.write_records(self.db, records, **context)
        actual = self.db.execute("SELECT * FROM market_quotes ORDER BY instrument_id").fetchall()
        expected = sorted([market.parse_record(record, **context) for record in records], key=lambda row: row[4])
        self.assertEqual(actual, expected)

    def test_field_transformations_preserve_inputs(self):
        batch = self.batch(0)
        for module, records, params in zip(storage.TABLE_MODULES,
                                           (batch.market_records, batch.trade_records, batch.account_records),
                                           (settings.MARKET, settings.TRADES, settings.ACCOUNTS)):
            before = deepcopy(records)
            context = dict(tick=0, received_at=self.start, ingested_at=self.start, params=params)
            self.assertEqual(module.parse_record(records[0], **context), module.parse_record(records[0], **context))
            self.assertEqual(records, before)

    def test_news_header_edges(self):
        cases = [
            ("  SyMbOlS : ALPHA, BETA, ALPHA\r\n", (["ALPHA", "BETA"], "ok", [])),
            ("Symbols: \n", ([], "empty", [])),
            ("Symbols: ALPHA,\n", ([], "malformed", [])),
            ("Symbols: ALPHA\nSymbols: BETA\n", ([], "malformed", [])),
            ("Symbols: ALPHA BETA\n", ([], "malformed", [])),
            ("Symbols: ALPHA, UNKNOWN\n", (["ALPHA"], "unknown_symbols", ["UNKNOWN"])),
            ("", ([], "missing", [])),
        ]
        for header, expected in cases:
            with self.subTest(header=header):
                raw = 'News-ID: test\nPublished-At: 2026-10-26T09:00:00Z\nTitle: 中文\n' + header + 'Body: 第一行\nSymbols: BETA\n'
                record = news.parse_record(raw, tick=0, received_at=self.start, ingested_at=self.start, params=settings.NEWS)
                self.assertEqual((record["symbols"], record["symbol_status"], record["unrecognized_symbols"]), expected)
                self.assertEqual(record["raw_text"], raw)

    def test_each_folder_can_be_copied_and_used_alone(self):
        examples = {
            "market": ("MarketParams", {"instrument_id": "ALPHA", "bid_cents": 100, "ask_cents": 102, "bid_size": 10, "ask_size": 10}),
            "trades": ("TradeParams", {"trade_id": "t1", "team_id": "A", "instrument_id": "ALPHA", "side": "BUY", "quantity": 1, "price_cents": 102, "fee_cents": 0}),
            "accounts": ("AccountParams", {"team_id": "A", "cash_cents": 100, "positions": {"ALPHA": 1}, "equity_cents": 201, "pnl_cents": 1}),
        }
        for name, (config_class, sample) in examples.items():
            with self.subTest(module=name):
                isolated = self.root / name
                isolated.mkdir()
                shutil.copytree(Path(__file__).parent / name, isolated / name, ignore=shutil.ignore_patterns("__pycache__", "mock.py"))
                script = (
                    f"import {name} as module\nimport duckdb\nfrom datetime import datetime, timezone\n"
                    "now = datetime.now(timezone.utc)\ndb = duckdb.connect()\nmodule.create_table(db)\n"
                    f"record = {sample!r}\nrecord['event_time'] = now\n"
                    f"module.write_records(db, [record], tick=0, received_at=now, ingested_at=now, params=module.{config_class}())\n"
                    "module.export_parquet(db, 'sample.parquet', start_tick=0, end_tick=1)\n"
                    "assert db.execute(\"SELECT count(*) FROM 'sample.parquet'\").fetchall() == [(1,)]\n"
                )
                subprocess.run([sys.executable, "-c", script], cwd=isolated, check=True, capture_output=True, text=True)
        isolated = self.root / "news_only"
        isolated.mkdir()
        shutil.copytree(Path(__file__).parent / "news", isolated / "news", ignore=shutil.ignore_patterns("__pycache__", "mock.py"))
        script = "import news\nfrom datetime import datetime, timezone\nnow=datetime.now(timezone.utc)\nraw='News-ID: n1\\nPublished-At: 2026-10-26T09:00:00Z\\nTitle: 中文\\nSymbols: ALPHA\\nBody: 新闻\\n'\nassert news.write_records('news.jsonl', [raw], tick=0, received_at=now, ingested_at=now, params=news.NewsParams()) == 1\n"
        subprocess.run([sys.executable, "-c", script], cwd=isolated, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
