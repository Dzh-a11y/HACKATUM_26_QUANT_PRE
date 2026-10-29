"""One isolated run; all generated data stays in workbench/output/<run-id>."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from catalog import CPP, HERE, source_hashes
from probe import difference, snapshot
from build import build

child = None
stopping = False

def stop(_signum, _frame):
    global stopping
    stopping = True
    if child and child.poll() is None:
        child.send_signal(signal.SIGTERM)

def write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    tmp.replace(path)

def execute(command, log, graceful=False):
    global child
    if stopping:
        raise InterruptedError('用户已停止实验')
    child = subprocess.Popen([str(x) for x in command],stdout=log,stderr=log)
    code = child.wait()
    child = None
    if code and not (graceful and stopping):
        raise RuntimeError(f'实验进程退出码 {code}；请查看运行日志')

def main(directory):
    directory = Path(directory)
    config = json.loads((directory/'config.json').read_text())
    job = dict(id=directory.name,config=config,status='running',phase='generate',created_at=datetime.now(timezone.utc).isoformat())
    write_json(directory/'job.json',job)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    start = time.perf_counter()
    try:
        # Refresh build/provenance before generation; editing only the UI needs no native rebuild.
        job['phase']='build'; write_json(directory/'job.json',job)
        provenance=build()
        job['phase']='generate'; write_json(directory/'job.json',job)
        sys.path.insert(0,str(CPP))
        from generate_fixture import generate
        fixture = directory/'fixture.json'
        before = snapshot()
        digest = generate(fixture,seconds=config['ticks'],symbols=config['symbols'],teams=config['teams'],step=1,export_every=config['export_every'])
        generation = difference(before,snapshot())
        write_json(directory/'generation.json',dict(stage='generate',metrics=generation,rows=config['ticks']*config['symbols'],sha256=digest))
        job.update(fixture_sha256=digest,phase='observe')
        current=source_hashes()
        if any(current.get(name)!=digest for name,digest in provenance['native_source_hashes'].items()):
            raise RuntimeError('C++ 源码在构建期间变化，请重新运行实验')
        provenance['source_hashes']=current
        write_json(directory/'provenance.json',provenance)
        write_json(directory/'job.json',job)
        with (directory/'worker.log').open('w') as log:
            execute([HERE/'build/observe_cpp',fixture,directory/'observed',config['threads'],'1GB',config['mode']],log,graceful=True)
            observed = json.loads((directory/'observed/run.json').read_text())
            if observed['status'] == 'failed':
                raise RuntimeError(observed.get('error','C++ 处理失败'))
            job.update(phase='verify',status='stopping' if stopping else 'running')
            write_json(directory/'job.json',job)
            # Validation runs after the writer closes. Stop does not skip validating a committed tail.
            command = [sys.executable,HERE.parent/'stream_ingestion/verify_run.py',directory/'observed']
            verified = subprocess.run([str(x) for x in command],stdout=log,stderr=log)
            job['validation'] = dict(passed=verified.returncode==0,scope='当前已提交三表、账户独立重放、Parquet 批次及新闻记录')
            if verified.returncode:
                raise RuntimeError('输出校验未通过；请查看运行日志')
            if config['compare'] and not stopping:
                job['phase']='baseline'; write_json(directory/'job.json',job)
                # Both baseline timings exclude detailed instrumentation and use the exact same fixture.
                execute([HERE/'build/original/ingest_cpp','--input',fixture,'--output',directory/'baseline_cpp','--fast','--threads',config['threads'],'--memory-limit','1GB'],log)
                execute([sys.executable,CPP/'python_worker.py','--input',fixture,'--output',directory/'baseline_python','--threads',config['threads'],'--memory-limit','1GB'],log)
                execute([sys.executable,CPP/'verify_pair.py',fixture,directory/'baseline_python',directory/'baseline_cpp'],log)
                execute([sys.executable,CPP/'verify_pair.py',fixture,directory/'baseline_python',directory/'observed'],log)
                summaries = {key:json.loads((directory/path/'run.json').read_text()) for key,path in [('cpp','baseline_cpp'),('python','baseline_python')]}
                if summaries['cpp']['source_id'] != summaries['python']['source_id']:
                    raise RuntimeError('C++ / Python DuckDB 引擎 source_id 不同，不能作为同引擎对照')
                write_json(directory/'comparison.json',dict(passed=True,runs=summaries,note='单次串行运行、同一输入、两版均无详细埋点；仅供探索，不代表稳定性能结论。'))
            job.update(status='stopped' if stopping or observed['status']=='stopped' else 'completed',phase='done')
    except InterruptedError:
        job.update(status='stopped',phase='done')
    except Exception as error:
        job.update(status='stopped' if stopping else 'failed',error=str(error),phase='done')
    finally:
        job['elapsed_seconds']=time.perf_counter()-start
        write_json(directory/'job.json',job)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory')
    main(parser.parse_args().directory)

