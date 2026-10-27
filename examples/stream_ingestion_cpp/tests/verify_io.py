"""真实节拍、SIGTERM 尾批和每个业务目录独立复制编译的验收。"""

import contextlib
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_fixture import generate
from verify_pair import verify_pair
from verify_run import verify


def standalone_modules():
    samples = {
        "market": dict(event_time=0, instrument_id="ALPHA", bid_cents=100, ask_cents=102, bid_size=10, ask_size=20),
        "trades": dict(event_time=0, trade_id="t1", team_id="TEAM_A", instrument_id="ALPHA", side="BUY", quantity=1, price_cents=102, fee_cents=1),
        "accounts": dict(event_time=0, team_id="TEAM_A", cash_cents=100, positions={"ALPHA": 1}, equity_cents=201, pnl_cents=1),
    }
    library_dir = ROOT / "vendor/duckdb"
    library = library_dir / ("libduckdb.dylib" if sys.platform == "darwin" else "libduckdb.so")
    for name in ("market", "trades", "accounts", "news"):
        with tempfile.TemporaryDirectory(prefix=f"standalone-{name}-") as temporary:
            path = Path(temporary)
            shutil.copytree(ROOT / name, path / name)
            shutil.copytree(ROOT / "support", path / "support")
            if name != "news":
                source = f'''#include "{name}/storage.hpp"
#include "support/db.hpp"
int main() {{
    support::Database database("sample.duckdb");
    auto connection = database.connection;
    {name}::create_table(connection);
    auto records = support::Json::parse(R"JSON([{json.dumps(samples[name])}])JSON");
    {name}::write_records(connection, records, {{0, 0, 0}}, {name}::Params{{}});
    {name}::export_parquet(connection, "sample.parquet", 0, 1);
    return support::scalar(connection, "SELECT count(*) FROM read_parquet('sample.parquet')") == 1 ? 0 : 1;
}}
'''
                sources = [path / name / "transform.cpp", path / name / "storage.cpp"]
            else:
                source = '''#include "news/writer.hpp"
int main() {
    support::Json records = {"News-ID: n1\\nPublished-At: 2026-10-26T09:00:00Z\\nTitle: 中文\\nSymbols: ALPHA\\nBody: 第一行\\n"};
    return news::write_records("news.jsonl", records, {0, 0, 0}, news::Params{}) == 1 ? 0 : 1;
}
'''
                sources = [path / name / "parser.cpp", path / name / "writer.cpp"]
            (path / "main.cpp").write_text(source)
            command = ["c++", "-std=c++20", "-O2", "-I", str(path), "-I", str(ROOT / "vendor"), "-I", str(library_dir),
                       str(path / "main.cpp"), *map(str, sources), "-o", str(path / "standalone")]
            if name != "news":
                command += [str(library), f"-Wl,-rpath,{library_dir}"]
            subprocess.run(command, cwd=path, check=True, capture_output=True, text=True, timeout=60)
            subprocess.run([str(path / "standalone")], cwd=path, check=True, capture_output=True, text=True, timeout=10)
            print(f"PASS: copy {name}/ + support/, compile and use without other business modules", flush=True)


def main():
    (ROOT / "output").mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="validation-", dir=ROOT / "output"))
    fixture = directory / "fixture.json"
    generate(fixture, seconds=6, export_every=5)
    binary = ROOT / "build/ingest_cpp"
    def command(output):
        return [str(binary), "--input", str(fixture), "--output", str(output)]
    real = directory / "realtime"
    subprocess.run(command(real), check=True, timeout=20)
    verify(real)
    stopped = directory / "sigterm"
    process = subprocess.Popen(command(stopped), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for line in process.stdout:
            if line.startswith("COMMIT"):
                process.send_signal(signal.SIGTERM)
                break
        stdout, stderr = process.communicate(timeout=10)
        if process.returncode:
            raise RuntimeError(stdout + stderr)
        info = json.loads((stopped / "run.json").read_text())
        if info["status"] != "stopped" or info["committed_ticks"] != 1:
            raise AssertionError("SIGTERM did not publish a one-tick tail")
        verify(stopped)
    finally:
        if process.poll() is None:
            process.kill(); process.communicate()
    # Independent parameter changes, including axes order, currency and header name.
    changed = json.loads(fixture.read_text())
    old_symbol, new_symbol = "ALPHA", "OMEGA"
    # Replace exact fixture strings/keys by re-encoding; no external input involved.
    changed = json.loads(json.dumps(changed).replace(old_symbol, new_symbol))
    info = changed["metadata"]
    info["teams"] = list(reversed(info["teams"]))
    info["currency"] = "USD"
    for name in ("market", "trades", "accounts"):
        info["parameters"][name]["currency"] = "USD"
    info["parameters"]["accounts"]["teams"] = info["teams"]
    info["parameters"]["news"]["symbols_field"] = "Tickers"
    for tick in changed["ticks"]:
        tick["news"] = [raw.replace("Symbols:", "Tickers:") for raw in tick["news"]]
    changed_path = directory / "changed.json"
    changed_path.write_text(json.dumps(changed, ensure_ascii=False))
    cpp, numpy = directory / "changed-cpp", directory / "changed-numpy"
    subprocess.run([str(binary), "--input", str(changed_path), "--output", str(cpp), "--fast"], check=True, timeout=20)
    subprocess.run([sys.executable, str(ROOT / "python_worker.py"), "--input", str(changed_path), "--output", str(numpy)], check=True, timeout=20)
    verify_pair(changed_path, numpy, cpp)
    standalone_modules()
    report = "PASS: six real one-second ticks and five-second export override; SIGTERM tail; independently changed symbols, currency, team order and news header; four business folders copied/compiled alone with support/.\n"
    (directory / "validation.txt").write_text(report)
    print(f"VALIDATION_DIR={directory}", flush=True)


if __name__ == "__main__":
    main()
