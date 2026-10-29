"""Loopback-only experiment API and buildless front end; no arbitrary command or SQL endpoint."""
import argparse
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
import uuid

import duckdb
from build import build
from catalog import bootstrap, HERE, ROOT, source_files
from profile_job import STAGES

OUTPUT = HERE/'output'
LOCK = threading.Lock()
ACTIVE = None
BOOT = None
SHUTTING_DOWN = threading.Event()

def stop_active(grace_seconds=15, terminate_seconds=2):
    """Stop only our current job and its private process group, including build tools."""
    if not ACTIVE or ACTIVE[1].poll() is not None: return
    process=ACTIVE[1]
    # Let the coordinator stop the writer and finish its output first.
    process.terminate()
    try: process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired: pass
    def group_signal(sig):
        try: os.killpg(process.pid,sig); return True
        except ProcessLookupError: return False
    if group_signal(signal.SIGTERM):
        deadline=time.monotonic()+terminate_seconds
        while time.monotonic()<deadline and group_signal(0): time.sleep(.05)
        if group_signal(0): group_signal(signal.SIGKILL)
    process.wait(timeout=5)
    # A forced exit must not leave a permanent "running" record in history.
    for path in [OUTPUT/ACTIVE[0]/'job.json',OUTPUT/'profiles'/ACTIVE[0]/'job.json']:
        value=read_json(path,{})
        if value.get('status') in {'running','stopping'}:
            value.update(status='interrupted',phase='done',error='实验台关闭时终止了任务；已落盘文件保留')
            path.write_text(json.dumps(value,ensure_ascii=False))

def safe_json(value):
    if isinstance(value,dict): return {str(k):safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [safe_json(v) for v in value]
    if isinstance(value,int) and abs(value)>9007199254740991: return str(value)
    return value

def read_json(path, default=None):
    try: return json.loads(path.read_text())
    except FileNotFoundError: return default

def directory(id, profiles=False):
    if not re.fullmatch(r'[0-9a-f]{12}',id): raise ValueError('无效运行 ID')
    path = (OUTPUT/'profiles' if profiles else OUTPUT)/id
    if not path.is_dir(): raise ValueError('运行不存在')
    return path

def validate_config(data):
    fields = {'ticks':(1,600,12),'symbols':(1,2000,32),'teams':(1,32,2),'threads':(1,16,1),'export_every':(1,600,5)}
    result = {}
    for key,(low,high,default) in fields.items():
        value = data.get(key,default)
        if type(value) is not int or not low<=value<=high: raise ValueError(f'{key} 需要是 {low}–{high} 的整数')
        result[key]=value
    if result['ticks']*result['symbols']>100000 or result['ticks']*result['symbols']*result['teams']>500000:
        raise ValueError('请减小本次规模：行情总行数 ≤ 100,000，轮次 × 标的 × 团队 ≤ 500,000')
    if data.get('mode','fast') not in {'fast','realtime'}: raise ValueError('无效回放模式')
    if type(data.get('compare',False)) is not bool: raise ValueError('compare 必须是布尔值')
    result.update(mode=data.get('mode','fast'),compare=data.get('compare',False),seed=42)
    return result

def list_runs():
    result=[]
    for path in sorted(OUTPUT.glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        item=read_json(path)
        if item: result.append(item)
    return result[:100]

def validate_profile(data):
    if not isinstance(data,dict): raise ValueError('采样参数必须是对象')
    seconds=data.get('seconds',3)
    stages=data.get('stages',list(STAGES))
    if type(seconds) is not int or not 1<=seconds<=10: raise ValueError('每阶段采样时长需要是 1–10 秒的整数')
    if not isinstance(stages,list) or not stages or any(not isinstance(s,str) or s not in STAGES for s in stages) or len(set(stages))!=len(stages):
        raise ValueError('请选择不重复的账户估值、账户转列或行情写入阶段')
    return dict(seconds=seconds,stages=stages)

def list_profiles():
    result=[]
    for path in sorted((OUTPUT/'profiles').glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        item=read_json(path)
        if item:
            result.append({k:v for k,v in item.items() if k not in {'results','provenance'}})
    return result[:100]

def trace_summary(folder):
    events=[]
    generation=read_json(folder/'generation.json')
    if generation: events.append(dict(kind='end',stage='generate',tick=-1,**{k:generation[k] for k in ['rows','metrics']}))
    path=folder/'observed/trace.jsonl'
    if path.exists():
        with path.open() as file:
            for line in file:
                try: events.append(json.loads(line))
                except json.JSONDecodeError: pass  # A writer may be in the middle of the final line.
    stages={}
    for event in events:
        if event['kind']!='end': continue
        stage=stages.setdefault(event['stage'],dict(calls=0,rows=0,wall_ms=0,user_ms=0,system_ms=0,minor_faults=0,major_faults=0,voluntary_switches=0,involuntary_switches=0,cycles=0,instructions=0,samples=[],counter_samples=0))
        m=event['metrics']; stage['calls']+=1; stage['rows']+=event.get('rows',0)
        for key in ['wall_ms','user_ms','system_ms','minor_faults','major_faults','voluntary_switches','involuntary_switches']:
            stage[key]+=m[key]
        if m['cycles'] is not None and m['instructions'] is not None:
            stage['cycles']+=m['cycles']; stage['instructions']+=m['instructions']; stage['counter_samples']+=1
        stage['samples'].append(m['wall_ms']); stage['last']=m
    for stage in stages.values():
        samples=sorted(stage['samples'])
        stage.update(p50_ms=samples[(len(samples)-1)//2],p95_ms=samples[max(0,math.ceil(len(samples)*.95)-1)])
        if stage['counter_samples']!=stage['calls']: stage['cycles']=stage['instructions']=None
        stage['ipc']=stage['instructions']/stage['cycles'] if stage['cycles'] else None
    return dict(stages=stages,events=events[-50:],event_count=len(events),current=events[-1] if events else None)

def output_data(folder, table):
    if table=='news.jsonl':
        path=folder/'observed/news.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()[:50]] if path.exists() else []
    allowed={'market_quotes':'tick, instrument_id, venue','team_trades':'tick, trade_id','account_snapshots':'tick, team_id'}
    if table not in allowed: raise ValueError('该表不属于当前流式运行；quotes_batch 是独立示例的内存表')
    job=read_json(folder/'job.json',{})
    if job.get('status') not in {'completed','stopped','failed'}:
        return dict(pending=True,message='写入进程正在持有 DuckDB。完成或停止后提供最终表预览；当前可查看输入和性能。')
    path=folder/'observed/market.duckdb'
    if not path.exists(): return []
    with duckdb.connect(str(path),read_only=True,config={'threads':1}) as db:
        db.execute("SET TimeZone='UTC'")
        cursor=db.execute(f'SELECT * FROM {table} ORDER BY {allowed[table]} LIMIT 50')
        names=[x[0] for x in cursor.description]
        return [dict(zip(names,row)) for row in cursor.fetchall()]

class Handler(BaseHTTPRequestHandler):
    server_version='DatabaseWorkbench/1'
    def log_message(self,fmt,*args): pass
    def send(self,value,status=200):
        content=json.dumps(safe_json(value),ensure_ascii=False,default=str).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)
    def same_host(self):
        expected={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in expected: return False
        origin=self.headers.get('Origin')
        return origin is None or origin in {f'http://{host}' for host in expected}
    def do_GET(self):
        if not self.same_host(): return self.send({'error':'只接受本机同源请求'},403)
        parsed=urlparse(self.path); query={k:v[0] for k,v in parse_qs(parsed.query).items()}
        try:
            if parsed.path=='/api/bootstrap': return self.send(BOOT)
            if parsed.path=='/api/status': return self.send({'status':'closing' if SHUTTING_DOWN.is_set() else 'running'})
            if parsed.path=='/api/runs': return self.send(list_runs())
            if parsed.path=='/api/profiles': return self.send(list_profiles())
            if parsed.path=='/api/profile':
                return self.send(read_json(directory(query['id'],profiles=True)/'job.json'))
            if parsed.path=='/api/profile-file':
                folder=directory(query['id'],profiles=True)
                stage=query.get('stage'); kind=query.get('kind')
                if stage not in STAGES or kind not in {'sample.txt','folded','sampler.log','worker.log'}:
                    raise ValueError('无效采样文件')
                path=folder/(stage+'.'+kind)
                if not path.is_file(): raise ValueError('该采样文件尚未生成')
                content=path.read_bytes()
                self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Content-Disposition',f'attachment; filename="{query["id"]}-{stage}.{kind}"')
                self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)
                return
            if parsed.path=='/api/state':
                folder=directory(query['id'])
                return self.send(dict(job=read_json(folder/'job.json'),run=read_json(folder/'observed/run.json'),
                    trace=trace_summary(folder),comparison=read_json(folder/'comparison.json'),generation=read_json(folder/'generation.json'),
                    log=(folder/'worker.log').read_text(errors='replace')[-18000:] if (folder/'worker.log').exists() else '',
                    path=str(folder),provenance=read_json(folder/'provenance.json')))
            if parsed.path=='/api/data':
                folder=directory(query['id'])
                if query.get('kind')=='input':
                    fixture=read_json(folder/'fixture.json')
                    if fixture is None: return self.send(dict(pending=True,message='正在生成输入'))
                    tick=int(query.get('tick',0))
                    if not 0<=tick<len(fixture['ticks']): raise ValueError('tick 超出输入范围')
                    return self.send(dict(metadata=fixture['metadata'],tick=fixture['ticks'][tick],sha256=hashlib.sha256((folder/'fixture.json').read_bytes()).hexdigest(),bytes=(folder/'fixture.json').stat().st_size))
                return self.send(output_data(folder,query.get('table','market_quotes')))
            if parsed.path=='/api/source':
                path=source_files().get(query.get('file'))
                if not path: raise ValueError('文件不在源码白名单内')
                return self.send(dict(file=query['file'],text=path.read_text(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            if parsed.path=='/api/report':
                folder=directory(query['id'])
                return self.send(dict(job=read_json(folder/'job.json'),run=read_json(folder/'observed/run.json'),trace=trace_summary(folder),
                    comparison=read_json(folder/'comparison.json'),provenance=read_json(folder/'provenance.json')))
            path=HERE/'dist'/('index.html' if parsed.path=='/' else parsed.path.lstrip('/'))
            if path.resolve().parent!=(HERE/'dist').resolve() or not path.is_file(): return self.send({'error':'页面不存在'},404)
            content=path.read_bytes()
            self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(content))); self.send_header('Cache-Control','no-cache'); self.end_headers(); self.wfile.write(content)
        except (ValueError,KeyError) as error: self.send({'error':str(error)},400)
        except Exception as error: self.send({'error':str(error)},500)
    def do_POST(self):
        global ACTIVE
        if not self.same_host(): return self.send({'error':'只接受本机同源请求'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096: raise ValueError('请求大小无效')
            data=json.loads(self.rfile.read(length))
            if self.path=='/api/shutdown':
                with LOCK:
                    first=not SHUTTING_DOWN.is_set()
                    SHUTTING_DOWN.set()
                try:
                    self.send({'status':'closing'},202)
                    self.wfile.flush()
                finally:
                    if first: threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if self.path=='/api/profile':
                if sys.platform!='darwin': raise ValueError('当前采样适配器需要 macOS sample')
                config=validate_profile(data)
                source=directory(data.get('source_run',''))
                if read_json(source/'job.json',{}).get('status')!='completed' or not (source/'fixture.json').is_file():
                    raise ValueError('请选择已有完整输入的已完成实验')
                with LOCK:
                    if SHUTTING_DOWN.is_set(): return self.send({'error':'实验台正在关闭'},503)
                    if ACTIVE and ACTIVE[1].poll() is None: return self.send({'error':'已有实验或采样运行中，请先停止或等待完成'},409)
                    id=uuid.uuid4().hex[:12]; folder=OUTPUT/'profiles'/id; folder.mkdir(parents=True)
                    (folder/'config.json').write_text(json.dumps(config))
                    (folder/'job.json').write_text(json.dumps(dict(id=id,source_run=source.name,config=config,status='running',phase='starting',results={})))
                    with (folder/'coordinator.log').open('w') as log:
                        process=subprocess.Popen([sys.executable,str(HERE/'profile_job.py'),str(source),str(folder)],stdout=log,stderr=log,start_new_session=True)
                    ACTIVE=(id,process)
                return self.send({'id':id},201)
            if self.path=='/api/run':
                config=validate_config(data)
                with LOCK:
                    if SHUTTING_DOWN.is_set(): return self.send({'error':'实验台正在关闭'},503)
                    if ACTIVE and ACTIVE[1].poll() is None: return self.send({'error':'已有实验运行中，请先停止或等待完成'},409)
                    id=uuid.uuid4().hex[:12]; folder=OUTPUT/id; folder.mkdir(parents=True)
                    (folder/'config.json').write_text(json.dumps(config))
                    (folder/'job.json').write_text(json.dumps(dict(id=id,config=config,status='running',phase='starting')))
                    with (folder/'coordinator.log').open('w') as log:
                        process=subprocess.Popen([sys.executable,str(HERE/'job.py'),str(folder)],stdout=log,stderr=log,start_new_session=True)
                    ACTIVE=(id,process)
                return self.send({'id':id},201)
            if self.path=='/api/stop':
                with LOCK:
                    if ACTIVE and ACTIVE[0]==data.get('id') and ACTIVE[1].poll() is None:
                        ACTIVE[1].send_signal(signal.SIGTERM)
                        return self.send({'status':'stopping'})
                return self.send({'error':'该实验当前没有运行'},409)
            self.send({'error':'未知接口'},404)
        except (ValueError,TypeError,KeyError) as error: self.send({'error':str(error)},400)
        except Exception as error: self.send({'error':str(error)},500)

def main():
    global BOOT
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    ownership=(OUTPUT/'.server.lock').open('a')
    try:
        fcntl.flock(ownership,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('实验台服务已经运行；请使用已有页面，或停止旧服务后重启。')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print('Building observer and reading source evidence…',flush=True)
    build(); BOOT=bootstrap()
    # A server restart cannot claim an orphaned run is still actively managed.
    for path in [*OUTPUT.glob('*/job.json'),*(OUTPUT/'profiles').glob('*/job.json')]:
        value=read_json(path,{})
        if value.get('status') in {'running','stopping'}:
            value.update(status='interrupted',error='上次服务已退出；请检查该运行文件后重新实验')
            path.write_text(json.dumps(value,ensure_ascii=False))
    print(f'Local: http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        with LOCK: SHUTTING_DOWN.set()
        try: stop_active()
        finally: server.server_close()

if __name__=='__main__': main()

