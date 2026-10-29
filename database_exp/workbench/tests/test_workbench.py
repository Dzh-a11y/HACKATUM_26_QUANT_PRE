"""Contract tests use real binaries, real storage and the existing independent verifier."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from app import validate_config, safe_json, trace_summary
from catalog import catalog, CPP
from probe import snapshot,difference
sys.path.insert(0,str(CPP))
from generate_fixture import generate
from verify_pair import verify_pair
from verify_run import verify
import duckdb

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='database-workbench-test-')
        self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def fixture(self,seconds=6,symbols=5,teams=3):
        path=self.root/'fixture.json'
        generate(path,seconds=seconds,symbols=symbols,teams=teams,export_every=4)
        return path
    def command(self,fixture,mode='fast'):
        return [str(HERE/'build/observe_cpp'),str(fixture),str(self.root/'observed'),'2','1GB',mode]
    def test_schema_from_owning_ddl(self):
        tables={t['name']:t for t in catalog()}
        self.assertEqual({name:len(t['columns']) for name,t in tables.items()},dict(market_quotes=11,team_trades=13,account_snapshots=10,quotes_batch=9,**{'news.jsonl':13}))
        market=tables['market_quotes']
        self.assertEqual([c['name'] for c in market['columns'] if c['primary']],['tick','instrument_id','venue'])
        self.assertTrue(any(c['type']=='CHECK' and 'ask_cents' in c['text'] for c in market['constraints']))
        self.assertFalse(tables['news.jsonl']['constraints'])
    def test_probe_returns_actual_counter_deltas_or_null(self):
        before=snapshot()
        sum(i*i for i in range(200000))
        metrics=difference(before,snapshot())
        self.assertGreater(metrics['wall_ms'],0)
        if metrics['cycles'] is not None:
            self.assertGreater(metrics['cycles'],0); self.assertGreater(metrics['instructions'],0)
        self.assertIsNone(metrics['cache_misses']); self.assertIsNone(metrics['branch_misses'])
    def test_config_and_lossless_large_integer(self):
        self.assertEqual(validate_config({})['seed'],42)
        for invalid in [{'ticks':True},{'symbols':2001},{'ticks':600,'symbols':2000},{'compare':'yes'},{'mode':'shell'}]:
            with self.assertRaises(ValueError): validate_config(invalid)
        self.assertEqual(safe_json({'cash':2**63-1})['cash'],str(2**63-1))
    def test_observer_matches_python_and_parquet(self):
        fixture=self.fixture()
        subprocess.run(self.command(fixture),check=True,capture_output=True)
        subprocess.run([sys.executable,str(CPP/'python_worker.py'),'--input',str(fixture),'--output',str(self.root/'python'),'--threads','2','--memory-limit','1GB'],check=True,capture_output=True)
        verify_pair(fixture,self.root/'python',self.root/'observed')
        summary=trace_summary(self.root)
        self.assertEqual(summary['stages']['txn_commit']['calls'],6)
        self.assertEqual(summary['stages']['market_write']['rows'],30)
        self.assertEqual(summary['stages']['parquet_export']['calls'],2)
        self.assertNotIn('txn_rollback',summary['stages'])
        self.assertTrue(all(s['wall_ms']>=0 for s in summary['stages'].values()))
    def test_realtime_stop_publishes_committed_tail(self):
        fixture=self.fixture(seconds=12)
        started=time.monotonic()
        process=subprocess.Popen(self.command(fixture,'realtime'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                trace=self.root/'observed/trace.jsonl'
                if trace.exists() and '"committed_ticks":2' in trace.read_text(): break
                time.sleep(.05)
            else: self.fail('No second commit observed')
            process.send_signal(signal.SIGTERM)
            stdout,stderr=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,stderr.decode())
            info=json.loads((self.root/'observed/run.json').read_text())
            self.assertEqual(info['status'],'stopped')
            self.assertEqual(info['mode'],'paced-fixture')
            self.assertGreaterEqual(time.monotonic()-started,.95)
            self.assertGreaterEqual(info['committed_ticks'],2)
            self.assertLess(info['committed_ticks'],12)
            verify(self.root/'observed')
            self.assertGreater(trace_summary(self.root)['stages']['pace_wait']['wall_ms'],0)
        finally:
            if process.poll() is None: process.kill(); process.wait()
    def test_failure_rolls_back_tables_and_reports_error(self):
        fixture=self.fixture()
        data=json.loads(fixture.read_text())
        data['ticks'][0]['trades'].append(data['ticks'][0]['trades'][0])
        fixture.write_text(json.dumps(data))
        result=subprocess.run(self.command(fixture),capture_output=True)
        self.assertNotEqual(result.returncode,0)
        info=json.loads((self.root/'observed/run.json').read_text())
        self.assertEqual(info['status'],'failed')
        self.assertEqual(info['committed_ticks'],0)
        with duckdb.connect(str(self.root/'observed/market.duckdb'),read_only=True) as db:
            for table in ['market_quotes','team_trades','account_snapshots']:
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
        self.assertEqual(trace_summary(self.root)['stages']['txn_rollback']['calls'],1)

if __name__=='__main__': unittest.main(verbosity=2)
