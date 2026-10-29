"""Count invariants, stage isolation and input boundaries for native stack reports."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import validate_profile
from profiling.parse_sample import parse_report

REPORT='''Header
Call graph:
    100 Thread_1
    + 100 main (in worker)
    +   80 profile_account_value() (in worker)
    +   ! 60 recursive() (in worker)
    +   ! : 40 recursive() (in worker)
    +   ! : | 30 malloc (in system)
    +   ! 20 wait() (in system)
    +   20 unrelated() (in worker)
    100 Thread_2
      100 background() (in worker)

Total number in stack (recursive counted multiple, when >=5):
'''

class ProfileTests(unittest.TestCase):
    def test_marker_isolation_recursion_and_self_conservation(self):
        result=parse_report(REPORT,'profile_account_value')
        self.assertEqual(result['stage_samples'],80)
        self.assertEqual(result['all_thread_samples'],200)
        functions={f['name']:f for f in result['functions']}
        self.assertNotIn('unrelated()',functions)
        self.assertNotIn('background()',functions)
        self.assertEqual(functions['recursive()']['inclusive_samples'],60)
        self.assertEqual(functions['recursive()']['self_samples'],30)
        self.assertEqual(functions['wait()']['self_samples'],20)
        self.assertEqual(sum(f['self_samples'] for f in functions.values()),80)
        self.assertEqual(sum(result['folded'].values()),80)

    def test_missing_or_inconsistent_marker_is_not_a_zero_or_whole_process_result(self):
        for report,marker in [(REPORT,'absent'),('no stacks','profile_account_value'),(REPORT.replace('80 profile_','40 profile_'),'profile_account_value')]:
            with self.assertRaises(ValueError): parse_report(report,marker)

    def test_stage_whitelist_and_bounded_duration(self):
        self.assertEqual(validate_profile({})['seconds'],3)
        self.assertEqual(validate_profile({'stages':['market_write'],'seconds':10})['stages'],['market_write'])
        for invalid in [None,[],{'seconds':True},{'seconds':0},{'seconds':11},{'seconds':1.5},{'stages':[]},{'stages':'market_write'},{'stages':['market_write']*2},{'stages':['../market_write']},{'stages':[{}]}]:
            with self.assertRaises(ValueError): validate_profile(invalid)

if __name__=='__main__': unittest.main(verbosity=2)
