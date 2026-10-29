"""Read schema and evidence from the owning source; no maintained schema copy."""
import ast
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess

import duckdb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CPP = HERE.parent / 'stream_ingestion_cpp'
PYTHON = HERE.parent / 'stream_ingestion'

STAGES = [
    ('generate', 'Python 数据生成', 'Python / NumPy → 同一份 fixture', 'stream_ingestion_cpp/generate_fixture.py', 'def generate('),
    ('input_decode', '读取与解码', 'JSON 文件 → 内存记录', 'stream_ingestion_cpp/pipeline.cpp', 'Json fixture;'),
    ('db_init', '数据库初始化', '连接、时区、三张表与约束', 'stream_ingestion_cpp/pipeline.cpp', 'void create_tables('),
    ('account_fills', '成交更新持仓', '逐笔累加，整数溢出检查', 'stream_ingestion_cpp/accounts/calculate.cpp', 'State apply_fills('),
    ('account_value', '账户估值', '现金、持仓、市值、PnL', 'stream_ingestion_cpp/accounts/calculate.cpp', 'support::Json value_accounts('),
    ('news_parse', '新闻解析', '头部、Symbols、原文 → JSON', 'stream_ingestion_cpp/news/parser.cpp', 'support::Json parse_record('),
    ('news_write', 'JSONL 写入', '追加、flush、fsync；独立于三表事务', 'stream_ingestion_cpp/news/writer.cpp', 'size_t write_records('),
    ('txn_begin', '开启事务', 'BEGIN TRANSACTION', 'stream_ingestion_cpp/pipeline.cpp', 'void write_tick('),
    ('market_transform', '行情转列', '行情记录 → 列缓冲区', 'stream_ingestion_cpp/market/transform.cpp', 'records_to_columns('),
    ('market_write', '行情写入', 'DataChunk → market_quotes', 'stream_ingestion_cpp/market/storage.cpp', 'size_t write_columns('),
    ('trades_transform', '成交转列', '成交记录 → 列缓冲区', 'stream_ingestion_cpp/trades/transform.cpp', 'records_to_columns('),
    ('trades_write', '成交写入', 'DataChunk → team_trades', 'stream_ingestion_cpp/trades/storage.cpp', 'size_t write_columns('),
    ('accounts_transform', '账户转列', '账户记录 → 列缓冲区', 'stream_ingestion_cpp/accounts/transform.cpp', 'records_to_columns('),
    ('accounts_write', '账户写入', 'DataChunk → account_snapshots', 'stream_ingestion_cpp/accounts/storage.cpp', 'size_t write_columns('),
    ('txn_commit', '提交事务', '三表一起 COMMIT', 'stream_ingestion_cpp/pipeline.cpp', '"COMMIT"'),
    ('state_advance', '推进内存状态', 'COMMIT 成功后推进', 'stream_ingestion_cpp/pipeline.cpp', 'state = std::move(next)'),
    ('pace_wait', '回放节拍等待', '独立展示，不计入处理耗时', 'stream_ingestion_cpp/pipeline.cpp', 'std::this_thread::sleep_until'),
    ('parquet_export', 'Parquet 归档', '三表 → ZSTD → manifest → 目录发布', 'stream_ingestion_cpp/pipeline.cpp', 'std::string export_batch('),
    ('db_close', '关闭数据库', '连接与数据库 RAII 释放', 'stream_ingestion_cpp/support/db.hpp', '~Database()'),
    ('txn_rollback', '事务回滚', '失败时回滚三表写入', 'stream_ingestion_cpp/pipeline.cpp', '"ROLLBACK"'),
]

def relative(path):
    return str(path.relative_to(ROOT))

def snippet(path, anchor=None, count=32):
    path = Path(path)
    lines = path.read_text().splitlines()
    index = next((i for i,line in enumerate(lines) if anchor and anchor in line), 0)
    return dict(file=relative(path), line=index+1, text='\n'.join(lines[index:index+count]),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def source_files():
    roots = [CPP, PYTHON, HERE, HERE.parent/'duckdb_parquet', HERE.parent/'news_jsonl']
    result = {}
    for root in roots:
        for path in root.rglob('*'):
            if any(part in {'build','vendor','output','.venv','__pycache__'} for part in path.relative_to(root).parts):
                continue
            if path.is_file() and (path.suffix in {'.cpp','.hpp','.py','.sql','.awk','.js','.css','.html','.sh'} or path.name=='CMakeLists.txt'):
                result[relative(path)] = path
    return result

def source_hashes():
    return {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in source_files().items()}

DESCRIPTIONS = {
    'tick':'采集轮次；归档使用左闭右开区间', 'event_time':'事件时间（UTC）',
    'received_at':'接收时间（UTC）', 'ingested_at':'输入中固定的模拟写入时间（UTC）',
    'instrument_id':'标的代码', 'venue':'市场', 'currency':'币种',
    'bid_cents':'买价，整数分', 'ask_cents':'卖价，整数分', 'bid_size':'买量，整数股数',
    'ask_size':'卖量，整数股数', 'trade_id':'成交唯一标识', 'team_id':'团队标识',
    'side':'买卖方向 BUY / SELL', 'quantity':'成交数量', 'price_cents':'成交价，整数分',
    'fee_cents':'手续费，整数分', 'cash_cents':'现金，整数分', 'positions':'标的 → 持仓数量的 JSON 对象',
    'equity_cents':'总权益，整数分', 'pnl_cents':'盈亏，整数分',
    'symbol':'标的代码', 'bid_ticks':'买价，1 tick = 0.01 EUR', 'ask_ticks':'卖价，1 tick = 0.01 EUR', 'seq':'生成器全局序号',
}

def catalog():
    tables = []
    with duckdb.connect(':memory:', config={'threads':1}) as db:
        for group, title in [('market','行情'),('trades','团队成交'),('accounts','账户快照')]:
            path = CPP/group/'storage.cpp'
            sql = re.search(r'R"SQL\((.*?)\)SQL"', path.read_text(), re.S).group(1)
            db.execute(sql)
            table = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', sql).group(1)
            tables.append(dict(name=table,title=title,kind='DuckDB',family='stream',ddl=sql.strip(),source=snippet(path,'void create_table(')))
        demo = HERE.parent/'duckdb_parquet'/'demo.py'
        tree = ast.parse(demo.read_text())
        schema = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMA' for t in node.targets))
        sql = f'CREATE TABLE quotes_batch ({schema})'
        db.execute(sql)
        tables.append(dict(name='quotes_batch', title='早期 Parquet 行情示例',kind='DuckDB 内存表',family='legacy',ddl=sql,source=snippet(demo,'SCHEMA =')))
        for table in tables:
            constraints = db.execute('SELECT constraint_type, constraint_text, constraint_column_names FROM duckdb_constraints() WHERE table_name = ?', [table['name']]).fetchall()
            table['constraints'] = [dict(type=a,text=b,columns=c) for a,b,c in constraints]
            pk = {name for kind,_,names in constraints if kind=='PRIMARY KEY' for name in names}
            columns = db.execute('SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_name=? ORDER BY ordinal_position',[table['name']]).fetchall()
            table['columns'] = [dict(name=name,type=typ,nullable=nullable=='YES',primary=name in pk,description=DESCRIPTIONS.get(name,'')) for name,typ,nullable in columns]
    fields = [('news_id','string'),('tick','int64'),('source','string'),('published_at','ISO time'),('received_at','ISO time'),('ingested_at','ISO time'),('title','string'),('body','string'),('symbols','string[]'),('symbol_status','string'),('unrecognized_symbols','string[]'),('symbol_method','string'),('raw_text','string')]
    parser = CPP/'news'/'parser.cpp'
    # Validate this display list against the owning return object on every start.
    found = re.findall(r'\{"(\w+)",', parser.read_text().split('return {{"news_id"',1)[1])
    if {'news_id',*found} != {name for name,_ in fields}:
        raise ValueError('News schema changed; update its type descriptions before displaying it')
    tables.append(dict(name='news.jsonl', title='新闻追加日志',kind='JSONL 文件 · 非数据库表',family='news',
        columns=[dict(name=n,type=t,nullable=False,primary=False,description='保留原始文本' if n=='raw_text' else '') for n,t in fields],
        constraints=[], ddl='无数据库 PK / NOT NULL / CHECK 约束；parser 的必需头部访问负责输入检查。', source=snippet(parser,'return {{"news_id"',20)))
    return tables

def evidence():
    specs = [
        ('batch','列式批量写入','源码已确认','C API Appender + DataChunk，整数列批量复制。批处理本身不等于 SIMD 证据。',CPP/'support/db.hpp','inline size_t append_columns'),
        ('threads','多线程配置与观测','配置 ≠ 并行证明','--threads 设置 DuckDB 的线程预算。主业务流程顺序执行；运行页显示实际进程线程数快照，但线程存在不代表同时有效工作。',CPP/'support/db.hpp','explicit Database('),
        ('simd','SIMD / 自动向量化','需要逐循环证据','现有账户估值包含逐项 __int128 溢出检查。下方展示本次编译器的 loop-vectorize 报告；未提供运行时 SIMD 指令比例，也不推断预编译 DuckDB 内部执行路径。',CPP/'accounts/calculate.cpp','std::vector<int64_t> mark_to_market'),
        ('numpy','NumPy 数组计算','源码已确认','数组接口与 int64 持仓计算可核对源码；这不自动证明某次调用走了 SIMD。',PYTHON/'accounts/transform.py','def value_accounts'),
        ('transaction','事务与状态推进','源码已确认','三表一个事务；只有 COMMIT 成功后才推进账户状态。新闻文件独立写入。',CPP/'pipeline.cpp','void write_tick('),
        ('archive','归档发布与压缩','源码已确认','ZSTD Parquet 写入暂存目录，三表完成后发布目录。',CPP/'pipeline.cpp','std::string export_batch('),
        ('native','macOS 原生性能计数器','本机调用可核验','proc_pid_rusage(RUSAGE_INFO_V4) 提供进程累计 instructions / cycles，getrusage 提供 CPU、缺页与切换计数。前后快照做差，包含采样开销及进程内其他线程活动。',HERE/'native/probe.hpp','inline Snapshot snapshot()'),
    ]
    return [dict(id=id,title=title,status=status,description=desc,source=snippet(path,anchor,45)) for id,title,status,desc,path,anchor in specs]

def compile_evidence():
    log = HERE/'build'/'build.log'
    lines = log.read_text(errors='replace').splitlines() if log.exists() else []
    selected = {}
    pattern = re.compile(r'(/[^\n]+/stream_ingestion_cpp/([^:\n]+)):(\d+):(\d+): remark: (.*)')
    for line in lines:
        match = pattern.match(line)
        if not match or '/vendor/' in line or 'loop' not in line:
            continue
        path, name, number, column, message = match.groups()
        name = name.replace('./','')
        if not (CPP/name).is_file():
            continue
        code = (CPP/name).read_text().splitlines()
        selected[(name,int(number),message)] = f'{name}:{number}:{column}: {message}\n  {code[int(number)-1]}'
    manifest = HERE/'build'/'provenance.json'
    ordered = sorted(selected,key=lambda key:(not key[0].startswith('accounts/calculate'),key))
    return dict(remarks='\n\n'.join(selected[key] for key in ordered), manifest=json.loads(manifest.read_text()) if manifest.exists() else None,
                note='编译报告只证明编译器对具体循环的决定；不证明该循环在本次运行中被执行。完整日志位于 build/build.log。')

def environment():
    proc = subprocess.run(['xcrun','xctrace','list','templates'],capture_output=True,text=True,timeout=10)
    return dict(os=platform.platform(),arch=platform.machine(),python=platform.python_version(),duckdb=duckdb.__version__,
                xctrace=proc.returncode==0,xctrace_detail=(proc.stdout if proc.returncode==0 else proc.stderr).strip()[:2000],
                counter_source='macOS proc_pid_rusage · RUSAGE_INFO_V4',
                unavailable=['cache-misses','branch-misses','CPU migrations'],
                references=[
                    {'title':'Apple XNU：Recount 计数器口径','url':'https://github.com/apple-oss-distributions/xnu/blob/main/doc/observability/recount.md'},
                    {'title':'Apple：CPU Counters / Instruments','url':'https://developer.apple.com/documentation/xcode/addressing-cpu-bottlenecks'},
                    {'title':'Apple：Xcode 命令行工具','url':'https://developer.apple.com/documentation/xcode/installing-the-command-line-tools/'}])

def bootstrap():
    return dict(tables=catalog(), evidence=evidence(), build=compile_evidence(), environment=environment(),
                stages=[dict(id=id,title=title,description=desc,source=snippet(HERE.parent/path,anchor,28)) for id,title,desc,path,anchor in STAGES])

