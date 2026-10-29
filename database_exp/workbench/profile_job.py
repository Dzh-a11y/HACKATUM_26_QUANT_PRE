"""Profile three original stages using macOS sample; never invoke sudo."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from catalog import HERE, source_hashes
from job import write_json
from profiling.parse_sample import parse_report

STAGES={'account_value':'账户估值','accounts_transform':'账户转列','market_write':'行情写入'}
children=[]
stopping=False

def stop(signum,frame):
    global stopping
    stopping=True
    for process in children:
        if process.poll() is None: process.terminate()

def build_profiler():
    root=HERE/'profiling'; folder=root/'build'; folder.mkdir(exist_ok=True)
    with (folder/'build.log').open('a') as log:
        for command in [['cmake','-S',root,'-B',folder,'-DCMAKE_BUILD_TYPE=Release'],
                        ['cmake','--build',folder,'--target','profile_stage','-j','4']]:
            subprocess.run([str(x) for x in command],stdout=log,stderr=log,check=True)
    binary=folder/'profile_stage'
    # dSYM makes optimized functions and inline source locations discoverable by sample.
    dsym=binary.with_suffix('.dSYM')
    if not dsym.exists() or dsym.stat().st_mtime<binary.stat().st_mtime:
        subprocess.run(['dsymutil',str(binary),'-o',str(dsym)],check=True,capture_output=True,text=True)
    return binary

def profile(source,output):
    source,output=Path(source),Path(output)
    config=json.loads((output/'config.json').read_text())
    source_job=json.loads((source/'job.json').read_text())
    fixture=source/'fixture.json'
    job=dict(id=output.name,source_run=source.name,status='running',phase='build',config=config,
             source_config=source_job['config'],created_at=datetime.now(timezone.utc).isoformat(),results={})
    write_json(output/'job.json',job)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    try:
        before=source_hashes()
        binary=build_profiler()
        after=source_hashes()
        if before!=after: raise RuntimeError('构建期间源码发生变化，请重新采样')
        job['provenance']=dict(source_hashes=after,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
            compiler=subprocess.check_output(['c++','--version'],text=True).strip(),
            flags='Release -O3 -g -fno-omit-frame-pointer; marker wrappers noinline / no sibling calls',
            command_template='/usr/bin/sample <this-experiment-pid> <seconds> 1 -mayDie -fullPaths -file <stage>.sample.txt')
        for stage in config['stages']:
            if stopping: break
            job['phase']=stage; write_json(output/'job.json',job)
            folder=output/stage
            raw=output/(stage+'.sample.txt')
            with (output/(stage+'.worker.log')).open('w') as log:
                worker=subprocess.Popen([str(binary),str(fixture),str(folder),stage,str(source_job['config']['threads'])],stdout=log,stderr=log)
                children.append(worker)
                try:
                    deadline=time.monotonic()+15
                    while not (folder/'ready.json').exists():
                        if stopping or worker.poll() is not None: raise RuntimeError('阶段进程未能启动，请查看 worker 日志')
                        if time.monotonic()>deadline: raise RuntimeError('阶段初始化超时')
                        time.sleep(.05)
                    command=['/usr/bin/sample',str(worker.pid),str(config['seconds']),'1','-mayDie','-fullPaths','-file',str(raw)]
                    sampler=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    children.append(sampler)
                    out,err=sampler.communicate(timeout=config['seconds']+30)
                    (output/(stage+'.sampler.log')).write_text(out+err)
                    (folder/'stop.flag').touch()
                    worker.wait(timeout=10)
                    if stopping: break
                    if sampler.returncode:
                        raise RuntimeError('macOS sample 未获进程采样权限或采样失败。请在普通终端运行 launch.sh 后重试；程序不会自动使用 sudo。详见 sampler 日志。')
                    if worker.returncode:
                        raise RuntimeError('阶段重复运行失败，请查看 worker 日志')
                    result=parse_report(raw.read_text(), 'profile_'+stage)
                    worker_info=json.loads((folder/'worker.json').read_text())
                    result.update(stage=stage,title=STAGES[stage],worker=worker_info,
                                  sample_interval_ms=1,requested_seconds=config['seconds'],raw_file=raw.name,
                                  scenario='重复该运行 fixture 的第 0 轮；行情写入使用原约束，并在标记函数外回滚事务以限制数据量。')
                    write_json(output/(stage+'.json'),result)
                    (output/(stage+'.folded')).write_text('\n'.join(f'{stack} {count}' for stack,count in result['folded'].items())+'\n')
                    job['results'][stage]=result
                    write_json(output/'job.json',job)
                finally:
                    for process in children:
                        if process.poll() is None:
                            process.terminate()
                            try: process.wait(timeout=5)
                            except subprocess.TimeoutExpired: process.kill(); process.wait()
                    children.clear()
        job.update(status='stopped' if stopping else 'completed',phase='done')
    except Exception as error:
        job.update(status='stopped' if stopping else 'failed',phase='done',error=str(error))
    finally:
        for process in children:
            if process.poll() is None: process.terminate()
        write_json(output/'job.json',job)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source');parser.add_argument('output')
    args=parser.parse_args()
    profile(args.source,args.output)
