"""Shutdown must remove owned descendants even when they ignore graceful termination."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class ShutdownTests(unittest.TestCase):
    def test_owned_process_group_is_killed_and_unrelated_process_survives(self):
        # Both members ignore SIGTERM, exercising the bounded SIGKILL fallback.
        script='''import os,signal,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child: print(child,flush=True)
while True: time.sleep(1)
'''
        owner=subprocess.Popen([sys.executable,'-c',script],start_new_session=True,stdout=subprocess.PIPE,text=True)
        sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
        try:
            descendant=int(owner.stdout.readline())
            with tempfile.TemporaryDirectory() as temp:
                folder=Path(temp)/'test-run';folder.mkdir()
                (folder/'job.json').write_text(json.dumps({'status':'running'}))
                with patch.object(app,'ACTIVE',('test-run',owner)),patch.object(app,'OUTPUT',Path(temp)):
                    app.stop_active(grace_seconds=.1,terminate_seconds=.1)
                self.assertEqual(json.loads((folder/'job.json').read_text())['status'],'interrupted')
            self.assertEqual(owner.returncode,-signal.SIGKILL)
            self.assertIsNone(sentinel.poll())
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                try: os.kill(descendant,0)
                except ProcessLookupError: break
                time.sleep(.05)
            else: self.fail('Owned descendant remained alive after shutdown')
        finally:
            try: os.killpg(owner.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            owner.wait();owner.stdout.close()
            sentinel.terminate();sentinel.wait()

if __name__=='__main__': unittest.main(verbosity=2)
